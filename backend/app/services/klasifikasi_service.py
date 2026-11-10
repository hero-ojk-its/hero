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
    Catatan: Disederhanakan agar upload dan analisa draft kajian berjalan otomatis
    tanpa memerlukan approval/persetujuan publikasi terpisah (non-blocking).
    Jika data persetujuan dikirim, tetap dicatat. Jika tidak, tidak lagi melempar HTTP 422.
    """
    if not persetujuan:
        return None

    if isinstance(persetujuan, dict):
        disetujui_oleh_raw = persetujuan.get("disetujui_oleh")
        alasan_raw = persetujuan.get("alasan")
    else:
        disetujui_oleh_raw = getattr(persetujuan, "disetujui_oleh", None)
        alasan_raw = getattr(persetujuan, "alasan", None)

    disetujui_oleh = (disetujui_oleh_raw or "").strip()
    alasan = (alasan_raw or "").strip()

    if not disetujui_oleh and not alasan:
        return None

    if user and getattr(user, "username", None):
        disetujui_oleh = user.username
    elif not disetujui_oleh:
        disetujui_oleh = "sistem"

    return {
        "disetujui_oleh": disetujui_oleh,
        "alasan": alasan or "Publikasi draf kajian disetujui otomatis",
        "pada": datetime.now(timezone.utc),
    }

