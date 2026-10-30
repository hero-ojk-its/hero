"""
app/services/category_service.py
Layanan manajemen hierarki kategori/folder Knowledge Base dan resolusi path otomatis.
"""
import json
import re
from typing import Optional, List, Dict, Any, TYPE_CHECKING
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
from app.services.audit_service import (
    record_audit,
    CREATE_CATEGORY,
    UPDATE_CATEGORY,
    DELETE_CATEGORY,
)

if TYPE_CHECKING:
    from app.services.storage_service import StorageService


def validate_classification_rule(raw_rule: Optional[str]) -> Optional[str]:
    """
    Validasi classification_rule:
    - Harus None atau string JSON objek (dict)
    - Maksimal 4.000 karakter
    - Melempar HTTPException(422) bila tidak valid
    """
    if raw_rule is None:
        return None

    if len(raw_rule) > 4000:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="classification_rule tidak boleh melebihi 4.000 karakter.",
        )

    try:
        parsed = json.loads(raw_rule)
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="classification_rule harus berupa format JSON yang valid.",
        )

    if not isinstance(parsed, dict):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail="classification_rule harus berupa objek JSON (dict), bukan array atau skalar.",
        )

    return raw_rule


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
            original_filename=getattr(doc, "original_filename", None),
            regulation_year=getattr(doc, "regulation_year", None),
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
        # 1. Ambil hitungan dokumen per category_id (hanya dokumen aktif)
        doc_counts_query = (
            self.db.query(Document.category_id, func.count(Document.id).label("count"))
            .filter(Document.category_id.isnot(None), Document.is_active == True)  # noqa: E712
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
                "jumlah_dokumen": direct_count,
                "classification_rule": cat.classification_rule,
                "children": child_nodes,
            }

        root_cats = children_map.get(None, [])
        return [build_node(rc) for rc in root_cats]

    def get_subtree_category_ids(self, root_cat_id: int) -> List[int]:
        """Mengembalikan ID kategori root dan seluruh ID keturunan di bawahnya."""
        all_cats = self.db.query(Category.id, Category.parent_id).all()
        children_map: Dict[Optional[int], List[int]] = {}
        for cid, pid in all_cats:
            children_map.setdefault(pid, []).append(cid)

        result: List[int] = []
        queue = [root_cat_id]
        while queue:
            curr = queue.pop(0)
            result.append(curr)
            queue.extend(children_map.get(curr, []))
        return result

    def create(
        self,
        name: str,
        parent_id: Optional[int] = None,
        classification_rule: Optional[str] = None,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> Category:
        """
        Membuat kategori baru dengan validasi induk dan nama unik di bawah induk yang sama.
        """
        if not name or not name.strip():
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                detail="Nama kategori tidak boleh kosong.",
            )

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

        valid_rule = validate_classification_rule(classification_rule)

        cat = Category(
            name=clean_name,
            parent_id=parent_id,
            auto_created=False,
            classification_rule=valid_rule,
        )
        self.db.add(cat)
        self.db.flush()

        record_audit(
            self.db,
            action=CREATE_CATEGORY,
            user_id=actor_user_id,
            target_resource=f"category:{cat.id}",
            detail={"name": clean_name, "parent_id": parent_id, "classification_rule": valid_rule},
            ip_address=ip_address,
            commit=False,
        )

        self.db.commit()
        self.db.refresh(cat)
        return cat

    def update(
        self,
        category_id: int,
        *,
        name: Optional[str] = None,
        name_provided: bool = False,
        parent_id: Optional[int] = None,
        parent_id_provided: bool = False,
        classification_rule: Optional[str] = None,
        classification_rule_provided: bool = False,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
        storage: Optional["StorageService"] = None,
        app_settings=settings,
    ) -> Dict[str, Any]:
        """
        Memperbarui nama, induk (parent_id), dan/atau classification_rule kategori.
        Jika nama atau parent_id berubah, seluruh dokumen di bawah hierarki kategori ini dipindahkan.
        """
        cat = self.db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
            )

        before_state: Dict[str, Any] = {}
        after_state: Dict[str, Any] = {}
        path_changed = False

        target_parent = parent_id if parent_id_provided else cat.parent_id

        # 1. Validasi & penanganan parent_id jika disediakan
        if parent_id_provided:
            if parent_id is not None:
                if parent_id == cat.id:
                    raise HTTPException(
                        status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                        detail="Kategori tidak boleh dipindah ke dalam dirinya sendiri atau turunannya",
                    )
                new_parent = self.db.query(Category).filter(Category.id == parent_id).first()
                if not new_parent:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Kategori induk dengan ID {parent_id} tidak ditemukan.",
                    )
                # Deteksi siklus: telusuri rantai parent dari new_parent ke atas
                curr_check: Optional[Category] = new_parent
                visited = set()
                while curr_check is not None:
                    if curr_check.id == cat.id:
                        raise HTTPException(
                            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                            detail="Kategori tidak boleh dipindah ke dalam dirinya sendiri atau turunannya",
                        )
                    if curr_check.id in visited:
                        break
                    visited.add(curr_check.id)
                    curr_check = (
                        self.db.query(Category).filter(Category.id == curr_check.parent_id).first()
                        if curr_check.parent_id is not None
                        else None
                    )

            if parent_id != cat.parent_id:
                path_changed = True
                before_state["parent_id"] = cat.parent_id
                after_state["parent_id"] = parent_id
                cat.parent_id = parent_id

        # 2. Validasi & penanganan name jika disediakan
        clean_name = None
        if name_provided:
            if not name or not name.strip():
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Nama kategori tidak boleh kosong.",
                )
            clean_name = sanitize_segment_name(name)
            if not clean_name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
                    detail="Nama kategori tidak boleh kosong.",
                )
            if clean_name != cat.name:
                path_changed = True
                before_state["name"] = cat.name
                after_state["name"] = clean_name
                cat.name = clean_name

        # Cek keunikan nama pada target parent
        effective_name = clean_name if (name_provided and clean_name) else cat.name
        filter_cond = (
            (Category.parent_id == target_parent)
            if target_parent is not None
            else Category.parent_id.is_(None)
        )
        existing_dup = (
            self.db.query(Category)
            .filter(filter_cond, Category.name == effective_name, Category.id != cat.id)
            .first()
        )
        if existing_dup:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"Kategori dengan nama '{effective_name}' sudah ada di bawah induk yang sama.",
            )

        # 3. Validasi & penanganan classification_rule jika disediakan
        if classification_rule_provided:
            valid_rule = validate_classification_rule(classification_rule)
            if valid_rule != cat.classification_rule:
                before_state["classification_rule"] = cat.classification_rule
                after_state["classification_rule"] = valid_rule
                cat.classification_rule = valid_rule

        # Setelah diubah oleh pengguna, auto_created otomatis menjadi False
        if cat.auto_created:
            before_state["auto_created"] = True
            after_state["auto_created"] = False
            cat.auto_created = False

        self.db.flush()
        self.db.commit()
        self.db.refresh(cat)

        # 4. Jika nama atau parent berubah, relokasi fisik seluruh dokumen di kategori ini dan subkategorinya
        dokumen_dipindah = 0
        dokumen_gagal: List[Dict[str, Any]] = []

        if path_changed and storage is not None:
            from app.services.placement_service import PlacementService

            place_svc = PlacementService(self.db, storage, self, app_settings)
            subtree_ids = self.get_subtree_category_ids(cat.id)
            docs_to_move = (
                self.db.query(Document)
                .filter(Document.category_id.in_(subtree_ids))
                .all()
            )

            for d in docs_to_move:
                try:
                    res = place_svc.place(
                        d,
                        force=True,
                        keep_category=True,
                        actor_user_id=actor_user_id,
                        ip_address=ip_address,
                    )
                    if res.placed:
                        dokumen_dipindah += 1
                    else:
                        dokumen_gagal.append({
                            "document_id": d.id,
                            "alasan": res.reason or "gagal_penempatan",
                        })
                except Exception as exc:
                    dokumen_gagal.append({
                        "document_id": d.id,
                        "alasan": str(exc),
                    })

        # 5. Catat audit UPDATE_CATEGORY
        record_audit(
            self.db,
            action=UPDATE_CATEGORY,
            user_id=actor_user_id,
            target_resource=f"category:{cat.id}",
            detail={
                "before": before_state,
                "after": after_state,
                "dokumen_dipindah": dokumen_dipindah,
            },
            ip_address=ip_address,
            commit=True,
        )

        cat_path = self.path_of(cat)
        doc_count = (
            self.db.query(Document)
            .filter(Document.category_id == cat.id, Document.is_active == True)  # noqa: E712
            .count()
        )

        return {
            "kategori": {
                "id": cat.id,
                "name": cat.name,
                "parent_id": cat.parent_id,
                "auto_created": cat.auto_created,
                "path": cat_path,
                "document_count": doc_count,
                "jumlah_dokumen": doc_count,
                "classification_rule": cat.classification_rule,
            },
            "dokumen_dipindah": dokumen_dipindah,
            "dokumen_gagal": dokumen_gagal,
        }

    def delete(
        self,
        category_id: int,
        *,
        actor_user_id: Optional[int] = None,
        ip_address: Optional[str] = None,
    ) -> None:
        """
        Menghapus kategori bila tidak memiliki subkategori dan tidak memiliki dokumen.
        Jika masih berisi, melempar 409 Conflict beserta jumlahnya.
        """
        cat = self.db.query(Category).filter(Category.id == category_id).first()
        if not cat:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Kategori dengan ID {category_id} tidak ditemukan.",
            )

        subcat_count = self.db.query(Category).filter(Category.parent_id == category_id).count()
        doc_count = self.db.query(Document).filter(Document.category_id == category_id).count()

        if subcat_count > 0 or doc_count > 0:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail={
                    "subkategori": subcat_count,
                    "dokumen": doc_count,
                    "message": f"Kategori tidak dapat dihapus karena masih memiliki {subcat_count} subkategori dan {doc_count} dokumen.",
                },
            )

        cat_name = cat.name
        cat_parent_id = cat.parent_id

        self.db.delete(cat)
        record_audit(
            self.db,
            action=DELETE_CATEGORY,
            user_id=actor_user_id,
            target_resource=f"category:{category_id}",
            detail={"id": category_id, "name": cat_name, "parent_id": cat_parent_id},
            ip_address=ip_address,
            commit=False,
        )
        self.db.commit()
