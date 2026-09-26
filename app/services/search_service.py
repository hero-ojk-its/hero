"""
app/services/search_service.py
Layanan pencarian dokumen Knowledge Base (Langkah 4).
Mendukung full-text search PostgreSQL tsvector/tsquery, pencarian frasa, websearch,
normalisasi nomor regulasi trigram, filter multi-dimensi, dan snippet highlight.
"""
import enum
import re
from dataclasses import dataclass
from datetime import date
from typing import Optional, List, Dict, Any, Tuple
from sqlalchemy import func, or_, and_, desc, asc, literal_column, case
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.category import Category
from app.models.enums import (
    KlasifikasiAkses,
    PeranDokumen,
    StatusKeberlakuan,
    StatusPemrosesan,
)
from app.services.naming_service import normalize_regulation_type


def build_regulation_number_ilike_pattern(raw_num: str) -> str:
    r"""
    Membangun pola ILIKE dengan wildcard '_' untuk pemisah nomor regulasi.
    1. Rapikan spasi di sekitar pemisah (/, \, -)
    2. Escape % dan _ asli milik pengguna
    3. Ganti setiap karakter pemisah (/, \, -, spasi) dengan wildcard satu karakter _
    4. Bungkus dengan %...%
    """
    s = raw_num.strip()
    # 1. Rapikan spasi di sekitar pemisah /, \, -
    s = re.sub(r'\s*([/\\\-])\s*', r'\1', s)
    # 2. Escape % dan _ asli milik pengguna
    s = s.replace('%', r'\%').replace('_', r'\_')
    # 3. Ganti karakter pemisah /, \, -, spasi dengan wildcard satu karakter _
    s = re.sub(r'[/\\\-\s]+', '_', s)
    return f"%{s}%"


class SearchMode(str, enum.Enum):
    phrase = "phrase"   # DEFAULT — phraseto_tsquery: kata-kata harus berurutan & bersebelahan
    all = "all"         # plainto_tsquery: semua kata ada, urutan bebas
    web = "web"         # websearch_to_tsquery: dukung "kutip", OR, -kecuali


class SearchSort(str, enum.Enum):
    relevance = "relevance"                  # default bila q terisi
    release_date_desc = "release_date_desc"  # default bila q kosong
    release_date_asc = "release_date_asc"
    created_desc = "created_desc"
    title_asc = "title_asc"


@dataclass
class SearchParams:
    q: Optional[str] = None
    mode: SearchMode = SearchMode.phrase
    regulation_number: Optional[str] = None
    regulation_type: Optional[str] = None
    category_id: Optional[int] = None
    include_subcategories: bool = True
    status_keberlakuan: Optional[List[StatusKeberlakuan]] = None
    document_role: Optional[PeranDokumen] = None
    access_classification: Optional[KlasifikasiAkses] = None
    processing_status: Optional[StatusPemrosesan] = None
    date_from: Optional[date] = None
    date_to: Optional[date] = None
    year: Optional[int] = None
    sort: Optional[SearchSort] = None
    skip: int = 0
    limit: int = 20


class SearchService:
    def __init__(self, db: Session):
        self.db = db

    def _get_category_descendants(self, root_cat_id: int) -> List[int]:
        """Mengambil ID kategori beserta seluruh turunannya."""
        all_cats = self.db.query(Category.id, Category.parent_id).all()
        children_map: Dict[Optional[int], List[int]] = {}
        for cid, pid in all_cats:
            children_map.setdefault(pid, []).append(cid)

        results = []
        queue = [root_cat_id]
        while queue:
            curr = queue.pop(0)
            results.append(curr)
            for ch in children_map.get(curr, []):
                queue.append(ch)
        return results

    def _build_category_paths_map(self) -> Dict[int, List[str]]:
        """Membangun peta category_id -> category_path tanpa N+1 query."""
        all_cats = self.db.query(Category.id, Category.name, Category.parent_id).all()
        cat_by_id = {c.id: c for c in all_cats}

        paths_map: Dict[int, List[str]] = {}
        for cid, cat in cat_by_id.items():
            path = []
            curr = cat
            while curr:
                path.append(curr.name)
                curr = cat_by_id.get(curr.parent_id) if curr.parent_id else None
            path.reverse()
            paths_map[cid] = path

        return paths_map

    def search(self, params: SearchParams) -> Tuple[int, List[Dict[str, Any]]]:
        """
        Mengeksekusi pencarian dokumen berdasarkan SearchParams.
        Mengembalikan tuple (total_count, items).
        """
        # 1. Validasi tanggal
        if params.date_from and params.date_to and params.date_from > params.date_to:
            raise ValueError("date_from tidak boleh lebih besar dari date_to")

        # 2. Batasi limit ke 100
        limit = min(max(1, params.limit), 100)
        skip = max(0, params.skip)

        # 3. Proses input q
        q_raw = params.q.strip()[:200] if params.q else ""
        has_text_query = bool(q_raw)

        filters = []
        tsquery_expr = None
        has_reg_boost = False
        reg_bonus_expr = None

        if has_text_query:
            # Periksa apakah query menghasilkan tsquery kosong (misal tanda baca murni seperti '!!!')
            if params.mode == SearchMode.phrase:
                tsquery_fn = func.phraseto_tsquery
            elif params.mode == SearchMode.web:
                tsquery_fn = func.websearch_to_tsquery
            else:
                tsquery_fn = func.plainto_tsquery

            tsquery_expr = tsquery_fn("simple", q_raw)
            tsquery_str = self.db.execute(func.text(tsquery_expr)).scalar() or ""

            # Jika q mengandung digit dan karakter pemisah nomor (/ . - \)
            has_digit = any(c.isdigit() for c in q_raw)
            has_sep = any(c in "/.-\\" for c in q_raw)
            is_reg_pattern = has_digit and has_sep

            if is_reg_pattern:
                pat = build_regulation_number_ilike_pattern(q_raw)
                reg_cond = Document.regulation_number.ilike(pat, escape="\\")
                has_reg_boost = True
                reg_bonus_expr = case((reg_cond, 1.0), else_=0.0)
                if tsquery_str.strip():
                    filters.append(or_(Document.search_vector.op("@@")(tsquery_expr), reg_cond))
                else:
                    filters.append(reg_cond)
            else:
                if not tsquery_str.strip():
                    # Query teks murni tanda baca -> kembalikan hasil kosong total 0
                    return 0, []
                filters.append(Document.search_vector.op("@@")(tsquery_expr))

        # 4. Filter nomor regulasi
        if params.regulation_number and params.regulation_number.strip():
            pat = build_regulation_number_ilike_pattern(params.regulation_number)
            filters.append(Document.regulation_number.ilike(pat, escape="\\"))

        # 5. Filter jenis regulasi
        if params.regulation_type and params.regulation_type.strip():
            norm_type = normalize_regulation_type(params.regulation_type)
            if norm_type:
                filters.append(Document.regulation_type == norm_type)

        # 6. Filter kategori
        if params.category_id is not None:
            if params.include_subcategories:
                cat_ids = self._get_category_descendants(params.category_id)
                filters.append(Document.category_id.in_(cat_ids))
            else:
                filters.append(Document.category_id == params.category_id)

        # 7. Filter status keberlakuan
        if params.status_keberlakuan:
            filters.append(Document.status_keberlakuan.in_(params.status_keberlakuan))

        # 8. Filter peran dokumen & klasifikasi akses & processing_status
        if params.document_role is not None:
            filters.append(Document.document_role == params.document_role)
        if params.access_classification is not None:
            filters.append(Document.access_classification == params.access_classification)
        if params.processing_status is not None:
            filters.append(Document.processing_status == params.processing_status)

        # 9. Filter tanggal & tahun
        if params.date_from:
            filters.append(Document.release_date >= params.date_from)
        if params.date_to:
            filters.append(Document.release_date <= params.date_to)
        if params.year is not None:
            filters.append(func.extract("year", Document.release_date) == params.year)

        # 10. Tentukan Pengurutan (Sort)
        effective_sort = params.sort
        if effective_sort is None:
            effective_sort = SearchSort.relevance if has_text_query else SearchSort.release_date_desc

        order_by_clauses = []
        rank_expr = None
        if has_text_query and effective_sort == SearchSort.relevance:
            base_rank = func.ts_rank_cd(Document.search_vector, tsquery_expr) if tsquery_expr is not None else literal_column("0.0")
            if has_reg_boost and reg_bonus_expr is not None:
                rank_expr = base_rank + reg_bonus_expr
            else:
                rank_expr = base_rank

            order_by_clauses.extend([
                desc(rank_expr),
                Document.release_date.desc().nulls_last(),
                Document.id.desc(),
            ])
        elif effective_sort == SearchSort.release_date_desc:
            order_by_clauses.extend([
                Document.release_date.desc().nulls_last(),
                Document.id.desc(),
            ])
        elif effective_sort == SearchSort.release_date_asc:
            order_by_clauses.extend([
                Document.release_date.asc().nulls_last(),
                Document.id.asc(),
            ])
        elif effective_sort == SearchSort.created_desc:
            order_by_clauses.extend([
                Document.created_at.desc().nulls_last(),
                Document.id.desc(),
            ])
        elif effective_sort == SearchSort.title_asc:
            order_by_clauses.extend([
                Document.title.asc(),
                Document.id.asc(),
            ])
        else:
            order_by_clauses.append(Document.id.desc())

        # 11. Query Count
        count_query = self.db.query(func.count(Document.id))
        if filters:
            count_query = count_query.filter(and_(*filters))
        total_count = count_query.scalar() or 0

        if total_count == 0:
            return 0, []

        # 12. Query Data dengan pagination
        # Buat kolom rank dan highlight jika q ada
        select_cols = [Document]
        if has_text_query and tsquery_expr is not None:
            if rank_expr is None:
                rank_expr = func.ts_rank_cd(Document.search_vector, tsquery_expr)
            highlight_expr = func.ts_headline(
                literal_column("'simple'"),
                func.coalesce(func.left(Document.full_text, 50000), Document.title),
                tsquery_expr,
                "StartSel=<mark>,StopSel=</mark>,MaxFragments=2,MaxWords=25,MinWords=10",
            )
            select_cols.extend([rank_expr.label("rank"), highlight_expr.label("highlight")])

        data_query = self.db.query(*select_cols)
        if filters:
            data_query = data_query.filter(and_(*filters))
        data_query = data_query.order_by(*order_by_clauses).offset(skip).limit(limit)

        rows = data_query.all()

        # 13. Resolusi category_path secara efisien
        cat_paths = self._build_category_paths_map()

        items = []
        for row in rows:
            if has_text_query and tsquery_expr is not None:
                doc_obj, rank_val, highlight_val = row[0], float(row[1]) if row[1] is not None else None, row[2]
            else:
                doc_obj, rank_val, highlight_val = (row[0] if isinstance(row, (tuple, list)) else row), None, None

            cpath = cat_paths.get(doc_obj.category_id, []) if doc_obj.category_id else []
            is_placed = bool(doc_obj.file_path_pdf and doc_obj.file_path_pdf.replace("\\", "/").startswith("kb/"))

            items.append({
                "id": doc_obj.id,
                "title": doc_obj.title,
                "regulation_number": doc_obj.regulation_number,
                "regulation_type": doc_obj.regulation_type,
                "release_date": doc_obj.release_date,
                "access_classification": doc_obj.access_classification,
                "document_role": doc_obj.document_role,
                "category_id": doc_obj.category_id,
                "category_path": cpath,
                "status_keberlakuan": doc_obj.status_keberlakuan,
                "processing_status": doc_obj.processing_status,
                "extraction_method": getattr(doc_obj, "extraction_method", None),
                "file_path_pdf": doc_obj.file_path_pdf,
                "file_hash": doc_obj.file_hash,
                "file_size_bytes": doc_obj.file_size_bytes,
                "standardized_filename": doc_obj.standardized_filename,
                "source_url": doc_obj.source_url,
                "is_placed": is_placed,
                "pdf_url": f"/api/v1/documents/{doc_obj.id}/pdf",
                "rank": rank_val,
                "highlight": highlight_val,
                "created_at": doc_obj.created_at,
                "updated_at": doc_obj.updated_at,
            })

        return total_count, items
