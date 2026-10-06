"""Rule-based classification and knowledge-base placement (URD 3.2).

"Klasifikasi dan penempatan dokumen ke folder knowledge base yang sesuai
(folder eksisting atau folder baru dibuat otomatis)."

Layout: <kb>/<source>/<category>/<doc_type>/<year>/<status>/<file>.pdf
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path

from hero.models import RegulationMetadata

# Built-in fallback only. The rules HERO actually uses live in
# config/kategori.yaml (US-24: "tinggal kita ganti knowledge base-nya saja"),
# so a new category or keyword is a config change, not a code change.
CATEGORY_RULES: list[tuple[str, tuple[str, ...]]] = [
    ("teknologi-informasi", (
        "teknologi informasi", "sistem elektronik", "keamanan siber",
        "data pribadi", "layanan digital", "inovasi teknologi sektor keuangan",
        "itsk", "penyelenggara sistem", "alih daya", "outsourcing",
        "pusat data", "manajemen risiko teknologi",
    )),
    ("perbankan", (
        "bank umum", "perbankan", "bank perkreditan", "bpr", "bprs",
        "bank syariah", "kredit", "permodalan bank", "kualitas aset",
    )),
    ("pasar-modal", (
        "pasar modal", "emiten", "efek", "bursa", "reksa dana",
        "perusahaan publik", "penawaran umum", "manajer investasi",
    )),
    ("iknb", (
        "asuransi", "dana pensiun", "lembaga pembiayaan", "penjaminan",
        "pergadaian", "modal ventura", "perusahaan pembiayaan", "iknb",
    )),
    ("perlindungan-konsumen", (
        "perlindungan konsumen", "edukasi konsumen", "pengaduan konsumen",
        "literasi keuangan",
    )),
    ("apu-ppt", (
        "pencucian uang", "pendanaan terorisme", "apu", "ppt",
        "know your customer", "prinsip mengenal nasabah",
    )),
    ("tata-kelola", (
        "tata kelola", "good corporate governance", "governance",
        "manajemen risiko", "kepatuhan", "audit intern", "pengendalian intern",
    )),
    ("kelembagaan", (
        "otoritas jasa keuangan", "organisasi dan tata kerja",
        "kelembagaan", "dewan komisioner",
    )),
]

UNCLASSIFIED = "lain-lain"
DEFAULT_RULES_FILE = Path("config/kategori.yaml")
_SAFE = re.compile(r"[^a-z0-9\-]+")


def _slug(value: str, max_len: int = 60) -> str:
    slug = _SAFE.sub("-", value.lower().replace("/", "-")).strip("-")
    slug = re.sub(r"-{2,}", "-", slug)
    return slug[:max_len].strip("-") or "dokumen"


class RulesError(ValueError):
    """The rules file is unusable; the message says which line to fix."""


@dataclass
class Category:
    kode: str
    label: str
    kata_kunci: tuple[str, ...]
    kecuali: tuple[str, ...] = ()
    sektor_jdih: tuple[str, ...] = ()
    # Kode satuan kerja di nomor peraturan lama: 11/POJK.03/2016 → "03".
    # Tiap entri (kode, sejak, sampai) — arti kode berubah setelah reorganisasi OJK.
    kode_nomor: tuple[tuple[str, int | None, int | None], ...] = ()

    def matches_code(self, code: str | None, year: int | None) -> bool:
        if not code:
            return False
        for kode, sejak, sampai in self.kode_nomor:
            if kode == code and (sejak is None or (year or 0) >= sejak) \
                    and (sampai is None or (year or 9999) <= sampai):
                return True
        return False


@dataclass
class Rules:
    kategori: list[Category]
    default: str = "lain-lain"
    bobot_perihal: float = 5.0
    bobot_nomor: float = 6.0
    bobot_isi: float = 1.0
    isi_maks_per_kata: int = 3
    isi_karakter: int = 20000
    cocok: str = "kata"                 # kata = batas kata | substring (perilaku lama)
    sumber: str = "bawaan"
    versi: str | None = None
    _patterns: dict[str, re.Pattern] = field(default_factory=dict, repr=False)

    def pattern(self, kw: str) -> re.Pattern:
        if kw not in self._patterns:
            body = re.escape(kw)
            self._patterns[kw] = re.compile(rf"(?<![a-z0-9]){body}(?![a-z0-9])" if self.cocok == "kata"
                                            else body)
        return self._patterns[kw]

    def sektor_map(self) -> dict[str, str]:
        return {sektor_key(s): c.kode for c in self.kategori for s in c.sektor_jdih}

    def codes(self) -> list[str]:
        return [c.kode for c in self.kategori]


def sektor_key(label: str) -> str:
    """JDIH spells the same sektor inconsistently ("Penjaminan , dan")."""
    return re.sub(r"\s+", " ", re.sub(r"\s*,\s*", ", ", label.strip().lower()))


def builtin_rules() -> Rules:
    return Rules([Category(code, code, kws) for code, kws in CATEGORY_RULES],
                 default=UNCLASSIFIED, cocok="substring", sumber="bawaan")


def _str_list(value, where: str) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        value = [value]
    if not isinstance(value, list) or not all(isinstance(v, (str, int)) for v in value):
        raise RulesError(f"{where} harus berupa daftar teks")
    return tuple(str(v).strip().lower() for v in value if str(v).strip())


def _code_list(value, kode: str) -> tuple[tuple[str, int | None, int | None], ...]:
    out = []
    for entry in value or []:
        if isinstance(entry, (str, int)):
            entry = {"kode": entry}
        if not isinstance(entry, dict) or "kode" not in entry:
            raise RulesError(f"kategori '{kode}': kode_nomor harus berisi kode, mis. \"03\" atau {{kode: \"07\", sejak: 2024}}")
        code = str(entry["kode"]).zfill(2)
        try:
            sejak = int(entry["sejak"]) if entry.get("sejak") else None
            sampai = int(entry["sampai"]) if entry.get("sampai") else None
        except (TypeError, ValueError) as exc:
            raise RulesError(f"kategori '{kode}': sejak/sampai harus tahun") from exc
        out.append((code, sejak, sampai))
    return tuple(out)


def parse_rules(raw: dict, source: str = "yaml") -> Rules:
    if not isinstance(raw, dict) or not isinstance(raw.get("kategori"), list) or not raw["kategori"]:
        raise RulesError("berkas aturan harus punya daftar 'kategori' yang tidak kosong")
    bobot = raw.get("bobot") or {}
    cats, seen = [], set()
    for i, item in enumerate(raw["kategori"], 1):
        if not isinstance(item, dict) or not item.get("kode"):
            raise RulesError(f"kategori ke-{i}: 'kode' wajib diisi")
        kode = _slug(str(item["kode"]), 40)
        if kode in seen:
            raise RulesError(f"kategori ke-{i}: kode '{kode}' muncul dua kali")
        seen.add(kode)
        kws = _str_list(item.get("kata_kunci"), f"kategori '{kode}': kata_kunci")
        if not kws:
            raise RulesError(f"kategori '{kode}': kata_kunci tidak boleh kosong")
        cats.append(Category(kode, str(item.get("label") or kode), kws,
                             _str_list(item.get("kecuali"), f"kategori '{kode}': kecuali"),
                             tuple(str(s).strip() for s in (item.get("sektor_jdih") or [])),
                             _code_list(item.get("kode_nomor"), kode)))
    cocok = str(raw.get("cocok", "kata"))
    if cocok not in ("kata", "substring"):
        raise RulesError("'cocok' harus 'kata' atau 'substring'")
    try:
        return Rules(
            cats, default=_slug(str(raw.get("kategori_default", UNCLASSIFIED)), 40),
            bobot_perihal=float(bobot.get("perihal", 5)), bobot_nomor=float(bobot.get("nomor", 6)),
            bobot_isi=float(bobot.get("isi", 1)),
            isi_maks_per_kata=int(bobot.get("isi_maks_per_kata", 3)),
            isi_karakter=int(bobot.get("isi_karakter", 20000)),
            cocok=cocok, sumber=source, versi=str(raw.get("versi")) if raw.get("versi") else None)
    except (TypeError, ValueError) as exc:
        raise RulesError(f"bagian 'bobot' tidak valid: {exc}") from exc


_CACHE: dict[str, tuple[float, Rules]] = {}


def load_rules(path: str | Path | None = None) -> Rules:
    """Read the rules file; re-read automatically when it changes on disk.

    A missing file falls back to the built-in rules (so tests and fresh
    checkouts work); a *broken* file raises — silently classifying with
    stale rules would be worse than stopping.
    """
    p = Path(path) if path else DEFAULT_RULES_FILE
    if not p.exists():
        return builtin_rules()
    mtime = p.stat().st_mtime
    hit = _CACHE.get(str(p))
    if hit and hit[0] == mtime:
        return hit[1]
    import yaml
    try:
        raw = yaml.safe_load(p.read_text(encoding="utf-8"))
    except yaml.YAMLError as exc:
        raise RulesError(f"{p}: YAML tidak valid: {exc}") from exc
    rules = parse_rules(raw, source=str(p))
    _CACHE[str(p)] = (mtime, rules)
    return rules


_TENTANG = re.compile(r"\btentang\b", re.I)
_SATKER = re.compile(r"/\s*[A-Z]{2,8}\s*\.\s*(\d{1,2})\s*/\s*((?:19|20)\d{2})")


def number_code(metadata: RegulationMetadata) -> tuple[str | None, int | None]:
    """("03", 2016) from "11/POJK.03/2016" — the issuing department's code."""
    for blob in (metadata.number, metadata.title):
        m = _SATKER.search(blob or "")
        if m:
            return m.group(1).zfill(2), int(m.group(2))
    return None, None


def perihal_of(metadata: RegulationMetadata) -> str:
    """The subject line only — never the issuer preamble.

    "Peraturan Anggota Dewan Komisioner Otoritas Jasa Keuangan … tentang
    Laporan Bulanan Perusahaan Pembiayaan": the words before *tentang* say who
    issued it, not what it regulates, and matched 'kelembagaan' on almost every
    OJK regulation in the first version of these rules.
    """
    if metadata.subject:
        return metadata.subject
    title = metadata.title or ""
    parts = _TENTANG.split(title, maxsplit=1)
    return parts[1] if len(parts) == 2 else title


def _longest(matched: list[str]) -> list[str]:
    """One phrase, one vote: "bank umum" matched → "bank" adds nothing."""
    return [kw for kw in matched if not any(kw != o and kw in o for o in matched)]


def classify(
    metadata: RegulationMetadata,
    text: str = "",
    hint: str | None = None,
    rules: Rules | None = None,
) -> tuple[str, list[str]]:
    """Return (category, matched keywords). ``hint`` from config wins outright."""
    if hint:
        return _slug(hint), ["configured hint"]
    rules = rules or load_rules()

    # The subject line weighs heavily; the body is only a tie-breaker.
    subject = perihal_of(metadata).lower()
    body = (text or "")[: rules.isi_karakter].lower()
    code, code_year = number_code(metadata)

    scores: dict[str, tuple[float, list[str]]] = {}
    for cat in rules.kategori:
        if any(rules.pattern(x).search(subject) for x in cat.kecuali):
            continue
        hits, score = [], 0.0
        if cat.matches_code(code, code_year or metadata.year):
            score += rules.bobot_nomor
            hits.append(f"kode nomor .{code}")
        in_subject = _longest([kw for kw in cat.kata_kunci if rules.pattern(kw).search(subject)])
        for kw in in_subject:
            score += rules.bobot_perihal
            hits.append(kw)
        if rules.bobot_isi:
            body_counts = {kw: len(rules.pattern(kw).findall(body)) for kw in cat.kata_kunci
                           if not any(kw in s for s in in_subject)}
            for kw in _longest([k for k, n in body_counts.items() if n]):
                score += rules.bobot_isi * min(body_counts[kw], rules.isi_maks_per_kata)
                hits.append(kw)
        if score:
            scores[cat.kode] = (score, hits)

    if not scores:
        return rules.default, []
    best = max(scores.items(), key=lambda kv: kv[1][0])     # ties: earlier category wins
    return best[0], best[1][1][:6]


STATUS_FOLDERS = {
    "berlaku": "berlaku",
    "dicabut": "dicabut",
    "diubah": "diubah",
    "rancangan": "rancangan",
}
UNKNOWN_STATUS_FOLDER = "status-tidak-diketahui"


def status_folder(status: str | None) -> str:
    return STATUS_FOLDERS.get((status or "").strip().lower(), UNKNOWN_STATUS_FOLDER)


def kb_relative_path(metadata: RegulationMetadata, category: str,
                     filename: str, source: str = "lainnya") -> Path:
    """Build <source>/<category>/<type>/<year>/<status>/<normalised-name>.pdf.

    Source comes first because it answers "how far can I trust this?" before
    anything else: JDIH is the official register, a draft is by definition not
    law yet, an upload is whatever someone handed in. Status comes last so a
    regulation that is revoked moves one folder sideways, not across the tree.
    """
    source_dir = _slug(source or "lainnya", 40)
    doc_type = _slug(metadata.doc_type or "tanpa-jenis", 24)
    year = str(metadata.year) if metadata.year else "tanpa-tahun"

    parts: list[str] = []
    if metadata.doc_type:
        parts.append(metadata.doc_type)
    if metadata.number:
        parts.append(metadata.number)
    if metadata.subject:
        parts.append(metadata.subject[:70])
    stem = _slug("-".join(parts), 110) if parts else _slug(Path(filename).stem, 110)
    return (Path(source_dir) / _slug(category or UNCLASSIFIED, 40) / doc_type
            / year / status_folder(metadata.status) / f"{stem}.pdf")
