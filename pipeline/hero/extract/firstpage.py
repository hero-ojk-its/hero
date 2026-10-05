"""US-20a — baca unsur identitas dari halaman pertama (OCR bila perlu).

Arahan mitra: "Buka halaman pertama, pakai OCR, dibaca judulnya. Pasti
terdiri dari nomor peraturan, tanggal, dan judul." Nomor dan judul memang
ada di halaman pertama hampir semua peraturan. Tanggal **tidak**: diukur
pada 89 dokumen KB, tanggal hanya ada di halaman pertama pada 18 dokumen
(20%). Peraturan perundang-undangan Indonesia menaruh tanggal penetapan di
blok penutup ("Ditetapkan di Jakarta pada tanggal …"), di halaman terakhir
batang tubuh — UU 12/2011 Lampiran II mengaturnya begitu.

Karena itu setiap unsur dibaca dari halaman pertama lebih dulu, dan tanggal
yang tidak ada di sana dicari di blok penutup. Setiap unsur membawa
``sumber``-nya (halaman-1 / penutup) dan cara bacanya (lapisan teks / OCR),
supaya keputusan "masuk antrian koreksi" bisa dijelaskan dan supaya mitra
bisa memutuskan, dengan angka, apakah tanggal dari penutup boleh dipakai.

Lapisan teks dipakai bila halaman memilikinya (lebih cepat dan lebih akurat
daripada OCR); OCR dijalankan untuk halaman hasil pindai, atau selalu bila
``mode="ocr"``.
"""
from __future__ import annotations

import io
import re
import time
from dataclasses import asdict, dataclass, field
from datetime import date
from pathlib import Path
from typing import Any

from hero.extract.metadata import (
    RE_DITETAPKAN, _detect_type, _extract_number, _extract_subject, _identity_block, _parse_date,
)

MIN_TEXT_CHARS = 120          # same threshold extract_pdf uses for "image-only page"
CLOSING_PAGES = 3             # the closing formula sits in the last pages of the batang tubuh
REQUIRED = ("nomor", "tanggal", "judul")


@dataclass
class Element:
    nilai: Any
    sumber: str | None = None       # "halaman-1" | "penutup" | "koreksi-manual"
    cara: str | None = None         # "teks" | "ocr"


@dataclass
class Identity:
    jenis: Element = field(default_factory=lambda: Element(None))
    nomor: Element = field(default_factory=lambda: Element(None))
    tahun: Element = field(default_factory=lambda: Element(None))
    tanggal: Element = field(default_factory=lambda: Element(None))
    judul: Element = field(default_factory=lambda: Element(None))
    halaman_1_cara: str | None = None
    ocr_keyakinan: float | None = None
    detik: float = 0.0
    catatan: list[str] = field(default_factory=list)

    @property
    def kurang(self) -> list[str]:
        return [k for k in REQUIRED if getattr(self, k).nilai in (None, "")]

    @property
    def lengkap(self) -> bool:
        return not self.kurang

    def values(self) -> dict[str, Any]:
        out = {k: getattr(self, k).nilai for k in ("jenis", "nomor", "tahun", "tanggal", "judul")}
        if isinstance(out["tanggal"], date):
            out["tanggal"] = out["tanggal"].isoformat()
        return out

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        for k in ("jenis", "nomor", "tahun", "tanggal", "judul"):
            if isinstance(d[k]["nilai"], date):
                d[k]["nilai"] = d[k]["nilai"].isoformat()
        d["kurang"] = self.kurang
        d["lengkap"] = self.lengkap
        return d


def _page_text(doc, index: int, *, force_ocr: bool, ocr_settings) -> tuple[str, str, float | None]:
    """(text, cara, confidence). OCR only when the page has no usable text
    layer — or always under force_ocr, which reproduces the partner's
    literal request and lets us measure OCR against the text layer."""
    page = doc[index]
    text = page.get_text() or ""
    if len(text.strip()) >= MIN_TEXT_CHARS and not force_ocr:
        return text, "teks", None
    if ocr_settings is None or not getattr(ocr_settings, "enabled", True):
        return text, "teks", None
    from PIL import Image

    from hero.extract.ocr import ocr_image, tesseract_available
    if not tesseract_available():
        return text, "teks", None
    png = page.get_pixmap(dpi=getattr(ocr_settings, "dpi", 300)).tobytes("png")
    res = ocr_image(Image.open(io.BytesIO(png)), languages=getattr(ocr_settings, "languages", "ind+eng"),
                    preprocess=getattr(ocr_settings, "preprocess", True),
                    deskew=getattr(ocr_settings, "deskew", True))
    return res["text"] or "", "ocr", res.get("confidence")


_TITLE_JUNK = re.compile(r"\s+(DENGAN RAHMAT|Menimbang|MENIMBANG|bahwa\s)", re.S)


def _judul(text: str) -> str | None:
    subj = _extract_subject(text)
    if not subj:
        return None
    subj = _TITLE_JUNK.split(subj)[0]
    subj = re.sub(r"\s+", " ", subj).strip(" .,;")
    return subj[:250] or None


def read_identity(path: str | Path, *, mode: str = "auto", ocr_settings=None) -> Identity:
    """Read jenis, nomor, tahun, tanggal, judul — page 1 first, closing block for the date.

    ``mode``: "auto" (text layer, OCR for scanned pages) or "ocr" (always OCR
    page 1 — the partner's literal procedure; slower, used to measure it).
    """
    import pymupdf

    started = time.perf_counter()
    ident = Identity()
    try:
        doc = pymupdf.open(str(path))
    except Exception as exc:  # noqa: BLE001 — unreadable files go to the correction queue
        ident.catatan.append(f"berkas tidak dapat dibuka: {type(exc).__name__}")
        ident.detik = round(time.perf_counter() - started, 3)
        return ident
    try:
        if doc.page_count == 0:
            ident.catatan.append("PDF tanpa halaman")
            return ident
        text, cara, conf = _page_text(doc, 0, force_ocr=(mode == "ocr"), ocr_settings=ocr_settings)
        ident.halaman_1_cara, ident.ocr_keyakinan = cara, conf
        head = _identity_block(text) or text[:1500]

        code, _label, _ = _detect_type(head)
        if code:
            ident.jenis = Element(code, "halaman-1", cara)
        number, _raw, year = _extract_number(head)
        if number:
            ident.nomor = Element(number, "halaman-1", cara)
        if year:
            ident.tahun = Element(year, "halaman-1", cara)
        judul = _judul(text)
        if judul:
            ident.judul = Element(judul, "halaman-1", cara)
        d = _parse_date(text[:3000])
        if d:
            ident.tanggal = Element(d, "halaman-1", cara)
        else:
            # Closing block: "Ditetapkan di Jakarta pada tanggal 12 Maret 2024".
            for i in range(max(1, doc.page_count - CLOSING_PAGES), doc.page_count)[::-1]:
                t, c, _ = _page_text(doc, i, force_ocr=False, ocr_settings=ocr_settings)
                m = RE_DITETAPKAN.search(t)
                if m:
                    d = _parse_date(t[m.end(): m.end() + 200])
                    if d:
                        ident.tanggal = Element(d, "penutup", c)
                        break
            if not ident.tanggal.nilai and doc.page_count > CLOSING_PAGES:
                # The Penjelasan/Lampiran can follow the closing block; scan
                # the text layer of the whole document for the formula.
                for i in range(doc.page_count):
                    t = doc[i].get_text() or ""
                    m = RE_DITETAPKAN.search(t)
                    if m and (d := _parse_date(t[m.end(): m.end() + 200])):
                        ident.tanggal = Element(d, "penutup", "teks")
                        break
        if ident.tahun.nilai is None and isinstance(ident.tanggal.nilai, date):
            ident.tahun = Element(ident.tanggal.nilai.year, ident.tanggal.sumber, ident.tanggal.cara)
        for k in ident.kurang:
            ident.catatan.append(f"{k} tidak terbaca")
    finally:
        doc.close()
        ident.detik = round(time.perf_counter() - started, 3)
    return ident


def survey(paths, *, mode: str = "auto", ocr_settings=None) -> dict[str, Any]:
    """Fill rates per element and where each came from — the US-20 measurement."""
    from collections import Counter

    n = lengkap = 0
    terisi: Counter = Counter()
    sumber: dict[str, Counter] = {k: Counter() for k in ("nomor", "tanggal", "judul")}
    cara: Counter = Counter()
    detik = 0.0
    contoh_kurang: list[dict[str, Any]] = []
    for p in paths:
        ident = read_identity(p, mode=mode, ocr_settings=ocr_settings)
        n += 1
        detik += ident.detik
        lengkap += ident.lengkap
        cara[ident.halaman_1_cara or "-"] += 1
        for k in ("jenis", "nomor", "tahun", "tanggal", "judul"):
            terisi[k] += getattr(ident, k).nilai not in (None, "")
        for k in sumber:
            sumber[k][getattr(ident, k).sumber or "tidak terbaca"] += 1
        if not ident.lengkap and len(contoh_kurang) < 15:
            contoh_kurang.append({"berkas": Path(p).name, "kurang": ident.kurang})
    pct = lambda v: round(100 * v / n, 1) if n else None  # noqa: E731
    return {
        "mode": mode, "dokumen": n, "lengkap": lengkap, "lengkap_pct": pct(lengkap),
        "terisi_pct": {k: pct(v) for k, v in terisi.items()},
        "sumber": {k: dict(v) for k, v in sumber.items()},
        "halaman_1_dibaca_dengan": dict(cara),
        "detik_total": round(detik, 2), "detik_per_dokumen": round(detik / n, 3) if n else None,
        "contoh_kurang": contoh_kurang,
    }
