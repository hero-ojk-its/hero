"""
scripts/buka_kunci_login.py
Membuka kunci lockout login untuk akun (u:<username>) atau alamat IP (ip:<ip>) (Langkah 34).

Pemakaian:
    python scripts/buka_kunci_login.py --username <username> [--apply]
    python scripts/buka_kunci_login.py --ip <ip_address> [--apply]
"""
import argparse
from pathlib import Path
import sys
from typing import Optional

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy.orm import Session
import app.database
from app.models.percobaan_login import PercobaanLogin


def buka_kunci(
    username: Optional[str] = None,
    ip: Optional[str] = None,
    apply: bool = False,
    db: Optional[Session] = None,
) -> None:
    own_db = False
    if db is None:
        db = app.database.SessionLocal()
        own_db = True

    try:
        target_keys = []
        if username:
            target_keys.append(f"u:{username.strip().lower()}")
        if ip:
            target_keys.append(f"ip:{ip.strip()}")

        if not target_keys:
            print("Peringatan: Tentukan --username atau --ip untuk membuka kunci.")
            return

        records = (
            db.query(PercobaanLogin)
            .filter(PercobaanLogin.kunci.in_(target_keys))
            .all()
        )

        if not records:
            print("Tidak ada catatan lockout yang cocok dengan kunci yang diminta.")
            return

        for rec in records:
            terkunci_str = (
                rec.terkunci_sampai.isoformat()
                if rec.terkunci_sampai
                else "tidak_terkunci"
            )
            if apply:
                rec.jumlah_gagal = 0
                rec.terkunci_sampai = None
                db.add(rec)
                print(f"[APPLY] Kunci '{rec.kunci}' berhasil dibuka (sebelumnya gagal={rec.jumlah_gagal}, status={terkunci_str}).")
            else:
                print(f"[DRY-RUN] Kunci '{rec.kunci}' ditemukan (gagal={rec.jumlah_gagal}, terkunci_sampai={terkunci_str}). Gunakan --apply untuk membuka kunci.")

        if apply:
            db.commit()
    finally:
        if own_db:
            db.close()


def main():
    parser = argparse.ArgumentParser(description="Membuka status lockout percobaan login HERO Backend.")
    parser.add_argument("--username", "-u", type=str, help="Username yang ingin dibuka kuncinya")
    parser.add_argument("--ip", type=str, help="Alamat IP yang ingin dibuka kuncinya")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Terapkan pembukaan kunci ke database (default: dry-run)",
    )
    args = parser.parse_args()

    buka_kunci(username=args.username, ip=args.ip, apply=args.apply)


if __name__ == "__main__":
    main()

