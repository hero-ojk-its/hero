"""Penamaan berkas dinamis (US-20a, dasar untuk #89 UI dan #90 rename).

Weekly #4, keputusan 5: OJK tidak punya format nama berkas baku, jadi
formatnya disusun pengguna. Format adalah templat dengan token:

    {jenis} {nomor_urut} Tahun {tahun} tentang {judul:90|title}
    → "POJK 11 Tahun 2024 tentang Ketahanan dan Keamanan Siber Bank Umum.pdf"

Sintaks token: ``{nama[:argumen][|filter]}``
  * argumen teks   → panjang maksimum ({judul:60})
  * argumen tanggal → format strftime ({tanggal:%d%m%Y})
  * filter          → lower · upper · title · slug

Nama yang dihasilkan selalu aman di Windows/macOS/Linux (tanpa / \\ : * ? " < > |),
dibatasi panjangnya, dan tidak pernah menimpa berkas lain. Nama hanya
diterapkan bila unsur wajib lengkap; bila tidak, dokumen masuk antrian koreksi
manual — tidak dibuang dan tidak diberi nama tebakan.
"""
from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

DEFAULT_TEMPLATE = "{jenis} {nomor_urut} Tahun {tahun} tentang {judul:90|title}"
MAX_NAME = 150
TOKENS: dict[str, str] = {
    "jenis": "Jenis peraturan, mis. POJK",
    "nomor": "Nomor lengkap, mis. 11/POJK.03/2024 (garis miring menjadi '-')",
    "nomor_urut": "Angka nomor saja, mis. 11",
    "tahun": "Tahun peraturan, mis. 2024",
    "tanggal": "Tanggal penetapan; argumen strftime, mis. {tanggal:%d-%m-%Y}",
    "judul": "Judul/perihal; argumen = panjang maksimum, mis. {judul:60}",
    "kategori": "Kategori knowledge base, mis. perbankan",
    "bidang": "Bidang/sektor dalam bentuk label, mis. Pasar Modal",
    "sumber": "Sumber dokumen, mis. jdih-ojk",
    "status": "Status hukum, mis. berlaku",
}
FILTERS = ("lower", "upper", "title", "slug")
_TOKEN = re.compile(r"\{([a-z_]+)(?::([^}|]*))?(?:\|([a-z]+))?\}")
_UNSAFE = re.compile(r'[\\/:*?"<>|\x00-\x1f]+')


@dataclass
class TemplateCheck:
    valid: bool
    errors: list[str]
    tokens: list[str]


def check_template(template: str) -> TemplateCheck:
    errors: list[str] = []
    used = []
    if not template or not template.strip():
        return TemplateCheck(False, ["templat kosong"], [])
    for m in _TOKEN.finditer(template):
        name, arg, flt = m.groups()
        used.append(name)
        if name not in TOKENS:
            errors.append(f"token tidak dikenal: {{{name}}}")
        if flt and flt not in FILTERS:
            errors.append(f"filter tidak dikenal: |{flt} (pilihan: {', '.join(FILTERS)})")
        if arg and name != "tanggal" and not arg.isdigit():
            errors.append(f"argumen {{{name}:{arg}}} harus berupa angka (panjang maksimum)")
    leftover = _TOKEN.sub("", template)
    if "{" in leftover or "}" in leftover:
        errors.append("kurung kurawal tidak berpasangan")
    if not used:
        errors.append("templat tidak memuat satu token pun — semua berkas akan bernama sama")
    return TemplateCheck(not errors, errors, used)


def _slug(s: str) -> str:
    return re.sub(r"-{2,}", "-", re.sub(r"[^a-z0-9]+", "-", s.lower())).strip("-")


def _apply(value: Any, name: str, arg: str | None, flt: str | None) -> str:
    if value in (None, ""):
        return ""
    if name == "tanggal":
        d = value if isinstance(value, date) else date.fromisoformat(str(value)[:10])
        text = d.strftime(arg or "%Y-%m-%d")
    else:
        text = str(value)
        if name == "nomor":
            text = text.replace("/", "-")
        text = re.sub(r"\s+", " ", text).strip()
        if arg and arg.isdigit() and len(text) > int(arg):
            text = text[: int(arg)].rsplit(" ", 1)[0]
    if flt == "lower":
        text = text.lower()
    elif flt == "upper":
        text = text.upper()
    elif flt == "title":
        from hero.kb.readmodel import title_case_id
        text = title_case_id(text)
    elif flt == "slug":
        text = _slug(text)
    return text


def nomor_urut(nomor: str | None) -> str | None:
    m = re.match(r"\s*(\d+)", nomor or "")
    return m.group(1) if m else None


def render_name(template: str, fields: dict[str, Any], *, ext: str = ".pdf") -> str:
    """Fill the template and make the result a safe file name."""
    values = dict(fields)
    values.setdefault("nomor_urut", nomor_urut(values.get("nomor")))
    if values.get("kategori") and not values.get("bidang"):
        from hero.kb.readmodel import CATEGORY_LABELS, title_case_id
        values["bidang"] = CATEGORY_LABELS.get(values["kategori"]) or title_case_id(
            str(values["kategori"]).replace("-", " "))
    name = _TOKEN.sub(lambda m: _apply(values.get(m.group(1)), *m.groups()), template)
    name = _UNSAFE.sub("-", name)
    # Missing optional tokens leave dangling separators: "POJK  tentang" → "POJK tentang".
    name = re.sub(r"\s{2,}", " ", name)
    name = re.sub(r"([-_ ])\1+", r"\1", name).strip(" .-_")
    name = name[: MAX_NAME - len(ext)].rstrip(" .-_") or "dokumen"
    return name + ext


# ---------------------------------------------------------------------------
# Komponen tombol (Weekly #4, keputusan 5): halaman Scraping menampilkan tombol
# Nama / Tahun / Jenis / Bidang; urutan klik menentukan format. UI cukup
# mengirim urutan itu — templatnya disusun di sini supaya #89 (UI) dan #90
# (rename) memakai satu definisi yang sama.
# ---------------------------------------------------------------------------
COMPONENTS: dict[str, tuple[str, str]] = {
    "nama": ("Nama", "{judul:90}"),
    "tahun": ("Tahun", "{tahun}"),
    "jenis": ("Jenis", "{jenis}"),
    "bidang": ("Bidang", "{bidang}"),
    # Bukan tombol di mockup, tetapi tanpa nomor dua peraturan sejenis pada
    # tahun yang sama dengan perihal mirip bisa bernama sama (lihat laporan).
    "nomor": ("Nomor", "{nomor_urut}"),
}
DEFAULT_SEPARATOR = " - "


def template_from_components(components: list[str],
                             separator: str = DEFAULT_SEPARATOR) -> str:
    """["jenis", "nomor", "tahun", "nama"] → "{jenis} - {nomor_urut} - {tahun} - {judul:90}".

    Komponen yang sama boleh muncul lebih dari sekali (tombol boleh diklik
    ulang); urutan dipertahankan apa adanya.
    """
    unknown = [c for c in components if c.lower() not in COMPONENTS]
    if unknown:
        raise ValueError(f"komponen tidak dikenal: {', '.join(unknown)} "
                         f"(pilihan: {', '.join(COMPONENTS)})")
    if not components:
        raise ValueError("pilih minimal satu komponen")
    if _UNSAFE.search(separator):
        raise ValueError("pemisah memuat karakter yang tidak boleh ada di nama berkas")
    return separator.join(COMPONENTS[c.lower()][1] for c in components)


def components_from_template(template: str,
                             separator: str = DEFAULT_SEPARATOR) -> list[str] | None:
    """Kebalikan dari :func:`template_from_components` untuk memulihkan tombol di UI.

    ``None`` bila templat tidak disusun dari tombol (mis. diketik bebas).
    """
    by_token = {tpl: key for key, (_label, tpl) in COMPONENTS.items()}
    parts = template.split(separator)
    if all(p in by_token for p in parts):
        return [by_token[p] for p in parts]
    return None


def unique_path(path: Path) -> Path:
    if not path.exists():
        return path
    for n in range(2, 1000):
        cand = path.with_name(f"{path.stem} ({n}){path.suffix}")
        if not cand.exists():
            return cand
    raise FileExistsError(path)


# ---------------------------------------------------------------------------
# Active template: config default, overridable at run time (#89 UI) without
# editing files — stored in the catalog so every process sees the same one.
# ---------------------------------------------------------------------------
SETTINGS_SCHEMA = "CREATE TABLE IF NOT EXISTS pengaturan (kunci TEXT PRIMARY KEY, nilai TEXT, diubah TEXT)"


def active_template(conn: sqlite3.Connection | None, default: str) -> str:
    if conn is None:
        return default
    conn.execute(SETTINGS_SCHEMA)
    row = conn.execute("SELECT nilai FROM pengaturan WHERE kunci = 'penamaan.templat'").fetchone()
    return row[0] if row and row[0] else default


def save_template(conn: sqlite3.Connection, template: str) -> TemplateCheck:
    chk = check_template(template)
    if chk.valid:
        conn.execute(SETTINGS_SCHEMA)
        with conn:
            conn.execute("INSERT OR REPLACE INTO pengaturan VALUES ('penamaan.templat', ?, datetime('now'))",
                         (template,))
    return chk
