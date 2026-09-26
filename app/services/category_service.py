"""
app/services/category_service.py
Layanan manajemen hierarki kategori/folder Knowledge Base dan resolusi path otomatis.
"""
from dataclasses import dataclass
import re
from typing import Optional, List, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func
from fastapi import HTTPException, status

from app.config import settings
from app.models.category import Category
from app.models.document import Document
from app.models.enums import PeranDokumen
from app.services.naming_service import (
    NamingInput,
    normalize_regulation_type,
    extract_year,
)
from app.services.audit_service import record_audit, CREATE_CATEGORY


def sanitize_segment_name(name: str) -> str:
    """Bersihkan nama segmen folder/kategori dari karakter terlarang."""
    # Hapus karakter terlarang Windows/Linux: / \ : * ? " < > |
    cleaned = re.sub(r'[/\\:*?"<>|]', "", name)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned[:100] if cleaned else "Lainnya"


class CategoryService:
    def __init__(self, db: Session):
        self.db = db

    def resolve_or_create_path(self, segments: List[str]) -> Category:
        """
        Menemukan atau membuat hierarki kategori secara rekursif dari list segmen nama.
        Idempoten dan aman terhadap race condition konkuren.
        """
        if not segments:
            # Fallback ke root Lainnya
            segments = [settings.category_unknown_type]

        curr_parent_id: Optional[int] = None
        curr_category: Optional[Category] = None

        for raw_seg in segments:
            seg = sanitize_segment_name(raw_seg)
            if not seg:
                continue

            # 1. Cari kategori yang sudah ada
            filter_cond = (
                (Category.parent_id == curr_parent_id)
                if curr_parent_id is not None
                else Category.parent_id.is_(None)
            )
            cat = (
                self.db.query(Category)
                .filter(filter_cond, Category.name == seg)
                .first()
            )

            # 2. Jika belum ada, buat baru dengan savepoint aman race condition
            if not cat:
                try:
                    with self.db.begin_nested():
                        new_cat = Category(
                            name=seg,
                            parent_id=curr_parent_id,
                            auto_created=True,
                        )
                        self.db.add(new_cat)
                        self.db.flush()
                        cat = new_cat
                except IntegrityError:
                    # Konflik karena dibuat paralel oleh transaksi lain
                    cat = (
                        self.db.query(Category)
                        .filter(filter_cond, Category.name == seg)
                        .first()
                    )

            if cat:
                curr_parent_id = cat.id
                curr_category = cat

        return curr_category

    def path_of(self, category: Category) -> List[str]:
        """
        Mengembalikan urutan nama kategori dari root hingga kategori leaf saat ini.
        """
        if not category:
            return []

        segments = [category.name]
        curr = category
        while curr.parent_id is not None:
            parent = (
                self.db.query(Category)
                .filter(Category.id == curr.parent_id)
                .first()
            )
            if not parent:
                break
            segments.append(parent.name)
            curr = parent

        segments.reverse()
        return segments

    def category_segments_for(self, doc: Document) -> List[str]:
        """
        Menentukan daftar segmen kategori berdasarkan metadata dokumen.
        - Jika draft_kajian -> [draft_category_root, <tahun atau category_unknown_year>]
        - Selain itu -> isi category_path_template
        """
        inp = NamingInput(
            regulation_number=doc.regulation_number,
            title=doc.title,
            regulation_type=doc.regulation_type,
            release_date=doc.release_date,
        )
        year = extract_year(inp)
        year_str = str(year) if year is not None else settings.category_unknown_year

        if doc.document_role == PeranDokumen.draft_kajian:
            return [settings.draft_category_root, year_str]

        norm_type = normalize_regulation_type(doc.regulation_type) or settings.category_unknown_type

        formatted = settings.category_path_template.format(
            jenis=norm_type,
            tahun=year_str,
        )
        raw_segs = [s.strip() for s in formatted.replace("\\", "/").split("/") if s.strip()]
        return [sanitize_segment_name(s) for s in raw_segs if s]

    def tree(self) -> List[Dict[str, Any]]:
        """
        Membangun seluruh pohon kategori bertingkat dengan jumlah dokumen
        langsung (document_count) dan total turunan (total_document_count)
        dalam agregasi tunggal efisien tanpa N+1 query.
        """
        # 1. Ambil hitungan dokumen per category_id
        doc_counts_query = (
            self.db.query(Document.category_id, func.count(Document.id).label("count"))
            .filter(Document.category_id.isnot(None))
            .group_by(Document.category_id)
            .all()
        )
        doc_counts: Dict[int, int] = {cat_id: cnt for cat_id, cnt in doc_counts_query}

        # 2. Ambil seluruh kategori
        all_categories = self.db.query(Category).order_by(Category.name.asc()).all()

        # 3. Kelompokkan berdasarkan parent_id
        children_map: Dict[Optional[int], List[Category]] = {}
        for cat in all_categories:
            children_map.setdefault(cat.parent_id, []).append(cat)

        # 4. Fungsi rekursif untuk membangun pohon dan menghitung total_document_count
        def build_node(cat: Category) -> Dict[str, Any]:
            direct_count = doc_counts.get(cat.id, 0)
            child_objs = children_map.get(cat.id, [])
            child_nodes = [build_node(c) for c in child_objs]
            total_count = direct_count + sum(cn["total_document_count"] for cn in child_nodes)

            return {
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "auto_created": cat.auto_created,
                "document_count": direct_count,
                "total_document_count": total_count,
                "children": child_nodes,
            }

        root_cats = children_map.get(None, [])
        return [build_node(rc) for rc in root_cats]

    def create(
        self,
        name: str,
        parent_id: Optional[int] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> Category:
        """
        Membuat kategori baru dengan validasi induk dan nama unik di bawah induk yang sama.
        """
        clean_name = sanitize_segment_name(name)
        if not clean_name:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Nama kategori tidak valid.",
            )

        if parent_id is not None:
            parent = self.db.query(Category).filter(Category.id == parent_id).first()
            if not parent:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail=f"Kategori induk dengan ID {parent_id} tidak ditemukan.",
                )

        # Cek duplikat
        filter_cond = (
            (Category.parent_id == parent_id)
            if parent_id is not None
            else Category.parent_id.is_(None)
        )
        existing = (
            self.db.query(Category)
            .filter(filter_cond, Category.name == clean_name)
            .first()
        )
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Kategori dengan nama '{clean_name}' sudah ada di bawah induk yang sama.",
            )

        cat = Category(
            name=clean_name,
            parent_id=parent_id,
            auto_created=False,
        )
        self.db.add(cat)
        self.db.flush()

        record_audit(
            self.db,
            action=CREATE_CATEGORY,
            user_id=actor_user_id,
            target_resource=f"category:{cat.id}",
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(cat)
        return cat
