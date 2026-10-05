"""
app/routers/naming.py
Router: /api/v1/naming
Endpoint pembangun dan pratinjau penamaan berkas dinamis (US-20c).
"""
from datetime import date
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.config import settings
from app.database import get_db
from app.models.document import Document
from app.schemas.naming import (
    NamingComponentsResponse,
    NamingComponentItem,
    NamingPreviewRequest,
    NamingPreviewResponse,
)
from app.services.naming_service import (
    VALID_NAMING_COMPONENTS,
    COMPONENT_ORDER_UI,
    COMPONENT_LABELS,
    ALLOWED_SEPARATORS,
    DEFAULT_NAMING_FORMAT,
    DEFAULT_NAMING_SEPARATOR,
    DEFAULT_WILDCARD,
    MAX_COMPONENTS,
    NamingInput,
    build_standard_filename,
    validate_naming_format,
    validate_naming_separator,
    extract_year,
    normalize_regulation_type,
)

router = APIRouter(prefix="/api/v1/naming", tags=["Naming"])

DEFAULT_SAMPLE_TITLE = "Penyelenggaraan Bursa Mineral dan Komoditas Strategis"
DEFAULT_SAMPLE_REG_NUMBER = "16/POJK.04/2026"
DEFAULT_SAMPLE_REG_TYPE = "POJK"
DEFAULT_SAMPLE_RELEASE_DATE = date(2026, 1, 1)
DEFAULT_SAMPLE_BIDANG = "BMKS"


@router.get(
    "/components",
    response_model=NamingComponentsResponse,
    summary="Daftar komponen pembangun nama berkas",
)
def get_naming_components() -> NamingComponentsResponse:
    """
    [US-20c] Mengembalikan daftar komponen yang tersedia untuk pembentukan nama berkas dinamis,
    beserta opsi pemisah, wildcard, format default, dan batas maksimal komponen.
    Urutan komponen disesuaikan dengan tata letak tombol di antarmuka pengguna (UI):
    Nama, Tahun, Jenis, Bidang, Nomor.
    """
    items = [
        NamingComponentItem(key=k, label=COMPONENT_LABELS[k])
        for k in COMPONENT_ORDER_UI
    ]
    return NamingComponentsResponse(
        components=items,
        separators=list(ALLOWED_SEPARATORS),
        wildcard=settings.naming_wildcard or DEFAULT_WILDCARD,
        default_format=list(DEFAULT_NAMING_FORMAT),
        max_components=MAX_COMPONENTS,
    )


@router.post(
    "/preview",
    response_model=NamingPreviewResponse,
    summary="Pratinjau standardisasi nama berkas",
)
def preview_naming(
    payload: NamingPreviewRequest,
    db: Session = Depends(get_db),
) -> NamingPreviewResponse:
    """
    [US-20c] Menghasilkan pratinjau nama berkas PDF baku berdasarkan format urutan komponen pilihan,
    pemisah, dan data metadata dokumen (dari DB, payload sampel, atau sampel bawaan sistem).
    """
    format_list = validate_naming_format(payload.naming_format)
    sep = validate_naming_separator(payload.naming_separator)

    title: Optional[str] = None
    reg_number: Optional[str] = None
    reg_type: Optional[str] = None
    rel_date: Optional[date] = None
    reg_year: Optional[int] = None
    bidang: Optional[str] = None
    orig_filename: Optional[str] = None

    if payload.document_id is not None:
        doc = db.query(Document).filter(Document.id == payload.document_id).first()
        if not doc:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Dokumen dengan ID {payload.document_id} tidak ditemukan.",
            )
        title = doc.title
        reg_number = doc.regulation_number
        reg_type = doc.regulation_type
        rel_date = doc.release_date
        reg_year = getattr(doc, "regulation_year", None)
        bidang = doc.bidang
        orig_filename = doc.original_filename
    elif payload.sample is not None:
        title = payload.sample.title
        reg_number = payload.sample.regulation_number
        reg_type = payload.sample.regulation_type
        rel_date = payload.sample.release_date
        reg_year = getattr(payload.sample, "regulation_year", None)
        bidang = payload.sample.bidang
    else:
        title = DEFAULT_SAMPLE_TITLE
        reg_number = DEFAULT_SAMPLE_REG_NUMBER
        reg_type = DEFAULT_SAMPLE_REG_TYPE
        rel_date = DEFAULT_SAMPLE_RELEASE_DATE
        reg_year = 2026
        bidang = DEFAULT_SAMPLE_BIDANG

    inp = NamingInput(
        regulation_number=reg_number,
        title=title,
        regulation_type=reg_type,
        release_date=rel_date,
        bidang=bidang,
        original_filename=orig_filename,
        regulation_year=reg_year,
    )

    filename = build_standard_filename(
        inp,
        naming_format=format_list,
        naming_separator=sep,
        wildcard=settings.naming_wildcard or DEFAULT_WILDCARD,
        max_length=settings.naming_max_length or 150,
    )

    # Deteksi missing components
    missing: List[str] = []
    for comp in format_list:
        is_missing = False
        if comp == "nama":
            is_missing = not (title and title.strip()) and not (orig_filename and orig_filename.strip())
        elif comp == "nomor":
            is_missing = not (reg_number and reg_number.strip())
        elif comp == "tahun":
            is_missing = extract_year(inp) is None
        elif comp == "jenis":
            is_missing = normalize_regulation_type(reg_type) is None
        elif comp == "bidang":
            is_missing = not (bidang and bidang.strip())

        if is_missing and comp not in missing:
            missing.append(comp)

    return NamingPreviewResponse(
        filename=filename,
        missing_components=missing,
    )
