import math
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional, Tuple
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import HAK_AKSES_PERAN, Izin, PeranPengguna, perlu_izin
from app.database import get_db
from app.models.user import User
from app.models.percobaan_login import PercobaanLogin
from app.services.audit_service import (
    record_audit,
    LOGIN,
    LOGIN_FAILED,
    LOGIN_LOCKED,
)

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
ALGORITHM = "HS256"


def _catat_kegagalan_login(
    db: Session,
    kunci: str,
    now: datetime,
    maks_gagal: int,
    jendela_menit: int,
    kunci_menit: int,
) -> Tuple[int, bool]:
    """
    Mencatat satu kegagalan login untuk suatu kunci pelacak.
    Mengembalikan (jumlah_gagal_terbaru, baru_terkunci_boolean).
    Race-safe: menggunakan with_for_update() pada baris kunci.
    """
    rec = (
        db.query(PercobaanLogin)
        .filter(PercobaanLogin.kunci == kunci)
        .with_for_update()
        .first()
    )
    baru_terkunci = False
    if not rec:
        rec = PercobaanLogin(
            kunci=kunci,
            jumlah_gagal=1,
            jendela_mulai=now,
            terkunci_sampai=None,
            diperbarui=now,
        )
        db.add(rec)
        db.flush()
    else:
        if (now - rec.jendela_mulai) > timedelta(minutes=jendela_menit):
            rec.jumlah_gagal = 1
            rec.jendela_mulai = now
            rec.terkunci_sampai = None
        else:
            rec.jumlah_gagal += 1
        rec.diperbarui = now

    if rec.jumlah_gagal >= maks_gagal and (rec.terkunci_sampai is None or rec.terkunci_sampai <= now):
        rec.terkunci_sampai = now + timedelta(minutes=kunci_menit)
        baru_terkunci = True

    db.flush()
    return rec.jumlah_gagal, baru_terkunci


def get_current_user(
    token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> Optional[User]:
    if not settings.auth_enabled:
        return None

    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token otentikasi tidak ditemukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    exc = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Token tidak valid atau telah kedaluwarsa",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise exc
    except jwt.PyJWTError:
        raise exc

    user = db.query(User).filter(User.username == username).first()
    if not user:
        raise exc

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Akun pengguna tidak aktif",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return user


def get_current_admin(
    current_user: Optional[User] = Depends(perlu_izin(Izin.AUDIT_BACA)),
) -> Optional[User]:
    return current_user


CurrentUser = Annotated[Optional[User], Depends(get_current_user)]
CurrentAdmin = Annotated[Optional[User], Depends(get_current_admin)]


@router.get("/me", summary="Profil dan Hak Akses Pengguna Aktif")
def get_current_user_profile(
    current_user: Optional[User] = Depends(get_current_user),
):
    """
    Mengembalikan profil pengguna aktif dan daftar izin yang dimiliki berdasarkan peran.
    Bila mode autentikasi dinonaktifkan (AUTH_ENABLED=false), mengembalikan {'auth_enabled': False}.
    """
    if not settings.auth_enabled:
        return {"auth_enabled": False}

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Otentikasi diperlukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    role_val = current_user.role
    role_enum = None
    if isinstance(role_val, PeranPengguna):
        role_enum = role_val
    elif isinstance(role_val, str) and role_val in PeranPengguna._value2member_map_:
        role_enum = PeranPengguna(role_val)

    allowed_perms = HAK_AKSES_PERAN.get(role_enum, set()) if role_enum else set()

    return {
        "auth_enabled": True,
        "username": current_user.username,
        "nama_lengkap": current_user.nama_lengkap,
        "unit_kerja": current_user.unit_kerja,
        "role": current_user.role,
        "izin": sorted(list(p.value for p in allowed_perms)),
    }


@router.post("/login", summary="Login Dapatkan Token")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    client_ip = request.client.host if request.client else "127.0.0.1"
    raw_username = form_data.username or ""
    username_clean = raw_username.strip().lower()
    key_user = f"u:{username_clean}"
    key_ip = f"ip:{client_ip}"
    now = datetime.now(timezone.utc)

    # 1. Cek lockout sebelum memeriksa password
    locked_rec = (
        db.query(PercobaanLogin)
        .filter(
            PercobaanLogin.kunci.in_([key_user, key_ip]),
            PercobaanLogin.terkunci_sampai.isnot(None),
            PercobaanLogin.terkunci_sampai > now,
        )
        .order_by(PercobaanLogin.terkunci_sampai.desc())
        .first()
    )
    if locked_rec:
        sisa_detik = max(1, int((locked_rec.terkunci_sampai - now).total_seconds()))
        sisa_menit = max(1, math.ceil(sisa_detik / 60))
        record_audit(
            db,
            action=LOGIN_FAILED,
            user_id=None,
            target_resource=f"user:{raw_username}",
            detail={
                "username": raw_username,
                "alasan": "terkunci",
                "jumlah_gagal": locked_rec.jumlah_gagal,
            },
            ip_address=client_ip,
            commit=True,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"Terlalu banyak percobaan login. Coba lagi dalam {sisa_menit} menit.",
            headers={"Retry-After": str(sisa_detik)},
        )

    user = db.query(User).filter(User.username == raw_username.strip()).first()

    # Verifikasi password menggunakan bcrypt murni
    password_valid = False
    if user and user.hashed_password:
        try:
            plain_bytes = form_data.password[:72].encode('utf-8')
            hashed_bytes = user.hashed_password.encode('utf-8')
            password_valid = bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception:
            password_valid = False

    if not user or not password_valid:
        gagal_user, kunci_user = _catat_kegagalan_login(
            db, key_user, now,
            settings.login_maks_gagal_per_akun,
            settings.login_jendela_menit,
            settings.login_kunci_menit,
        )
        gagal_ip, kunci_ip = _catat_kegagalan_login(
            db, key_ip, now,
            settings.login_maks_gagal_per_ip,
            settings.login_jendela_menit,
            settings.login_kunci_menit,
        )
        if kunci_user or kunci_ip:
            record_audit(
                db,
                action=LOGIN_LOCKED,
                user_id=user.id if user else None,
                target_resource=f"user:{raw_username}",
                detail={
                    "username": raw_username,
                    "kunci": [k for k, terkunci in [(key_user, kunci_user), (key_ip, kunci_ip)] if terkunci],
                    "durasi_menit": settings.login_kunci_menit,
                },
                ip_address=client_ip,
                commit=False,
            )

        record_audit(
            db,
            action=LOGIN_FAILED,
            user_id=user.id if user else None,
            target_resource=f"user:{raw_username}",
            detail={
                "username": raw_username,
                "alasan": "kredensial_salah",
                "jumlah_gagal": gagal_user,
            },
            ip_address=client_ip,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kredensial salah")

    if not user.is_active:
        gagal_user, kunci_user = _catat_kegagalan_login(
            db, key_user, now,
            settings.login_maks_gagal_per_akun,
            settings.login_jendela_menit,
            settings.login_kunci_menit,
        )
        gagal_ip, kunci_ip = _catat_kegagalan_login(
            db, key_ip, now,
            settings.login_maks_gagal_per_ip,
            settings.login_jendela_menit,
            settings.login_kunci_menit,
        )
        if kunci_user or kunci_ip:
            record_audit(
                db,
                action=LOGIN_LOCKED,
                user_id=user.id,
                target_resource=f"user:{raw_username}",
                detail={
                    "username": raw_username,
                    "kunci": [k for k, terkunci in [(key_user, kunci_user), (key_ip, kunci_ip)] if terkunci],
                    "durasi_menit": settings.login_kunci_menit,
                },
                ip_address=client_ip,
                commit=False,
            )

        record_audit(
            db,
            action=LOGIN_FAILED,
            user_id=user.id,
            target_resource=f"user:{raw_username}",
            detail={
                "username": raw_username,
                "alasan": "akun_nonaktif",
                "jumlah_gagal": gagal_user,
            },
            ip_address=client_ip,
            commit=True,
        )
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun pengguna tidak aktif")

    # Sukses: reset kunci akun u:<username>
    rec_user = db.query(PercobaanLogin).filter(PercobaanLogin.kunci == key_user).first()
    if rec_user:
        rec_user.jumlah_gagal = 0
        rec_user.terkunci_sampai = None
        rec_user.diperbarui = now
        db.add(rec_user)

    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    peran_val = user.role.value if hasattr(user.role, "value") else str(user.role)
    token = jwt.encode(
        {"sub": user.username, "role": user.role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    record_audit(
        db,
        action=LOGIN,
        user_id=user.id,
        target_resource=f"user:{user.id}",
        detail={"username": user.username, "peran": peran_val},
        ip_address=client_ip,
        commit=True,
    )
    return {"access_token": token, "token_type": "bearer"}