"""
app/schemas/user.py
Skema Pydantic untuk manajemen pengguna dan profil peran (Langkah 23, US-01 #32).
"""
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field, ConfigDict

from app.core.permissions import PeranPengguna


class UserResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: int
    username: str
    nama_lengkap: Optional[str] = None
    unit_kerja: Optional[str] = None
    role: str
    is_active: bool
    created_at: Optional[datetime] = None


class UserCreateIn(BaseModel):
    username: str = Field(..., min_length=3, max_length=100, description="Username unik login")
    password: str = Field(..., min_length=12, description="Password minimal 12 karakter")
    role: PeranPengguna = Field(..., description="Peran akses pengguna")
    nama_lengkap: Optional[str] = Field(None, max_length=150, description="Nama lengkap pengguna")
    unit_kerja: Optional[str] = Field(None, max_length=150, description="Unit kerja / divisi")


class UserUpdateIn(BaseModel):
    role: Optional[PeranPengguna] = Field(None, description="Peran akses baru")
    is_active: Optional[bool] = Field(None, description="Status aktif pengguna")
    nama_lengkap: Optional[str] = Field(None, max_length=150, description="Nama lengkap pengguna")
    unit_kerja: Optional[str] = Field(None, max_length=150, description="Unit kerja / divisi")
    password: Optional[str] = Field(None, min_length=12, description="Password baru minimal 12 karakter")
