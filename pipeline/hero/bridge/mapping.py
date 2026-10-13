"""Penerjemah kontrak: struktur data HERO → skema backend, dan sebaliknya.

Semua pengetahuan tentang *nama field backend* terkumpul di satu berkas ini.
Kalau backend mengubah kontraknya, yang berubah hanya di sini — worker tidak
perlu disentuh. Dua kontrak yang diterjemahkan:

* ``backend/docs/api/crawler-adapter-contract.md`` §2.1 ``PdfCandidate``
* ``backend/docs/api/ingest-extraction-contract.md`` §3.3 hasil ekstraksi

Aturan yang dipegang di sini (invarian lapisan data):

* **Tidak mengarang.** Nilai yang tidak terbaca dikirim sebagai ``None``,
  bukan ditebak. Tanggal "mulai berlaku" hanya dikirim bila sumbernya memang
  menuliskannya — tanggal pengundangan *bukan* tanggal berlaku.
* **Keyakinan harus bisa dipertanggungjawabkan.** ``field_confidence`` memberi
  angka dari tabel aturan yang tertulis di docstring-nya, bukan dari perasaan;
  ambang 0,7 di backend-lah yang memutuskan ``perlu_koreksi``.
"""
from __future__ import annotations

import json
import re
from datetime import date
from typing import Any

# hero status (inventory.status / RegulationMetadata.status) → backend enum
# StatusKeberlakuan. "rancangan" tidak punya padanan: sebuah draft belum
# berlaku dan belum dicabut, jadi jujur dikirim sebagai tidak_diketahui dan
# perannya dinyatakan lewat document_role di sisi backend.
BACKEND_STATUS = {
    "berlaku": "berlaku",
    "diubah": "diubah",
    "dicabut": "dicabut",
    "rancangan": "tidak_diketahui",
    "unknown": "tidak_diketahui",
    None: "tidak_diketahui",
}

# jenis lampiran HERO → doc_kind backend (utama | abstrak | faq | lampiran | lainnya)
BACKEND_DOC_KIND = {
    "utama": "utama", "abstrak": "abstrak", "faq": "faq", "lampiran": "lampiran",
    "matriks": "lainnya", "infografis": "lainnya", "terjemahan": "lainnya",
    "landasan": "lainnya", "riwayat": "lainnya",
}

# file_method dari `hero scan ukur` → size_source backend
BACKEND_SIZE_SOURCE = {"head": "head", "range": "range", "listing": "listing"}

# Label tanggal pada register, per sumber. Urutan = prioritas.
RELEASE_DATE_FIELDS = ("Tanggal Penetapan (ISO)", "Tanggal Pengundangan (ISO)", "Tanggal (ISO)")
EFFECTIVE_DATE_FIELDS = ("Tanggal Berlaku (ISO)",)
SUB_BIDANG_FIELDS = ("Sub Klasifikasi", "Sub Sektor", "Sub-Sektor")


# --------------------------------------------------------------------------
# Kandidat hasil pindai (mode push)
# --------------------------------------------------------------------------
def _iso(value: Any) -> str | None:
    if isinstance(value, date):
        return value.isoformat()
    s = str(value or "").strip()
    return s[:10] if re.match(r"^\d{4}-\d{2}-\d{2}", s) else None


def _first(fields: dict[str, Any], names: tuple[str, ...]) -> Any:
    for n in names:
        v = fields.get(n)
        if v not in (None, ""):
            return v
    return None


def _filename_from(url: str, fallback: str | None = None) -> str:
    from urllib.parse import unquote, urlsplit

    name = unquote(urlsplit(url).path.rsplit("/", 1)[-1]).strip()
    if name and "." in name:
        return name[:255]
    base = (fallback or "dokumen").strip() or "dokumen"
    return (base if base.lower().endswith(".pdf") else f"{base}.pdf")[:255]


def _row_fields(row: dict[str, Any]) -> dict[str, Any]:
    """``fields`` bisa berupa dict (dari kode) atau ``fields_json`` (dari SQLite)."""
    raw = row.get("fields")
    if isinstance(raw, dict):
        return raw
    blob = row.get("fields_json") or raw
    if isinstance(blob, str) and blob.strip():
        try:
            parsed = json.loads(blob)
            return parsed if isinstance(parsed, dict) else {}
        except json.JSONDecodeError:
            return {}
    return {}


def _attachments(row: dict[str, Any]) -> list[dict[str, Any]]:
    raw = row.get("attachments")
    if isinstance(raw, list):
        return raw
    blob = row.get("attachments_json") or raw
    if isinstance(blob, str) and blob.strip():
        try:
            parsed = json.loads(blob)
            return parsed if isinstance(parsed, list) else []
        except json.JSONDecodeError:
            return []
    return []


def candidate_from_inventory(row: dict[str, Any], *, depth: int = 1,
                             url: str | None = None, filename: str | None = None,
                             doc_kind: str = "utama") -> dict[str, Any] | None:
    """Satu rekaman register HERO → satu ``PdfCandidate`` backend.

    ``None`` bila rekaman itu belum punya tautan berkas: register memuat
    halaman detail yang kadang belum (atau tidak) melampirkan dokumen, dan
    kandidat tanpa URL tidak berarti apa-apa bagi backend.
    """
    doc_url = url or row.get("document_url")
    if not doc_url:
        return None
    f = _row_fields(row)
    year = row.get("year")
    return {
        "url": str(doc_url),
        "filename": filename or _filename_from(str(doc_url), row.get("document_name") or row.get("title")),
        "size_bytes": row.get("file_size") or None,
        "size_source": BACKEND_SIZE_SOURCE.get(row.get("file_method") or "", "unknown"),
        "found_on_page": row.get("detail_url") or row.get("record_key") or "",
        "depth": int(depth),
        "document_title": row.get("title") or None,
        "detail_url": row.get("detail_url") or row.get("record_key") or None,
        "final_url": None,                    # backend menyelesaikan redirect saat menarik
        "doc_kind": BACKEND_DOC_KIND.get(doc_kind, "lainnya"),
        "regulation_number": row.get("number") or None,
        "regulation_type": (row.get("doc_type") or None),
        "bidang": row.get("sektor") or None,
        "sub_bidang": _first(f, SUB_BIDANG_FIELDS),
        "release_date": _iso(_first(f, RELEASE_DATE_FIELDS)),
        "effective_date": _iso(_first(f, EFFECTIVE_DATE_FIELDS)),
        "regulation_year": int(year) if str(year or "").isdigit() else None,
        "status_keberlakuan": BACKEND_STATUS.get(row.get("status"), "tidak_diketahui"),
        "source_path": None,
        "match_warning": row.get("file_error") or None,
    }


def candidates_from_inventory_row(row: dict[str, Any], *, depth: int = 1,
                                  include_companions: bool = False) -> list[dict[str, Any]]:
    """Dokumen utama rekaman + (opsional) lampiran pendampingnya.

    Abstrak/FAQ/matriks default-nya **tidak** dikirim: yang disimpan adalah
    peraturannya sendiri (keputusan desain `exclude_patterns`). Backend tetap
    menerimanya bila diminta, lengkap dengan ``doc_kind`` yang benar sehingga
    bisa dipilih atau diabaikan di layar hasil pemindaian.
    """
    out: list[dict[str, Any]] = []
    main = candidate_from_inventory(row, depth=depth)
    if main:
        out.append(main)
    seen = {c["url"] for c in out}
    for att in _attachments(row):
        url = att.get("url")
        kind = att.get("kind") or "lainnya"
        if not url or url in seen:
            continue
        if not include_companions and kind != "utama":
            continue
        if not str(att.get("ext") or "pdf").lower().startswith("pdf") and kind != "utama":
            continue
        cand = candidate_from_inventory(row, depth=depth, url=url,
                                        filename=att.get("name"), doc_kind=kind)
        if cand:
            cand["size_bytes"] = att.get("size") or cand["size_bytes"]
            if att.get("size"):
                cand["size_source"] = "listing"
            out.append(cand)
            seen.add(url)
    return out


# --------------------------------------------------------------------------
# Hasil ekstraksi
# --------------------------------------------------------------------------
# Keyakinan per field. Tabel ini adalah kontraknya — angkanya bukan selera,
# tapi cerminan dari *dari mana* nilai itu dibaca:
#
#   1,00  tidak dipakai: tidak ada pembacaan otomatis yang pasti
#   0,95  terbaca di blok pembuka halaman 1 (lapisan teks) — tempat identitas
#         peraturan Indonesia selalu berada
#   0,85  terbaca di blok penutup ("Ditetapkan di … pada tanggal …")
#   0,75  dilengkapi dari metadata dokumen utuh / register sumber
#   0,55  turunan: judul dari metadata PDF, jenis dari pola nomor
#   0,35  dari nama berkas saja
#   0,00  tidak terbaca → field dikirim None dan backend menandai perlu_koreksi
#
# Halaman yang dibaca lewat OCR dikalikan keyakinan OCR halaman itu (0..1),
# karena karakter yang salah baca tidak pernah lebih yakin dari mesin OCR-nya.
CONF_BY_SOURCE = {"halaman-1": 0.95, "penutup": 0.85, "metadata": 0.75,
                  "turunan": 0.55, "nama-berkas": 0.35, "koreksi-manual": 0.99}

# Batas kolom ``documents`` di backend (String(n)). Nilai lebih panjang tidak
# ditolak di pintu masuk (PATCH 200) melainkan meledak saat commit penempatan,
# dan dokumennya diklaim ulang tanpa akhir sampai percobaannya habis.
BATAS_KOLOM = {"title": 255, "regulation_number": 100, "regulation_type": 100,
               "bidang": 150, "extraction_engine": 100}
# Judul peraturan sungguhan jarang melebihi ±200 karakter. Lebih panjang dari
# itu hampir pasti teks isi yang terbaca sebagai judul (halaman pertama tanpa
# kop, mis. lembar ringkasan satu halaman).
JUDUL_WAJAR_MAKS = 200
KEYAKINAN_HEADER_GAGAL = 0.4          # < ambang backend 0.7 → masuk antrean koreksi


def bersihkan_teks(value: str | None) -> str:
    """Buang byte NUL (0x00): kolom teks PostgreSQL menolaknya sama sekali.

    OCR dan pengekstrak PDF kadang mengeluarkannya untuk glif yang tak terpetakan.
    Satu byte di antara ratusan ribu karakter cukup untuk menggagalkan commit
    seluruh dokumen (insiden VPS 13 Okt: dokumen 137 diklaim ulang sampai
    percobaannya habis). Hanya NUL yang dibuang; karakter kontrol lain diterima
    PostgreSQL dan tidak diubah."""
    return str(value).replace("\x00", "") if value else ""


def _fit(value: str | None, n: int) -> str | None:
    """Rapikan spasi lalu potong ke ``n`` karakter di batas kata, dengan elipsis."""
    if not value:
        return None
    v = " ".join(bersihkan_teks(value).split())
    if not v:
        return None
    if len(v) <= n:
        return v
    cut = v[: n - 1]
    if " " in cut[n // 2:]:
        cut = cut[: cut.rindex(" ")]
    return cut.rstrip(" ,;:-") + "…"


def header_gagal_dibaca(md) -> bool:
    """Kop dokumen jelas gagal diurai: judul terlalu panjang untuk judul sungguhan.

    Pada kasus ini bukan hanya judulnya yang tak bisa dipercaya. Pengurai
    mengambil nomor/jenis dari tempat lain dalam teks — terbukti pada lembar
    ringkasan SEOJK satu halaman, nomor yang terbaca adalah nomor peraturan
    LAIN yang disebut sebagai yang dicabut."""
    return len(" ".join(str(getattr(md, "subject", "") or "").split())) > JUDUL_WAJAR_MAKS


def field_confidence(md, *, identity=None, ocr_confidence: float | None = None,
                     from_ocr: bool = False) -> dict[str, float]:
    """Keyakinan per field metadata, mengikuti tabel di atas."""
    def src(name: str, default: str) -> str:
        if identity is None:
            return default
        el = getattr(identity, name, None)
        if el is None or getattr(el, "nilai", None) in (None, ""):
            return default
        return getattr(el, "sumber", None) or default

    scale = 1.0
    if from_ocr and ocr_confidence is not None:
        scale = max(0.0, min(1.0, float(ocr_confidence) / 100.0
                             if ocr_confidence > 1 else float(ocr_confidence)))

    conf: dict[str, float] = {}
    if md.number:
        conf["regulation_number"] = CONF_BY_SOURCE.get(src("nomor", "metadata"), 0.75)
    if md.doc_type:
        # Jenis diambil dari blok sebelum kata TENTANG; bila hanya tersirat dari
        # pola nomor ("11/POJK.03/2022") itu turunan, bukan bacaan langsung.
        conf["regulation_type"] = CONF_BY_SOURCE.get(src("jenis", "turunan"), 0.55)
    if md.issued_date:
        conf["release_date"] = CONF_BY_SOURCE.get(src("tanggal", "metadata"), 0.75)
    if md.title:
        has_subject = bool(md.subject)
        conf["title"] = CONF_BY_SOURCE["halaman-1"] if has_subject else CONF_BY_SOURCE["nama-berkas"]
    if header_gagal_dibaca(md):
        # Jangan lolos diam-diam sebagai "terindeks": biarkan manusia memeriksa.
        conf = {k: min(v, KEYAKINAN_HEADER_GAGAL) for k, v in conf.items()}
    return {k: round(v * scale, 2) for k, v in conf.items()}


def extraction_payload(md, extraction, *, identity=None, quality: dict[str, Any] | None = None,
                       bidang: str | None = None, send_full_text: bool = True,
                       max_chars: int = 300_000,
                       engine: str = "hero-pipeline") -> dict[str, Any]:
    """Isi ``PATCH /internal/documents/{id}/extraction`` dari hasil ekstraksi HERO."""
    from_ocr = bool(getattr(extraction, "ocr_pages", 0))
    payload: dict[str, Any] = {
        "bidang": _fit(bidang, BATAS_KOLOM["bidang"]),
        "title": _fit(md.subject or md.title, BATAS_KOLOM["title"]),
        "regulation_number": _fit(md.number, BATAS_KOLOM["regulation_number"]),
        "regulation_type": _fit(md.doc_type, BATAS_KOLOM["regulation_type"]),
        "release_date": md.issued_date.isoformat() if isinstance(md.issued_date, date) else None,
        "extraction_method": "ocr" if from_ocr else "teks_langsung",
        "extraction_engine": _fit(engine, BATAS_KOLOM["extraction_engine"]),
        "confidence": field_confidence(
            md, identity=identity, from_ocr=from_ocr,
            ocr_confidence=getattr(extraction, "mean_ocr_confidence", None)),
    }
    if send_full_text:
        text = extraction.text if hasattr(extraction, "text") else str(extraction)
        payload["full_text"] = bersihkan_teks(text)[:max_chars]
    if quality and quality.get("grade") in ("gagal",):
        # Grade "gagal" berarti teks tidak terbaca sama sekali; pemanggil
        # memutuskan mengirim error, bukan metadata kosong.
        payload["_grade"] = quality["grade"]
    return payload


def failure_payload(code: str, message: str) -> dict[str, Any]:
    """Isi PATCH untuk kegagalan. ``code``: ``ekstraksi_gagal`` | ``ocr_gagal``."""
    return {"error": {"code": code, "message": message[:1000]}}


# --------------------------------------------------------------------------
# Pasal → tabel articles
# --------------------------------------------------------------------------
def pasal_label(number: str | None) -> str | None:
    """Nomor pasal HERO ("2", "7A") → label yang dipakai backend ("Pasal 2").

    Parser struktur HERO menyimpan nomornya saja; tabel ``articles`` backend
    menyimpan labelnya ("Pasal 5", "Ayat (1)" — lihat ``ArticleChunkIn``).
    Penyeragaman dilakukan di sini, bukan di parser, supaya katalog HERO tetap
    bisa mengurutkan pasal secara numerik.
    """
    raw = " ".join(str(number or "").split())
    if not raw:
        return None
    return raw if re.match(r"^[A-Za-z]", raw) else f"Pasal {raw}"


def pasal_number(label: str | None) -> str:
    """Kebalikan ``pasal_label``: "Pasal 7A" → "7A".

    Katalog HERO menyimpan nomornya saja. Itu bukan selera: rencana perubahan
    yang dibaca dari teks draft ("Ketentuan Pasal 4 diubah…") menghasilkan
    nomor polos, dan pencocokannya ke pasal korpus gagal hening-hening bila
    satu sisi menyimpan "Pasal 4" dan sisi lain "4".
    """
    raw = " ".join(str(label or "").split())
    return re.sub(r"^(?:pasal|article)\s+", "", raw, flags=re.IGNORECASE)


def _trim(value: str | None, n: int) -> str | None:
    if not value:
        return None
    v = " ".join(bersihkan_teks(value).split())
    return v[:n] if v else None


def article_payloads(document_id: int, articles: list, *,
                     vectors: list[list[float] | None] | None = None,
                     push_ayat: bool = False,
                     with_page: bool = False,
                     with_parent: bool = False) -> list[dict[str, Any]]:
    """``DocumentStructure.articles`` → daftar ``ArticleChunkIn`` backend.

    Hanya pasal batang tubuh yang dikirim: pasal di lampiran/penjelasan adalah
    rujukan, bukan norma, dan memasukkannya akan mencemari unit pembanding
    harmonisasi. ``order_index`` menjaga urutan tampil karena nomor pasal bisa
    berupa "7A" (pasal sisipan) yang tidak terurut secara numerik.

    ``with_page`` dan ``with_parent`` mengikuti kemampuan backend yang
    sebenarnya (``BackendClient.article_contract``), bukan harapan: backend
    lama mengabaikan field asing tanpa bersuara, sehingga mengirimnya begitu
    saja hanya menyembunyikan bahwa halaman tidak pernah sampai.

    ``push_ayat`` butuh ``with_parent``. Tanpa induk, ayat menjadi baris
    menggantung yang tidak bisa ditelusuri kembali ke pasalnya — lebih buruk
    daripada tidak mengirimnya, karena isinya sudah termuat di dalam teks
    pasal.
    """
    if push_ayat and not with_parent:
        raise ValueError("push_ayat butuh with_parent: ayat tanpa induk tidak dapat ditelusuri")
    rows: list[dict[str, Any]] = []
    order = 0
    for i, art in enumerate(articles):
        if getattr(art, "in_attachment", False):
            continue
        number = _trim(pasal_label(getattr(art, "number", None)), 50) or f"Pasal {i + 1}"
        text = bersihkan_teks(getattr(art, "text", "") or "").strip()
        if not text:
            continue
        row: dict[str, Any] = {
            "document_id": int(document_id),
            "level": "pasal",
            "chapter_title": _trim(getattr(art, "bab", None), 255),
            "article_number": number,
            "content_text": text,
            "order_index": order,
        }
        halaman = _page_number(getattr(art, "page", None))
        if with_page and halaman is not None:
            row["page"] = halaman
        vec = vectors[i] if vectors and i < len(vectors) else None
        if vec is not None:
            row["embedding"] = vec
        rows.append(row)
        induk = order
        order += 1

        if push_ayat:
            for num, body in getattr(art, "ayat", []) or []:
                body = bersihkan_teks(body or "").strip()
                if not body:
                    continue
                ayat_row: dict[str, Any] = {
                    "document_id": int(document_id),
                    "level": "ayat",
                    "chapter_title": _trim(getattr(art, "bab", None), 255),
                    "article_number": _trim(f"{number} ayat ({num})", 50) or number,
                    "content_text": body,
                    "order_index": order,
                    "parent_order_index": induk,
                }
                if with_page and halaman is not None:
                    # Halaman ayat = halaman pasalnya: parser mencatat posisi
                    # awal pasal, bukan tiap ayat. Menebak halaman ayat yang
                    # lebih jauh akan menghasilkan rujukan yang salah.
                    ayat_row["page"] = halaman
                rows.append(ayat_row)
                order += 1
    return rows


def _page_number(value: Any) -> int | None:
    """Halaman 1-indexed yang dapat diterima backend (``ge=1``), atau None.

    Nilai 0/negatif/tak terbaca dibuang alih-alih dikoreksi: halaman yang
    ditebak akan mengirim pemeriksa ke halaman yang salah, dan itu lebih
    merugikan daripada kolom kosong yang jujur."""
    try:
        n = int(value)
    except (TypeError, ValueError):
        return None
    return n if n >= 1 else None
