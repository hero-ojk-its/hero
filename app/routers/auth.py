from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional
import bcrypt
from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.services.audit_service import record_audit, LOGIN

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login", auto_error=False)
ALGORITHM = "HS256"


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
    current_user: Optional[User] = Depends(get_current_user),
) -> Optional[User]:
    if not settings.auth_enabled:
        return None

    if not current_user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Otentikasi diperlukan",
            headers={"WWW-Authenticate": "Bearer"},
        )

    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Hanya untuk admin",
        )

    return current_user


CurrentUser = Annotated[Optional[User], Depends(get_current_user)]
CurrentAdmin = Annotated[Optional[User], Depends(get_current_admin)]


@router.post("/login", summary="Login Dapatkan Token")
def login(
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: Session = Depends(get_db),
):
    user = db.query(User).filter(User.username == form_data.username).first()

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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Kredensial salah")

    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Akun pengguna tidak aktif")

    expire = datetime.now(timezone.utc) + timedelta(hours=settings.access_token_expire_hours)
    token = jwt.encode(
        {"sub": user.username, "role": user.role, "exp": expire},
        settings.secret_key,
        algorithm=ALGORITHM,
    )

    client_ip = request.client.host if request.client else None
    record_audit(
        db,
        action=LOGIN,
        user_id=user.id,
        target_resource=f"user:{user.id}",
        ip_address=client_ip,
        commit=True,
    )
    return {"access_token": token, "token_type": "bearer"}