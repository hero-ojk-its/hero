"""
Usang: gunakan scripts/create_user.py --role admin_sistem untuk manajemen akun pengguna modern.
Skrip ini dipertahankan demi kompatibilitas alur reset admin lama.
"""
import os
import sys
from pathlib import Path

# Tambahkan direktori root ke sys.path bila dijalankan langsung
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import bcrypt
from app.config import settings
from app.database import SessionLocal
from app.models.user import User


def reset_admin_user():
    print("Usang: gunakan scripts/create_user.py --role admin_sistem")
    db = SessionLocal()
    try:
        raw_password = os.getenv("ADMIN_PASSWORD")
        if not raw_password:
            if settings.app_env == "development":
                print("Peringatan: ADMIN_PASSWORD tidak diset, menggunakan default untuk lingkungan development.")
                raw_password = "admin123"
            else:
                print("Kesalahan: ADMIN_PASSWORD wajib diset pada lingkungan non-development.", file=sys.stderr)
                sys.exit(1)

        # Cari user admin, jika ada update password-nya
        admin = db.query(User).filter(User.username == "admin").first()

        # Batasi maksimal 72 bytes untuk mencegah ValueError bcrypt
        safe_password = raw_password[:72].encode('utf-8')

        # Hash pakai library bcrypt murni
        hashed_bytes = bcrypt.hashpw(safe_password, bcrypt.gensalt())
        hashed_pw = hashed_bytes.decode('utf-8')

        if admin:
            admin.hashed_password = hashed_pw
            admin.role = "admin_sistem"
            print("Akun admin berhasil di-reset ulang!")
        else:
            new_admin = User(
                username="admin",
                hashed_password=hashed_pw,
                role="admin_sistem",
                is_active=True
            )
            db.add(new_admin)
            print("Akun admin baru berhasil dibuat!")

        db.commit()
        print("   Username: admin")

    except Exception as e:
        db.rollback()
        print(f"Terjadi kesalahan: {e}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    reset_admin_user()