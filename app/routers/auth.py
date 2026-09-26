from datetime import datetime, timedelta, timezone
import bcrypt
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
import jwt
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.user import User
from app.models.audit_log import create_audit_log

router = APIRouter()
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")
ALGORITHM = "HS256"

def get_current_user(token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    exc = HTTPException(status_code=401, detail="Token tidak valid")
    try:
        payload = jwt.decode(token, settings.secret_key, algorithms=[ALGORITHM])
        username = payload.get("sub")
        if not username:
            raise exc
    except jwt.PyJWTError:
        raise exc
    user = db.query(User).filter(User.username == username).first()
    if not user: raise exc
    return user

def get_current_admin(current_user: User = Depends(get_current_user)):
    if current_user.role != "admin":
        raise HTTPException(status_code=403, detail="Hanya untuk admin")
    return current_user

@router.post("/login", summary="Login Dapatkan Token")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(User).filter(User.username == form_data.username).first()
    
    # Verifikasi password menggunakan bcrypt murni (aman dari bug passlib & batas 72 bytes)
    password_valid = False
    if user and user.hashed_password:
        try:
            plain_bytes = form_data.password[:72].encode('utf-8')
            hashed_bytes = user.hashed_password.encode('utf-8')
            password_valid = bcrypt.checkpw(plain_bytes, hashed_bytes)
        except Exception:
            password_valid = False

    if not user or not password_valid:
        raise HTTPException(status_code=401, detail="Kredensial salah")
    
    expire = datetime.now(timezone.utc) + timedelta(hours=8)
    token = jwt.encode({"sub": user.username, "role": user.role, "exp": expire}, settings.secret_key, algorithm=ALGORITHM)
    
    create_audit_log(db, user_id=user.id, action="LOGIN")
    return {"access_token": token, "token_type": "bearer"}