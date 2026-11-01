"""
app/services/klasifikasi_service.py
Aturan terpusat untuk verifikasi publikasi draft kajian (Langkah 35).
"""
from datetime import datetime, timezone
from typing import Any, Optional

from fastapi import HTTPException, status

from app.config import settings
from app.core.permissions import Izin, punya_izin


def periksa_publikasi_draft(
    peran: Any,
    klasifikasi: Any,
    persetujuan: Optional[Any],
    user: Optional[Any] = None,
) -> Optional[dict]:
    """
    Aturan validasi publikasi draft kajian:
    - Jika draft_kajian + publik:
      - Wajib memiliki persetujuan lengkap (disetujui_oleh dan alasan >= 10 karakter setelah strip).
      - Jika AUTH_ENABLED=true: pengguna wajib memiliki izin Izin.DRAFT_PUBLIKASI (hanya admin_kb).
        disetujui_oleh otomatis diisi dari username login pengguna (nilai dari klien diabaikan).
      - Jika AUTH_ENABLED=false: disetujui_oleh diambil dari klien apa adanya.
      - Mengembalikan dict {"disetujui_oleh": str, "alasan": str, "pada": datetime}.
    - Kombinasi peran & klasifikasi lain: mengembalikan None.
    """
    peran_str = peran.value if hasattr(peran, "value") else str(peran or "")
    klasifikasi_str = klasifikasi.value if hasattr(klasifikasi, "value") else str(klasifikasi or "")

    if peran_str == "draft_kajian" and klasifikasi_str == "publik":
        pesan_galat_422 = {
            "code": "draft_publik_butuh_persetujuan",
            "message": "Draft kajian hanya boleh publik dengan persetujuan (disetujui_oleh dan alasan wajib diisi).",
        }

        if persetujuan is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=pesan_galat_422,
            )

        if isinstance(persetujuan, dict):
            disetujui_oleh_raw = persetujuan.get("disetujui_oleh")
            alasan_raw = persetujuan.get("alasan")
        else:
            disetujui_oleh_raw = getattr(persetujuan, "disetujui_oleh", None)
            alasan_raw = getattr(persetujuan, "alasan", None)

        alasan = (alasan_raw or "").strip()
        if len(alasan) < 10:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=pesan_galat_422,
            )

        if settings.auth_enabled:
            if not user or not getattr(user, "is_active", False):
                raise HTTPException(
                    status_code=status.HTTP_401_UNAUTHORIZED,
                    detail="Otentikasi diperlukan",
                )

            if not punya_izin(user, Izin.DRAFT_PUBLIKASI):
                role = getattr(user, "role", None)
                role_str = str(role.value if hasattr(role, "value") else role) if role is not None else ""
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "akses_ditolak",
                        "izin": Izin.DRAFT_PUBLIKASI.value,
                        "peran": role_str,
                        "message": f"Akun Anda tidak memiliki izin {Izin.DRAFT_PUBLIKASI.value} untuk aksi ini.",
                    },
                )

            disetujui_oleh = getattr(user, "username", None) or "admin"
        else:
            disetujui_oleh = (disetujui_oleh_raw or "").strip()
            if not disetujui_oleh:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=pesan_galat_422,
                )

        return {
            "disetujui_oleh": disetujui_oleh,
            "alasan": alasan,
            "pada": datetime.now(timezone.utc),
        }

    return None

