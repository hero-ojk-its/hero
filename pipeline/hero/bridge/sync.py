"""Cermin korpus backend → katalog HERO, agar mesin analisa bekerja di atas
data yang sama dengan yang dilihat frontend.

**Kenapa dicermin, bukan dibaca langsung?** Harmonisasi (URD 3.4) tidak
membandingkan dua dokumen; ia membandingkan **setiap pasal draft terhadap
setiap pasal korpus**, lalu menanyakan status hukum tiap pembanding ke graf
relasi dan mencari calon pembanding di register yang belum terunduh. Mesin itu
sudah ada, teruji (``tests/test_harmonisasi.py``), dan terkalibrasi terhadap
14 pasangan peraturan perubahan — semuanya di atas katalog SQLite. Mencerminkan
korpus satu kali jauh lebih murah dan lebih aman daripada menulis ulang mesin
harmonisasi, vektor, graf, dan mutu data untuk dua jenis basis data.

Isi cermin adalah **data turunan**: boleh dihapus kapan saja dan dibangun ulang
dengan ``hero bridge sinkron``. Sumber kebenaran tetap Postgres backend.

Satu PDF yang masuk dua kali — lewat backend *dan* lewat ``hero scrape`` —
punya SHA-256 yang sama, jadi di katalog ia tetap satu baris; ``doc_map`` di
buku besar jembatan menjaga kedua identitasnya tetap tersambung.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Sequence

from hero.bridge import mapping, pg
from hero.bridge.state import BridgeState, default_path
from hero.config import Settings
from hero.kb.catalog import Catalog
from hero.models import IngestRecord, RegulationMetadata

log = logging.getLogger("hero.bridge.sync")

# processing_status backend yang layak masuk korpus. 'diterima'/'diproses'
# belum punya teks; 'gagal'/'ditolak' tidak punya isi yang bisa dibandingkan.
SYNCABLE = ("terindeks", "perlu_koreksi")

# status_keberlakuan backend → reg_status katalog HERO. Draft (document_role
# = draft_kajian) selalu menjadi 'rancangan' apa pun status keberlakuannya,
# karena ADR-03 mengeluarkan rancangan dari korpus pembanding.
REG_STATUS = {"berlaku": "berlaku", "diubah": "diubah", "dicabut": "dicabut",
              "tidak_diketahui": "unknown"}


@dataclass
class SyncReport:
    dokumen: int = 0
    pasal: int = 0
    dilewati_tanpa_teks: int = 0
    dilewati_tanpa_pasal: int = 0
    draft: int = 0
    halaman_terisi: int = 0
    halaman_kosong: int = 0
    detik: float = 0.0
    galat: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"dokumen": self.dokumen, "pasal": self.pasal, "draft": self.draft,
                "dilewati_tanpa_teks": self.dilewati_tanpa_teks,
                "dilewati_tanpa_pasal": self.dilewati_tanpa_pasal,
                "halaman_pasal_terisi": self.halaman_terisi,
                "halaman_pasal_kosong": self.halaman_kosong,
                "detik": round(self.detik, 1), "galat": self.galat[:10]}


DOC_SQL = """
SELECT d.id, d.title, d.regulation_number, d.regulation_type, d.regulation_year,
       d.release_date, d.bidang, d.status_keberlakuan, d.document_role,
       d.access_classification, d.processing_status, d.file_hash, d.file_size_bytes,
       d.original_filename, d.standardized_filename, d.file_path_pdf, d.source_url,
       d.extraction_method, d.extraction_engine, d.full_text, d.created_at
FROM documents d
WHERE d.processing_status = ANY(%s)
{extra}
ORDER BY d.id
{limit}
"""

ART_SQL = """
SELECT a.document_id, a.article_number, a.chapter_title, a.content_text, a.order_index, a.level
FROM articles a
WHERE a.document_id = ANY(%s) AND a.level = 'pasal'
ORDER BY a.document_id, COALESCE(a.order_index, a.id), a.id
"""


def _iso(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date().isoformat()
    return str(value)[:10] or None


def _record(row: dict[str, Any], doc_id: str,
            local_md: dict[str, Any] | None = None) -> IngestRecord:
    """Baris backend → IngestRecord katalog.

    Nilai yang **dimiliki backend** (judul, nomor, jenis, tanggal, status)
    selalu menang — pengguna bisa mengoreksinya manual di UI dan koreksi itu
    tidak boleh ditimpa. Nilai yang **tidak punya tempat di skema backend**
    (dasar hukum, penerbit) diambil dari catatan ekstraksi lokal.
    """
    local_md = local_md or {}
    is_draft = (row.get("document_role") or "") == "draft_kajian"
    reg_status = "rancangan" if is_draft else REG_STATUS.get(
        row.get("status_keberlakuan") or "", "unknown")
    if reg_status == "unknown" and local_md.get("status") in ("berlaku", "diubah", "dicabut"):
        reg_status = local_md["status"]        # terbaca dari teks dokumen
    md = RegulationMetadata(
        title=row.get("title"),
        subject=row.get("title"),          # judul backend adalah perihal ("tentang …")
        doc_type=row.get("regulation_type") or local_md.get("doc_type"),
        number=row.get("regulation_number") or local_md.get("number"),
        year=row.get("regulation_year") or local_md.get("year"),
        issuing_body=local_md.get("issuing_body"),
        legal_basis=list(local_md.get("legal_basis") or []),
        status=reg_status,
        confidence=float(local_md.get("confidence") or 0.0),
    )
    md.issued_date = _parse_date(row.get("release_date")) or _parse_date(local_md.get("issued_date"))
    return IngestRecord(
        doc_id=doc_id,
        sha256=row["file_hash"],
        source_type="backend",
        source_name="hero-backend",
        source_ref=row.get("source_url") or f"backend:document/{row['id']}",
        original_filename=row.get("original_filename") or row.get("standardized_filename")
        or f"dokumen-{row['id']}.pdf",
        stored_path=row.get("file_path_pdf"),
        category=row.get("bidang"),
        size_bytes=int(row.get("file_size_bytes") or 0),
        is_scanned=(row.get("extraction_method") or "") == "ocr",
        status="ingested",
        reason=f"cermin backend (processing_status={row.get('processing_status')})",
        metadata=md,
    )


def _parse_date(value: Any):
    from datetime import date

    if value is None or isinstance(value, date):
        return value if isinstance(value, date) else None
    try:
        return date.fromisoformat(str(value)[:10])
    except ValueError:
        return None


def mirror(settings: Settings, *, dsn: str | None = None, limit: int | None = None,
           document_ids: Sequence[int] | None = None, include_drafts: bool = True,
           state: BridgeState | None = None,
           progress: Callable[[str], None] | None = None) -> SyncReport:
    """Tarik dokumen + pasal backend ke katalog HERO. Idempoten."""
    say = progress or (lambda m: None)
    rep = SyncReport()
    started = time.perf_counter()
    own_state = state is None
    st = state or BridgeState(default_path(settings))
    conn = pg.connect(dsn)
    try:
        extra = []
        params: list[Any] = [list(SYNCABLE)]
        if document_ids:
            extra.append("AND d.id = ANY(%s)")
            params.append([int(i) for i in document_ids])
        if not include_drafts:
            extra.append("AND d.document_role <> 'draft_kajian'")
        sql = DOC_SQL.format(extra="\n".join(extra),
                             limit=f"LIMIT {int(limit)}" if limit else "")
        with conn.cursor() as cur:
            cur.execute(sql, params)
            cols = [c.name for c in cur.description]
            docs = [dict(zip(cols, r)) for r in cur.fetchall()]
        say(f"{len(docs)} dokumen berstatus {'/'.join(SYNCABLE)} di backend")
        if not docs:
            rep.detik = time.perf_counter() - started
            return rep

        ids = [d["id"] for d in docs]
        with conn.cursor() as cur:
            cur.execute(ART_SQL, (ids,))
            acols = [c.name for c in cur.description]
            arts_by_doc: dict[int, list[dict[str, Any]]] = {}
            for r in cur.fetchall():
                a = dict(zip(acols, r))
                arts_by_doc.setdefault(int(a["document_id"]), []).append(a)
        say(f"{sum(len(v) for v in arts_by_doc.values())} pasal terbaca")

        pages = st.all_pages()
        metas = st.all_metadata()
        with Catalog(settings.catalog_db) as cat:
            for d in docs:
                bid = int(d["id"])
                if not d.get("file_hash"):
                    rep.galat.append(f"dokumen {bid} tanpa file_hash — dilewati")
                    continue
                text = d.get("full_text") or ""
                arts = arts_by_doc.get(bid, [])
                if not text and not arts:
                    rep.dilewati_tanpa_teks += 1
                    continue
                doc_id = f"be-{bid}"
                rec = _record(d, doc_id, metas.get(bid))
                cat.upsert_document(rec)
                # Satu sha256 = satu baris: bila PDF ini sudah ada di katalog
                # dari jalur scraping, doc_id aslinya yang dipakai.
                existing = cat.exists(rec.sha256)
                if existing is not None:
                    doc_id = existing["doc_id"]
                st.map_document(bid, doc_id, rec.sha256)

                page_map = pages.get(bid, {})
                rows = []
                for a in arts:
                    label = str(a.get("article_number") or "").strip()
                    # Katalog HERO menyimpan nomor polos ("4"), backend menyimpan
                    # labelnya ("Pasal 4"). Buku besar halaman memakai label.
                    num = mapping.pasal_number(label)
                    pg_no = page_map.get(label) or page_map.get(num)
                    if pg_no is None:
                        rep.halaman_kosong += 1
                    else:
                        rep.halaman_terisi += 1
                    rows.append({"number": num, "bab": a.get("chapter_title"),
                                 "page": pg_no, "text": a.get("content_text") or ""})
                if rows:
                    cat.save_articles(doc_id, rows)
                else:
                    rep.dilewati_tanpa_pasal += 1
                cat.save_text(doc_id, text, structure={
                    "has_structure": bool(rows), "article_count": len(rows),
                    "bab_count": len({r["bab"] for r in rows if r["bab"]}),
                    "sections": [], "sumber": "cermin-backend"})
                rep.dokumen += 1
                rep.pasal += len(rows)
                if (d.get("document_role") or "") == "draft_kajian":
                    rep.draft += 1
                if rep.dokumen % 50 == 0:
                    say(f"  {rep.dokumen}/{len(docs)} dokumen")
        st.log("sinkron", "backend", rep.as_dict())
    finally:
        conn.close()
        if own_state:
            st.close()
    rep.detik = time.perf_counter() - started
    return rep


def backend_documents(dsn: str | None = None, *, role: str | None = None,
                      limit: int = 50) -> list[dict[str, Any]]:
    """Daftar ringkas dokumen backend — untuk memilih draft di CLI/layar."""
    conn = pg.connect(dsn)
    try:
        where = ["processing_status = ANY(%s)"]
        params: list[Any] = [list(SYNCABLE)]
        if role:
            where.append("document_role = %s")
            params.append(role)
        params.append(int(limit))
        with conn.cursor() as cur:
            cur.execute(f"SELECT id, title, regulation_number, regulation_type, regulation_year, "
                        f"document_role, status_keberlakuan, access_classification, "
                        f"processing_status FROM documents WHERE {' AND '.join(where)} "
                        f"ORDER BY id DESC LIMIT %s", params)
            cols = [c.name for c in cur.description]
            return [dict(zip(cols, r)) for r in cur.fetchall()]
    finally:
        conn.close()
