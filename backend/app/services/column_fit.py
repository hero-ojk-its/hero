"""
app/services/column_fit.py
Memangkas nilai teks ke panjang kolom String(n) sebelum disimpan.

Mengapa ada: sumber luar (mis. kolom "Sub Sektor" di ojk.go.id) kadang memuat
daftar yang lebih panjang daripada kolom database. Postgres menolak INSERT-nya
(``value too long for type character varying(100)``) dan seluruh pemindaian ikut
gagal, padahal seluruh isinya sah. Lebih baik menyimpan nilai yang dipangkas dan
bertanda "…" daripada kehilangan satu sesi pemindaian utuh.

PENTING: Modul ini TIDAK mengimpor app.database / app.models; model diberikan pemanggil.
"""
import logging
from typing import Any

logger = logging.getLogger("hero.column_fit")

ELLIPSIS = "…"


def fit_text(value: str, max_len: int) -> str:
    """Pangkas ``value`` agar muat ``max_len`` karakter; bagian terpotong ditandai ``…``."""
    if max_len <= 0 or len(value) <= max_len:
        return value
    if max_len == 1:
        return ELLIPSIS
    return value[: max_len - 1].rstrip() + ELLIPSIS


def clip_to_columns(obj: Any) -> int:
    """Pangkas atribut teks pada instance ORM sesuai panjang kolom String(n)-nya.

    Mengembalikan jumlah atribut yang dipangkas. Kolom tanpa batas panjang (Text)
    dan nilai bukan-teks dibiarkan.
    """
    clipped = 0
    for col in obj.__table__.columns:
        max_len = getattr(col.type, "length", None)
        if not max_len:
            continue
        value = getattr(obj, col.key, None)
        if isinstance(value, str) and len(value) > max_len:
            setattr(obj, col.key, fit_text(value, max_len))
            clipped += 1
            logger.warning(
                "Kolom %s.%s dipangkas dari %d ke %d karakter.",
                obj.__table__.name, col.key, len(value), max_len,
            )
    return clipped
