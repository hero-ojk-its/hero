import os
import sys
import bcrypt
from app.config import settings
from app.database import SessionLocal
from app.models.user import User


def reset_admin_user():
    db = SessionLocal()
    try:
        raw_password = os.getenv("ADMIN_PASSWORD")
        if not raw_password:
            if settings.app_env == "development":
                print("⚠️  Peringatan: ADMIN_PASSWORD tidak diset, menggunakan default 'admin123' untuk lingkungan development.")
                raw_password = "admin123"
            else:
                print("❌ Kesalahan: ADMIN_PASSWORD wajib diset pada lingkungan non-development.", file=sys.stderr)
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
            print("🔄 Password akun admin berhasil di-reset ulang!")
        else:
            new_admin = User(
                username="admin",
                hashed_password=hashed_pw,
                role="admin",
                is_active=True
            )
            db.add(new_admin)
            print("✅ Akun admin baru berhasil dibuat!")

        db.commit()
        print("   Username: admin")
        print(f"   Password: {raw_password}")

    except Exception as e:
        db.rollback()
        print(f"❌ Terjadi kesalahan: {e}", file=sys.stderr)
    finally:
        db.close()


if __name__ == "__main__":
    reset_admin_user()