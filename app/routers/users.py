"""
app/routers/users.py
Router manajemen pengguna sistem HERO (Langkah 23, US-01 #32).
Seluruh endpoint memerlukan izin PENGGUNA_KELOLA (Admin Sistem).
"""
import logging
from typing import List, Optional

import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from sqlalchemy.orm import Session

from app.database import get_db
from app.core.permissions import Izin, PeranPengguna, perlu_izin
from app.models.user import User
from app.schemas.user import UserCreateIn, UserResponse, UserUpdateIn
from app.services.audit_service import CREATE_USER, UPDATE_USER, record_audit

logger = logging.getLogger("hero")

router = APIRouter(prefix="/api/v1/users", tags=["Users"])


@router.get(
    "/",
    response_model=List[UserResponse],
    summary="Daftar akun pengguna sistem",
)
def list_users(
    role: Optional[PeranPengguna] = Query(None, description="Filter berdasarkan peran"),
    is_active: Optional[bool] = Query(None, description="Filter status aktif"),
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.PENGGUNA_KELOLA)),
) -> List[User]:
    """
    Mengembalikan daftar seluruh akun pengguna sistem HERO.
    Kata sandi (hash) tidak pernah disertakan dalam respons.
    """
    query = db.query(User)
    if role is not None:
        role_val = role.value if hasattr(role, "value") else str(role)
        query = query.filter(User.role == role_val)
    if is_active is not None:
        query = query.filter(User.is_active == is_active)

    return query.order_by(User.id.asc()).all()


@router.post(
    "/",
    response_model=UserResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Buat akun pengguna baru",
)
def create_user(
    payload: UserCreateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.PENGGUNA_KELOLA)),
) -> User:
    """
    Membuat akun pengguna baru dengan peran tertentu.
    Password minimal 12 karakter di-hash menggunakan bcrypt.
    """
    # 1. Cek duplikasi username
    existing = db.query(User).filter(User.username == payload.username).first()
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "username_terdaftar",
                "message": f"Username '{payload.username}' sudah terdaftar.",
            },
        )

    # 2. Hash password dengan bcrypt (potong 72 bytes sesuai batas bcrypt)
    plain_bytes = payload.password[:72].encode("utf-8")
    hashed_str = bcrypt.hashpw(plain_bytes, bcrypt.gensalt()).decode("utf-8")

    role_val = payload.role.value if hasattr(payload.role, "value") else str(payload.role)

    # 3. Buat user baru
    new_user = User(
        username=payload.username,
        hashed_password=hashed_str,
        role=role_val,
        nama_lengkap=payload.nama_lengkap,
        unit_kerja=payload.unit_kerja,
        is_active=True,
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)

    # 4. Catat jejak audit (tanpa password)
    actor_id = getattr(current_user, "id", None) if current_user else None
    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=CREATE_USER,
        user_id=actor_id,
        target_resource=f"user:{new_user.id}",
        detail={
            "username": new_user.username,
            "role": new_user.role,
            "nama_lengkap": new_user.nama_lengkap,
            "unit_kerja": new_user.unit_kerja,
            "is_active": new_user.is_active,
        },
        ip_address=client_ip,
        commit=True,
    )

    return new_user


@router.patch(
    "/{user_id}",
    response_model=UserResponse,
    summary="Perbarui data atau peran akun pengguna",
)
def update_user(
    user_id: int,
    payload: UserUpdateIn,
    request: Request,
    db: Session = Depends(get_db),
    current_user=Depends(perlu_izin(Izin.PENGGUNA_KELOLA)),
) -> User:
    """
    Memperbarui profil, peran, status aktif, atau password akun pengguna.
    Tidak ada endpoint DELETE — akun cukup dinonaktifkan (is_active=False).

    Aturan perlindungan:
    - 409 'admin_terakhir': Ditolak bila perubahan menyebabkan tidak ada Admin Sistem aktif.
    - 409 'ubah_diri_sendiri': Ditolak bila Admin Sistem menonaktifkan atau menurunkan peran akun sendiri.
    """
    target = db.query(User).filter(User.id == user_id).first()
    if not target:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pengguna dengan ID {user_id} tidak ditemukan.",
        )

    actor_id = getattr(current_user, "id", None) if current_user else None
    target_is_admin = target.role == PeranPengguna.admin_sistem.value
    target_is_active = bool(target.is_active)

    new_role_val = payload.role.value if payload.role and hasattr(payload.role, "value") else (str(payload.role) if payload.role else None)
    will_demote_admin = (new_role_val is not None and new_role_val != PeranPengguna.admin_sistem.value)
    will_deactivate = (payload.is_active is False)

    # Guard 2: ubah_diri_sendiri
    # Admin Sistem tidak boleh menonaktifkan atau menurunkan peran akunnya sendiri
    if actor_id is not None and actor_id == target.id:
        if will_deactivate or (target_is_admin and will_demote_admin):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "ubah_diri_sendiri",
                    "message": "Admin Sistem tidak dapat menonaktifkan atau menurunkan peran akun sendiri.",
                },
            )

    # Guard 1: admin_terakhir
    # Jika target adalah Admin Sistem aktif dan akan dinonaktifkan atau diturunkan perannya
    if target_is_admin and target_is_active and (will_deactivate or will_demote_admin):
        other_admins_count = (
            db.query(User)
            .filter(
                User.id != target.id,
                User.role == PeranPengguna.admin_sistem.value,
                User.is_active == True,  # noqa: E712
            )
            .count()
        )
        if other_admins_count == 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "code": "admin_terakhir",
                    "message": "Tidak dapat menonaktifkan atau mengubah peran Admin Sistem aktif terakhir.",
                },
            )

    diff_detail = {}

    if payload.role is not None and target.role != new_role_val:
        diff_detail["role_sebelum"] = target.role
        diff_detail["role_sesudah"] = new_role_val
        target.role = new_role_val

    if payload.is_active is not None and target.is_active != payload.is_active:
        diff_detail["is_active_sebelum"] = target.is_active
        diff_detail["is_active_sesudah"] = payload.is_active
        target.is_active = payload.is_active

    if payload.nama_lengkap is not None and target.nama_lengkap != payload.nama_lengkap:
        diff_detail["nama_lengkap_sebelum"] = target.nama_lengkap
        diff_detail["nama_lengkap_sesudah"] = payload.nama_lengkap
        target.nama_lengkap = payload.nama_lengkap

    if payload.unit_kerja is not None and target.unit_kerja != payload.unit_kerja:
        diff_detail["unit_kerja_sebelum"] = target.unit_kerja
        diff_detail["unit_kerja_sesudah"] = payload.unit_kerja
        target.unit_kerja = payload.unit_kerja

    if payload.password:
        plain_bytes = payload.password[:72].encode("utf-8")
        target.hashed_password = bcrypt.hashpw(plain_bytes, bcrypt.gensalt()).decode("utf-8")
        diff_detail["password_diubah"] = True

    db.commit()
    db.refresh(target)

    # Catat jejak audit jika ada perubahan
    if diff_detail:
        client_ip = request.client.host if request.client else None
        record_audit(
            db,
            action=UPDATE_USER,
            user_id=actor_id,
            target_resource=f"user:{target.id}",
            detail=diff_detail,
            ip_address=client_ip,
            commit=True,
        )

    return target
