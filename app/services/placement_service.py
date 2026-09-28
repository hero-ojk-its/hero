"""
app/services/placement_service.py
Layanan penempatan berkas ke hierarki folder KB (kb/<kategori>/<nama baku>.pdf).
"""
from dataclasses import dataclass
import logging
from pathlib import Path
from typing import Optional, List
from sqlalchemy.orm import Session

from app.config import settings
from app.models.category import Category
from app.models.document import Document
from app.services.storage_service import StorageService, get_storage_service
from app.services.category_service import CategoryService
from app.services.naming_service import (
    NamingInput,
    build_standard_filename,
    is_metadata_sufficient,
)
from app.services.audit_service import record_audit, PLACE_DOCUMENT

logger = logging.getLogger("hero")


@dataclass
class PlacementResult:
    document_id: int
    placed: bool
    reason: str  # "ditempatkan" | "metadata_belum_cukup" | "sudah_ditempatkan" | "gagal: ..."
    old_path: Optional[str]
    new_path: Optional[str]
    category_id: Optional[int]
    category_path: Optional[List[str]]


class PlacementService:
    def __init__(
        self,
        db: Session,
        storage: StorageService,
        categories: CategoryService,
        app_settings=settings,
    ):
        self.db = db
        self.storage = storage
        self.categories = categories
        self.settings = app_settings

    def place(
        self,
        doc: Document,
        *,
        force: bool = False,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> PlacementResult:
        """
        Menempatkan dokumen ke folder kategori KB dengan nama baku jika metadata mencukupi.
        """
        inp = NamingInput(
            regulation_number=doc.regulation_number,
            title=doc.title,
            regulation_type=doc.regulation_type,
            release_date=doc.release_date,
        )

        # 1. Cek kelengkapan metadata
        if not is_metadata_sufficient(inp):
            cat = (
                self.db.query(Category).filter(Category.id == doc.category_id).first()
                if doc.category_id
                else None
            )
            cat_path = self.categories.path_of(cat) if cat else None
            return PlacementResult(
                document_id=doc.id,
                placed=False,
                reason="metadata_belum_cukup",
                old_path=doc.file_path_pdf,
                new_path=None,
                category_id=doc.category_id,
                category_path=cat_path,
            )

        # 2. Cek apakah sudah berada di bawah kb/
        is_in_kb = doc.file_path_pdf and doc.file_path_pdf.replace("\\", "/").startswith("kb/")
        if is_in_kb and not force:
            cat = (
                self.db.query(Category).filter(Category.id == doc.category_id).first()
                if doc.category_id
                else None
            )
            cat_path = self.categories.path_of(cat) if cat else None
            return PlacementResult(
                document_id=doc.id,
                placed=True,
                reason="sudah_ditempatkan",
                old_path=doc.file_path_pdf,
                new_path=doc.file_path_pdf,
                category_id=doc.category_id,
                category_path=cat_path,
            )

        # 3. Tentukan kategori tujuan
        target_cat = None
        if doc.category_id is not None:
            target_cat = self.db.query(Category).filter(Category.id == doc.category_id).first()
            if target_cat:
                cat_segments = self.categories.path_of(target_cat)
            else:
                cat_segments = self.categories.category_segments_for(doc)
                target_cat = self.categories.resolve_or_create_path(cat_segments)
        else:
            cat_segments = self.categories.category_segments_for(doc)
            target_cat = self.categories.resolve_or_create_path(cat_segments)

        # 4. Hitung nama baku
        cfg = self.settings or settings
        std_filename = build_standard_filename(
            inp,
            template=getattr(cfg, "naming_template", None) or "{nomor} {judul} {tahun}",
            wildcard=getattr(cfg, "naming_wildcard", None) or "NA",
            max_length=getattr(cfg, "naming_max_length", None) or 150,
        )

        old_path = doc.file_path_pdf
        subdir = "kb/" + "/".join(cat_segments)
        new_path = None

        try:
            # 5. Pindahkan berkas fisik
            new_path = self.storage.move(
                rel_src=old_path,
                subdir=subdir,
                filename_hint=std_filename,
            )

            # 6. Update atribut dokumen
            doc.file_path_pdf = new_path
            doc.standardized_filename = Path(new_path).name
            if target_cat:
                doc.category_id = target_cat.id

            record_audit(
                self.db,
                action=PLACE_DOCUMENT,
                user_id=actor_user_id,
                target_resource=f"document:{doc.id}",
                ip_address=ip_address,
                commit=False,
            )

            self.db.commit()
            self.db.refresh(doc)

            final_cat = (
                self.db.query(Category).filter(Category.id == doc.category_id).first()
                if doc.category_id
                else None
            )
            final_cat_path = self.categories.path_of(final_cat) if final_cat else cat_segments

            return PlacementResult(
                document_id=doc.id,
                placed=True,
                reason="ditempatkan",
                old_path=old_path,
                new_path=new_path,
                category_id=doc.category_id,
                category_path=final_cat_path,
            )

        except Exception as exc:
            self.db.rollback()
            logger.exception("Gagal menempatkan dokumen ID %s: %s", doc.id, exc)

            # Rollback fisik jika berkas sudah sempat dipindah
            if new_path and self.storage.exists(new_path) and old_path != new_path:
                try:
                    old_parent = str(Path(old_path).parent).replace("\\", "/")
                    old_hint = Path(old_path).name
                    self.storage.move(new_path, subdir=old_parent, filename_hint=old_hint)
                except Exception as rb_exc:
                    logger.exception(
                        "Gagal mengembalikan berkas dokumen ID %s ke old_path '%s': %s",
                        doc.id,
                        old_path,
                        rb_exc,
                    )

            return PlacementResult(
                document_id=doc.id,
                placed=False,
                reason=f"gagal: {str(exc)}",
                old_path=old_path,
                new_path=None,
                category_id=doc.category_id,
                category_path=None,
            )

    def place_pending(
        self,
        limit: int = 100,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> List[PlacementResult]:
        """
        Menempatkan seluruh dokumen yang belum berada di folder kb/.
        """
        clamped_limit = max(1, min(limit, 500))
        # Cari dokumen yang file_path_pdf tidak berawalan 'kb/'
        docs = (
            self.db.query(Document)
            .filter(~Document.file_path_pdf.startswith("kb/"))
            .order_by(Document.id.asc())
            .limit(clamped_limit)
            .all()
        )

        results: List[PlacementResult] = []
        for doc in docs:
            res = self.place(doc, actor_user_id=actor_user_id, ip_address=ip_address)
            results.append(res)

        return results
