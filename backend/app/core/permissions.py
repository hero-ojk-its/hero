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

from fastapi import Depends, HTTPException, status

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
    DRAFT_PUBLIKASI = "DRAFT_PUBLIKASI"


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
# 5. Siapa yang boleh menyetujui publikasi draft kajian (DRAFT_PUBLIKASI)?
#    (Saat ini: dialokasikan ke Admin KB)
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
        Izin.DRAFT_PUBLIKASI,
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


def punya_izin(user: Optional[Any], izin: Izin) -> bool:
    """Helper untuk memeriksa apakah user aktif memiliki izin tertentu."""
    if not user or not getattr(user, "is_active", False):
        return False
    role_enum = _resolve_role_enum(getattr(user, "role", None))
    if not role_enum:
        return False
    allowed_perms = HAK_AKSES_PERAN.get(role_enum, set())
    return izin in allowed_perms


def check_non_public_access(doc: Any, user: Optional[Any] = None) -> None:
    """
    Memvalidasi akses ke dokumen non-publik.
    - Dokumen draft_kajian: tidak dikenakan pembatasan klasifikasi akses Publik/Non-publik.
    - Dokumen corpus_eksisting: akses non-publik wajib memiliki izin boleh_baca_nonpublik(user).
    """
    from app.models.enums import KlasifikasiAkses, PeranDokumen

    doc_role = getattr(doc, "document_role", None)
    if doc_role == PeranDokumen.draft_kajian or (isinstance(doc_role, str) and doc_role == "draft_kajian"):
        return None

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


def perlu_salah_satu_izin(daftar_izin: list) -> Callable[..., Any]:
    """
    FastAPI dependency factory untuk memvalidasi pengguna memiliki minimal satu dari izin yang ditentukan:
    - auth_enabled=false: kembalikan None dan izinkan akses.
    - auth_enabled=true:
      - tanpa token / token tidak valid: 401
      - akun nonaktif: 401
      - peran tidak punya salah satu izin: 403 {"code": "akses_ditolak"}
    """
    from app.routers.auth import get_current_user

    def secured_dependency(
        user: Optional[Any] = Depends(get_current_user),
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

        if not any(iz in allowed_perms for iz in daftar_izin):
            izin_str = "/".join(iz.value if hasattr(iz, "value") else str(iz) for iz in daftar_izin)
            role_str = str(role) if role is not None else ""
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "akses_ditolak",
                    "izin": izin_str,
                    "peran": role_str,
                    "message": f"Akun Anda tidak memiliki izin ({izin_str}) untuk aksi ini.",
                },
            )

        return user

    return secured_dependency


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

    def secured_dependency(
        user: Optional[Any] = Depends(get_current_user),
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
            izin_str = izin.value if hasattr(izin, "value") else str(izin)
            role_str = str(role) if role is not None else ""
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail={
                    "code": "akses_ditolak",
                    "izin": izin_str,
                    "peran": role_str,
                    "message": f"Akun Anda tidak memiliki izin {izin_str} untuk aksi ini.",
                },
            )

        return user

    return secured_dependency


def perlu_izin_admin(izin: Izin) -> Callable[..., Any]:
    """
    Dependensi otorisasi untuk endpoint administratif (/users, /audit-logs) (Langkah 34):
    - AUTH_ENABLED=true: sama persis dengan perlu_izin(izin).
    - AUTH_ENABLED=false dan ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=true:
      wajib menyertakan header X-Internal-API-Key yang cocok dengan INTERNAL_API_KEY.
      Tanpa/keliru -> 403 {"code": "butuh_login", "message": "Endpoint ini hanya tersedia saat login aktif (AUTH_ENABLED=true) atau dengan kunci internal."}
    - AUTH_ENABLED=false dan ADMIN_BUTUH_KUNCI_SAAT_AUTH_MATI=false:
      diizinkan tanpa token (perilaku lama).
    """
    import hmac
    from fastapi import Header
    from app.routers.auth import get_current_user

    base_check = perlu_izin(izin)

    def admin_secured_dependency(
        user: Optional[Any] = Depends(get_current_user),
        x_internal_api_key: Optional[str] = Header(None, alias="X-Internal-API-Key"),
    ) -> Optional[Any]:
        if settings.auth_enabled:
            return base_check(user=user)

        if settings.admin_butuh_kunci_saat_auth_mati:
            key = settings.internal_api_key or ""
            if not x_internal_api_key or not key or not hmac.compare_digest(x_internal_api_key, key):
                raise HTTPException(
                    status_code=status.HTTP_403_FORBIDDEN,
                    detail={
                        "code": "butuh_login",
                        "message": "Endpoint ini hanya tersedia saat login aktif (AUTH_ENABLED=true) atau dengan kunci internal.",
                    },
                )
            return None

        return None

    return admin_secured_dependency
