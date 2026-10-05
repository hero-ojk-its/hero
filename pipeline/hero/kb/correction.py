"""Penamaan baku + antrian koreksi manual (US-20 #11, US-20a #12, dasar #90).

Alur satu dokumen baru (dipanggil dari ``IngestPipeline.ingest_file``)::

    PDF ──read_identity (halaman 1, OCR bila perlu; tanggal dari penutup)──┐
        └─ isi kekosongan dari metadata dokumen utuh/sumber (JDIH)        ─┤
                                                                          ▼
        unsur wajib lengkap? ── ya ──► nama dari templat ──► folder KB
                              └ tidak ─► data/antrian_koreksi/<doc_id>.pdf + baris 'antrian'

Dokumen di antrian **tetap tercatat di katalog** (tidak dibuang, AC US-20);
setelah petugas melengkapi unsur yang kurang (``resolve``), berkasnya diberi
nama baku dan dipindah ke folder KB yang semestinya.

Tabel ``penamaan`` menyimpan identitas per unsur beserta sumbernya, sehingga
saat templat diganti (#90) semua berkas dapat dinamai ulang tanpa membaca
PDF lagi (``apply_template``).
"""
from __future__ import annotations

import json
import re
import shutil
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any

from hero.extract.firstpage import Element, Identity, read_identity
from hero.inventory import SOURCE_RANCANGAN
from hero.kb.classify import kb_relative_path
from hero.kb.naming import TOKENS, active_template, check_template, render_name, unique_path
from hero.models import RegulationMetadata

QUEUE_DIR = "antrian_koreksi"     # sibling of the KB folder, never inside it (FR-SCR-09b)
IDENTITY_KEYS = ("jenis", "nomor", "tahun", "tanggal", "judul")

SCHEMA = """
CREATE TABLE IF NOT EXISTS penamaan (
    doc_id        TEXT PRIMARY KEY,
    status        TEXT NOT NULL,        -- dinamai | antrian | dikoreksi
    kurang        TEXT,                 -- JSON: unsur wajib yang belum terbaca
    identitas     TEXT,                 -- JSON: Identity.to_dict() (nilai + sumber + cara)
    templat       TEXT,
    nama_berkas   TEXT,
    catatan       TEXT,
    dibuat        TEXT,
    diperbarui    TEXT,
    dikoreksi_oleh TEXT
);
CREATE INDEX IF NOT EXISTS idx_penamaan_status ON penamaan(status);
"""


def ensure_schema(conn) -> None:
    conn.executescript(SCHEMA)


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


def naming_rule(conn, naming, source_key: str | None) -> tuple[str, list[str]]:
    """(template, required elements) for a document from this source."""
    if source_key == SOURCE_RANCANGAN:
        return naming.draft_template, required_for(naming.draft_template, naming.draft_required)
    template = active_template(conn, naming.template)
    return template, required_for(template, naming.required)


def queue_dir(kb: Path) -> Path:
    return Path(kb).parent / QUEUE_DIR


def required_for(template: str, required: list[str] | tuple[str, ...]) -> list[str]:
    """Unsur wajib = yang dikonfigurasi ∪ unsur identitas yang dipakai templat.

    Templat ``{jenis} {nomor_urut} Tahun {tahun}`` tanpa tahun akan menghasilkan
    "POJK 11 Tahun .pdf"; lebih baik dokumen itu dikoreksi daripada salah nama.
    """
    used = set(check_template(template).tokens)
    if "nomor_urut" in used:
        used.add("nomor")
    need = list(dict.fromkeys(list(required) + [k for k in IDENTITY_KEYS if k in used]))
    return need


def missing(ident: Identity, need: list[str]) -> list[str]:
    return [k for k in need if getattr(ident, k).nilai in (None, "")]


def fill_from_metadata(ident: Identity, md: RegulationMetadata) -> None:
    """Fill gaps from the full-document extraction (and source hints such as
    JDIH, already merged into ``md``). Each filled element is labelled so the
    UI can show "diambil dari metadata dokumen, bukan halaman pertama"."""
    pairs = {"jenis": md.doc_type, "nomor": md.number, "tahun": md.year,
             "tanggal": md.issued_date, "judul": md.subject}
    for key, value in pairs.items():
        if getattr(ident, key).nilai in (None, "") and value not in (None, ""):
            setattr(ident, key, Element(value, "metadata-dokumen", "teks"))


def backfill_metadata(md: RegulationMetadata, ident: Identity) -> None:
    """Give the catalog what page 1 knows when the full-text parser missed it."""
    if not md.doc_type and ident.jenis.nilai:
        md.doc_type = ident.jenis.nilai
    if not md.number and ident.nomor.nilai:
        md.number = ident.nomor.nilai
    if not md.year and ident.tahun.nilai:
        md.year = int(ident.tahun.nilai)
    if not md.issued_date and isinstance(ident.tanggal.nilai, date):
        md.issued_date = ident.tanggal.nilai
    if not md.subject and ident.judul.nilai:
        md.subject = ident.judul.nilai


def naming_fields(ident: Identity | dict, *, kategori: str | None, sumber: str | None,
                  status: str | None) -> dict[str, Any]:
    vals = ident.values() if isinstance(ident, Identity) else dict(ident)
    return {**vals, "kategori": kategori, "sumber": sumber, "status": status}


@dataclass
class Placement:
    status: str                 # dinamai | antrian
    target: Path
    nama: str | None
    kurang: list[str]


def place(kb: Path, md: RegulationMetadata, ident: Identity, *, category: str,
          source_key: str, template: str, need: list[str], original_name: str,
          doc_id: str) -> Placement:
    """Decide where a new document goes — before it touches the KB folder."""
    kurang = missing(ident, need)
    if kurang:
        # Outside the KB and named by id: FR-SCR-09b — no file enters the KB
        # under its source name. The original name stays in the catalog.
        return Placement("antrian", queue_dir(kb) / f"{doc_id}.pdf", None, kurang)
    nama = render_name(template, naming_fields(ident, kategori=category, sumber=source_key,
                                               status=md.status))
    folder = (kb / kb_relative_path(md, category, original_name, source_key)).parent
    return Placement("dinamai", folder / nama, nama, [])


def record(conn, doc_id: str, placement: Placement, ident: Identity, template: str,
           *, oleh: str | None = None) -> None:
    ensure_schema(conn)
    now = _now()
    conn.execute(
        "INSERT INTO penamaan (doc_id, status, kurang, identitas, templat, nama_berkas, catatan, "
        "dibuat, diperbarui, dikoreksi_oleh) VALUES (?,?,?,?,?,?,?,?,?,?) "
        "ON CONFLICT(doc_id) DO UPDATE SET status=excluded.status, kurang=excluded.kurang, "
        "identitas=excluded.identitas, templat=excluded.templat, nama_berkas=excluded.nama_berkas, "
        "catatan=excluded.catatan, diperbarui=excluded.diperbarui, "
        "dikoreksi_oleh=COALESCE(excluded.dikoreksi_oleh, penamaan.dikoreksi_oleh)",
        (doc_id, placement.status, json.dumps(placement.kurang), json.dumps(ident.to_dict(), default=str),
         template, placement.nama, "; ".join(ident.catatan) or None, now, now, oleh))
    conn.commit()


# ---------------------------------------------------------------------------
# Queue: list + resolve
# ---------------------------------------------------------------------------
def queue(conn, status: str = "antrian") -> list[dict[str, Any]]:
    ensure_schema(conn)
    rows = conn.execute(
        "SELECT p.*, d.original_filename, d.stored_path, d.source_name, d.category "
        "FROM penamaan p JOIN documents d USING (doc_id) WHERE p.status = ? "
        "ORDER BY p.dibuat", (status,)).fetchall()
    out = []
    for r in rows:
        ident = json.loads(r["identitas"] or "{}")
        out.append({
            "doc_id": r["doc_id"], "berkas_asli": r["original_filename"],
            "lokasi": r["stored_path"], "sumber": r["source_name"],
            "kurang": json.loads(r["kurang"] or "[]"),
            "terbaca": {k: (ident.get(k) or {}).get("nilai") for k in IDENTITY_KEYS},
            "catatan": r["catatan"], "masuk": r["dibuat"],
        })
    return out


def summary(conn) -> dict[str, int]:
    ensure_schema(conn)
    return {r[0]: r[1] for r in conn.execute("SELECT status, COUNT(*) FROM penamaan GROUP BY status")}


def _identity_from_json(raw: str | None) -> Identity:
    ident = Identity()
    data = json.loads(raw or "{}")
    for k in IDENTITY_KEYS:
        el = data.get(k) or {}
        val = el.get("nilai")
        if k == "tanggal" and isinstance(val, str) and val:
            val = date.fromisoformat(val[:10])
        setattr(ident, k, Element(val, el.get("sumber"), el.get("cara")))
    ident.halaman_1_cara = data.get("halaman_1_cara")
    ident.ocr_keyakinan = data.get("ocr_keyakinan")
    return ident


class CorrectionError(ValueError):
    pass


def _validate(koreksi: dict[str, Any]) -> dict[str, Any]:
    clean: dict[str, Any] = {}
    for k, v in koreksi.items():
        if v in (None, ""):
            continue
        if k not in IDENTITY_KEYS:
            raise CorrectionError(f"unsur tidak dikenal: {k}")
        if k == "tanggal":
            try:
                v = date.fromisoformat(str(v)[:10])
            except ValueError as exc:
                raise CorrectionError("tanggal harus berformat YYYY-MM-DD") from exc
        elif k == "tahun":
            if not str(v).isdigit() or not 1945 <= int(v) <= 2100:
                raise CorrectionError("tahun tidak wajar")
            v = int(v)
        else:
            v = re.sub(r"\s+", " ", str(v)).strip()
        clean[k] = v
    return clean


def _rel(path: Path) -> str:
    cwd = Path.cwd()
    return str(path.relative_to(cwd)) if path.is_absolute() and path.is_relative_to(cwd) else str(path)


def resolve(catalog, settings, doc_id: str, koreksi: dict[str, Any], *,
            oleh: str | None = None, dry_run: bool = False) -> dict[str, Any]:
    """Apply a manual correction, then name and move the file into the KB."""
    conn = catalog.conn
    ensure_schema(conn)
    row = conn.execute("SELECT * FROM penamaan WHERE doc_id = ?", (doc_id,)).fetchone()
    doc = catalog.get(doc_id)
    if doc is None:
        raise CorrectionError(f"dokumen {doc_id} tidak ada di katalog")
    ident = _identity_from_json(row["identitas"] if row else None)
    for k, v in _validate(koreksi).items():
        setattr(ident, k, Element(v, "koreksi-manual", None))
    if ident.tahun.nilai is None and isinstance(ident.tanggal.nilai, date):
        ident.tahun = Element(ident.tanggal.nilai.year, ident.tanggal.sumber, None)

    template, need = naming_rule(conn, settings.naming, doc["source_key"])
    kurang = missing(ident, need)
    if kurang:
        raise CorrectionError("masih kurang: " + ", ".join(kurang))

    md = RegulationMetadata(
        title=doc["title"], subject=ident.judul.nilai, doc_type=ident.jenis.nilai or doc["doc_type"],
        number=ident.nomor.nilai, year=ident.tahun.nilai, status=doc["reg_status"] or "unknown")
    kb = settings.knowledge_base
    nama = render_name(template, naming_fields(ident, kategori=doc["category"],
                                               sumber=doc["source_key"], status=md.status))
    folder = (kb / kb_relative_path(md, doc["category"] or "lain-lain", nama,
                                    doc["source_key"] or "lainnya")).parent
    current = Path(doc["stored_path"]) if doc["stored_path"] else None
    target = folder / nama
    if current is None or current.resolve() != target.resolve():
        target = unique_path(target)
    out = {"doc_id": doc_id, "dari": doc["stored_path"], "ke": _rel(target), "nama": target.name}
    if dry_run:
        return out
    if current is not None and current.exists() and current.resolve() != target.resolve():
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(current), target)
    tanggal = ident.tanggal.nilai.isoformat() if isinstance(ident.tanggal.nilai, date) else None
    conn.execute(
        "UPDATE documents SET stored_path = ?, doc_type = ?, number = ?, year = ?, "
        "issued_date = ?, subject = ? WHERE doc_id = ?",
        (_rel(target), md.doc_type, md.number, md.year, tanggal, md.subject, doc_id))
    record(conn, doc_id, Placement("dikoreksi", target, target.name, []), ident, template, oleh=oleh)
    return out


# ---------------------------------------------------------------------------
# Existing documents / template change (#90)
# ---------------------------------------------------------------------------
@dataclass
class ApplyReport:
    template: str
    dinamai: int = 0
    tetap: int = 0
    antrian: int = 0
    hilang: int = 0
    rencana: list[dict[str, str]] = field(default_factory=list)
    kurang: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {"templat": self.template, "dinamai": self.dinamai, "tetap": self.tetap,
                "antrian": self.antrian, "berkas_hilang": self.hilang,
                "unsur_kurang": self.kurang, "contoh": self.rencana[:20]}


def apply_template(catalog, settings, *, template: str | None = None, dry_run: bool = True,
                   reread: bool = False, mode: str = "auto") -> ApplyReport:
    """(Re)name every catalogued file with the active template.

    Documents already in the KB that turn out incomplete are queued for
    correction but **not moved** — they are already in use; only the queue
    status changes. ``reread`` forces page 1 to be read again (e.g. after the
    reader improves); otherwise the stored identity is reused.
    """
    conn = catalog.conn
    ensure_schema(conn)
    naming = settings.naming
    template = template or active_template(conn, naming.template)
    chk = check_template(template)
    if not chk.valid:
        raise CorrectionError("; ".join(chk.errors))
    rep = ApplyReport(template)
    stored_ident = {r["doc_id"]: r["identitas"] for r in conn.execute("SELECT doc_id, identitas FROM penamaan")}
    kb = settings.knowledge_base

    for doc in conn.execute("SELECT * FROM documents ORDER BY doc_id").fetchall():
        current = Path(doc["stored_path"]) if doc["stored_path"] else None
        if current is None or not current.exists():
            rep.hilang += 1
            continue
        if doc["doc_id"] in stored_ident and not reread:
            ident = _identity_from_json(stored_ident[doc["doc_id"]])
        else:
            ident = read_identity(current, mode=mode, ocr_settings=settings.ocr)
        md = RegulationMetadata(
            title=doc["title"], subject=doc["subject"], doc_type=doc["doc_type"], number=doc["number"],
            year=doc["year"], status=doc["reg_status"] or "unknown",
            issued_date=date.fromisoformat(doc["issued_date"][:10]) if doc["issued_date"] else None)
        fill_from_metadata(ident, md)
        if doc["source_key"] == SOURCE_RANCANGAN:
            tpl, need = naming_rule(conn, naming, doc["source_key"])
        else:
            tpl, need = template, required_for(template, naming.required)
        kurang = missing(ident, need)
        if kurang:
            rep.antrian += 1
            for k in kurang:
                rep.kurang[k] = rep.kurang.get(k, 0) + 1
            if not dry_run:
                record(conn, doc["doc_id"], Placement("antrian", current, None, kurang), ident, tpl)
            continue
        nama = render_name(tpl, naming_fields(ident, kategori=doc["category"],
                                              sumber=doc["source_key"], status=md.status))
        target = current.parent / nama
        if current.name == nama:
            rep.tetap += 1
        else:
            target = unique_path(target)
            rep.dinamai += 1
            rep.rencana.append({"dari": current.name, "ke": target.name})
        if dry_run:
            continue
        if target != current:
            shutil.move(str(current), target)
            conn.execute("UPDATE documents SET stored_path = ? WHERE doc_id = ?",
                         (_rel(target), doc["doc_id"]))
        prev = conn.execute("SELECT status FROM penamaan WHERE doc_id = ?", (doc["doc_id"],)).fetchone()
        status = "dikoreksi" if prev and prev["status"] == "dikoreksi" else "dinamai"
        record(conn, doc["doc_id"], Placement(status, target, target.name, []), ident, tpl)
    return rep


def token_help() -> dict[str, str]:
    return dict(TOKENS)
