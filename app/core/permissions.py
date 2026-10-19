"""
app/core/permissions.py
Matriks hak akses dan dependensi otorisasi berbasis peran (Langkah 23, US-01 #32).

Prinsip utama:
- Hanya dict HAK_AKSES_PERAN yang menentukan siapa boleh apa.
- Router tidak boleh memeriksa nama peran secara langsung.
- Bila AUTH_ENABLED=false, seluruh pemeriksaan otorisasi dilewati (mengembalikan None).
"""
from enum import Enum
from typing import Any, Callable, Dict, Optional, Set

from fastapi import Depends, HTTPException, Request, status
from sqlalchemy.orm import Session

from app.config import settings


class Izin(str, Enum):
    """Daftar kode hak akses fitur dalam sistem HERO."""
    KB_BACA = "KB_BACA"
    KB_BACA_NONPUBLIK = "KB_BACA_NONPUBLIK"
    DOKUMEN_UNGGAH = "DOKUMEN_UNGGAH"
    METADATA_KOREKSI = "METADATA_KOREKSI"
    KEGAGALAN_KELOLA = "KEGAGALAN_KELOLA"
    ANALISA_JALANKAN = "ANALISA_JALANKAN"
    ANALISA_EKSPOR = "ANALISA_EKSPOR"
    MODE_ATUR = "MODE_ATUR"
    SUMBER_KELOLA = "SUMBER_KELOLA"
    KB_KELOLA = "KB_KELOLA"
    STATUS_UBAH = "STATUS_UBAH"
    AUDIT_BACA = "AUDIT_BACA"
    PENGGUNA_KELOLA = "PENGGUNA_KELOLA"
    TANGGAPAN_TINJAU = "TANGGAPAN_TINJAU"


class PeranPengguna(str, Enum):
    """Peran pengguna sistem HERO sesuai dokumen 08 §PERAN."""
    analis = "analis"
    admin_kb = "admin_kb"
    admin_sistem = "admin_sistem"
    pilot_user = "pilot_user"


# CATATAN ARSITEKTUR — Menunggu keputusan final Pak Faris untuk 4 hal berikut:
# 1. Apakah Admin KB / Admin Sistem juga mendapat hak Analis?
#    (Saat ini: dipisah ketat; Analis fokus analisa, Admin KB fokus repositori, Admin Sistem fokus sistem)
# 2. Apakah Pilot User boleh membaca KB?
#    (Saat ini: dibatasi ketat, Pilot User hanya memiliki izin TANGGAPAN_TINJAU)
# 3. Siapa yang boleh STATUS_UBAH?
#    (Saat ini: dialokasikan ke Admin KB)
# 4. Siapa yang boleh KB_BACA_NONPUBLIK?
#    (Saat ini: dialokasikan ke Analis dan Admin KB)
#
# Saat ini dipilih opsi paling ketat. Perubahan kebijakan cukup dilakukan di dict HAK_AKSES_PERAN ini.
HAK_AKSES_PERAN: Dict[PeranPengguna, Set[Izin]] = {
    PeranPengguna.analis: {
        Izin.KB_BACA,
        Izin.KB_BACA_NONPUBLIK,
        Izin.DOKUMEN_UNGGAH,
        Izin.METADATA_KOREKSI,
        Izin.KEGAGALAN_KELOLA,
        Izin.ANALISA_JALANKAN,
        Izin.ANALISA_EKSPOR,
        Izin.MODE_ATUR,
        Izin.TANGGAPAN_TINJAU,
    },
    PeranPengguna.admin_kb: {
        Izin.KB_BACA,
        Izin.KB_BACA_NONPUBLIK,
        Izin.SUMBER_KELOLA,
        Izin.KB_KELOLA,
        Izin.STATUS_UBAH,
    },
    PeranPengguna.admin_sistem: {
        Izin.MODE_ATUR,
        Izin.AUDIT_BACA,
        Izin.PENGGUNA_KELOLA,
    },
    PeranPengguna.pilot_user: {
        Izin.TANGGAPAN_TINJAU,
    },
}


def _resolve_role_enum(role: Any) -> Optional[PeranPengguna]:
    """Helper untuk memetakan string role ke PeranPengguna enum."""
    if isinstance(role, PeranPengguna):
        return role
    if isinstance(role, str) and role in PeranPengguna._value2member_map_:
        return PeranPengguna(role)
    return None


def boleh_baca_nonpublik(user: Optional[Any] = None) -> bool:
    """
    Menentukan apakah pengguna diizinkan membaca dokumen non-publik:
    - auth_enabled=false: kembalikan not settings.protect_non_public_when_auth_disabled (perilaku sekarang)
    - auth_enabled=true: user aktif yang memiliki izin KB_BACA_NONPUBLIK
    """
    if not settings.auth_enabled:
        return not settings.protect_non_public_when_auth_disabled

    if not user or not getattr(user, "is_active", False):
        return False

    role_enum = _resolve_role_enum(getattr(user, "role", None))
    if not role_enum:
        return False

    allowed_perms = HAK_AKSES_PERAN.get(role_enum, set())
    return Izin.KB_BACA_NONPUBLIK in allowed_perms


def check_non_public_access(doc: Any, user: Optional[Any] = None) -> None:
    """
    Memvalidasi akses ke dokumen non-publik.
    Melempar HTTPException 403 bila dokumen non-publik dan pengguna tidak diizinkan.
    Pesan galat:
    - Auth nonaktif: 'Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.'
    - Auth aktif: {'code': 'akses_ditolak', 'izin': 'KB_BACA_NONPUBLIK'}
    """
    from app.models.enums import KlasifikasiAkses

    acc_class = getattr(doc, "access_classification", None)
    if acc_class == KlasifikasiAkses.non_publik or (isinstance(acc_class, str) and acc_class == "non_publik"):
        if not boleh_baca_nonpublik(user):
            if not settings.auth_enabled:
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail="Dokumen non-publik hanya dapat dibuka setelah login diaktifkan.",
                )
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={"code": "akses_ditolak", "izin": "KB_BACA_NONPUBLIK"},
            )


def perlu_izin(izin: Izin) -> Callable[..., Any]:
    """
    FastAPI dependency factory untuk memvalidasi hak akses pengguna berdasarkan matriks izin:
    - auth_enabled=false: kembalikan None dan izinkan akses (tidak mengubah perilaku lama).
    - auth_enabled=true:
      - tanpa token / token tidak valid: 401
      - akun nonaktif: 401 "Akun pengguna tidak aktif"
      - peran tidak punya izin: 403 {"code": "akses_ditolak", "izin": "<nama izin>", "peran": "<peran>"}
    - Peran dibaca dari DB setiap request, bukan dari klaim token, supaya perubahan peran langsung berlaku.
    """
    from app.routers.auth import get_current_user
    from app.database import get_db

    def secured_dependency(
        request: Request,
        user: Optional[Any] = Depends(get_current_user),
        db: Session = Depends(get_db),
    ) -> Optional[Any]:
        if not settings.auth_enabled:
            return None

        if user is None:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Otentikasi diperlukan",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not getattr(user, "is_active", False):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Akun pengguna tidak aktif",
                headers={"WWW-Authenticate": "Bearer"},
            )

        role = getattr(user, "role", None)
        role_enum = _resolve_role_enum(role)
        allowed_perms = HAK_AKSES_PERAN.get(role_enum, set()) if role_enum else set()

        if izin not in allowed_perms:
            # Jika request mengakses dokumen non-publik, dahulukan penolakan izin KB_BACA_NONPUBLIK (P07)
            doc_id = request.path_params.get("document_id") or request.path_params.get("id")
            if doc_id and db is not None:
                try:
                    from app.models.document import Document
                    from app.models.enums import KlasifikasiAkses
                    doc_obj = db.query(Document).filter(Document.id == int(doc_id)).first()
                    if doc_obj:
                        acc_class = getattr(doc_obj, "access_classification", None)
                        if acc_class == KlasifikasiAkses.non_publik or (isinstance(acc_class, str) and acc_class == "non_publik"):
                            if not boleh_baca_nonpublik(user):
                                raise HTTPException(
                                    status_code=status.HTTP_403_FORBIDDEN,
                                    detail={"code": "akses_ditolak", "izin": "KB_BACA_NONPUBLIK"},
                                )
                except (ValueError, TypeError):
                    pass

            izin_str = izin.value if hasattr(izin, "value") else str(izin)
            role_str = str(role) if role is not None else ""
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "akses_ditolak",
                    "izin": izin_str,
                    "peran": role_str,
                },
            )

        return user

    return secured_dependency
