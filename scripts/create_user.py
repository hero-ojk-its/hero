#!/usr/bin/env python3
"""
Skrip pembuatan akun pengguna administratif HERO Backend (US-01 #32).
Dipakai terutama untuk membuat Admin Sistem pertama di VPS sebelum AUTH_ENABLED diaktifkan.

Keamanan:
- Password dibaca dari variabel lingkungan HERO_NEW_USER_PASSWORD atau getpass (interaktif).
- Password tidak boleh lewat argumen CLI dan tidak pernah dicetak ke output/log.
- Idempoten: bila username sudah ada, skrip keluar tanpa mengubah apa pun.
"""
import argparse
import getpass
import os
import sys
from pathlib import Path

# Tambahkan direktori root ke sys.path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt
from app.database import SessionLocal
from app.models.user import User
from app.core.permissions import PeranPengguna
from app.services.audit_service import record_audit, CREATE_USER


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Buat akun pengguna HERO Backend dengan peran tertentu.",
    )
    parser.add_argument("--username", required=True, help="Username unik pengguna")
    parser.add_argument(
        "--role",
        required=True,
        choices=[p.value for p in PeranPengguna],
        help="Peran pengguna: analis, admin_kb, admin_sistem, pilot_user",
    )
    parser.add_argument("--nama", dest="nama_lengkap", default=None, help="Nama lengkap pengguna")
    parser.add_argument("--unit", dest="unit_kerja", default=None, help="Unit kerja atau kedinasan pengguna")

    args = parser.parse_args()

    db = SessionLocal()
    try:
        # 1. Cek keberadaan pengguna (Idempoten)
        existing_user = db.query(User).filter(User.username == args.username).first()
        if existing_user:
            print(f"Pengguna '{args.username}' sudah terdaftar. Tidak ada perubahan yang dilakukan.")
            return 0

        # 2. Ambil password secara aman
        raw_password = os.environ.get("HERO_NEW_USER_PASSWORD")
        if not raw_password:
            raw_password = getpass.getpass(prompt="Masukkan password baru (minimal 12 karakter): ")

        if not raw_password or len(raw_password) < 12:
            print("Galat: Password wajib diisi dan minimal 12 karakter.", file=sys.stderr)
            return 1

        # 3. Hash password dengan bcrypt
        password_bytes = raw_password[:72].encode("utf-8")
        hashed_password = bcrypt.hashpw(password_bytes, bcrypt.gensalt()).decode("utf-8")

        # 4. Buat objek User
        new_user = User(
            username=args.username,
            hashed_password=hashed_password,
            role=args.role,
            nama_lengkap=args.nama_lengkap,
            unit_kerja=args.unit_kerja,
            is_active=True,
        )
        db.add(new_user)
        db.commit()
        db.refresh(new_user)

        # 5. Catat ke audit log
        try:
            record_audit(
                db,
                action=CREATE_USER,
                user_id=new_user.id,
                target_resource=f"user:{new_user.id}",
                detail={
                    "username": new_user.username,
                    "role": new_user.role,
                    "nama_lengkap": new_user.nama_lengkap,
                    "unit_kerja": new_user.unit_kerja,
                    "dibuat_lewat": "scripts/create_user.py",
                },
                commit=True,
            )
        except Exception:
            # Kegagalan audit log tidak menggagalkan pembuatan user
            pass

        print(f"Pengguna '{new_user.username}' dengan peran '{new_user.role}' berhasil dibuat.")
        return 0

    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(main())
