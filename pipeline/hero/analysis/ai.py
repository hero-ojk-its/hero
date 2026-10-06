"""Mode AI-Assisted (URD 3.1): narasi natural di atas fakta Deterministik.

The model is *not* given the regulation. It is given the facts v2 already
extracted — each with an id and the Pasal it came from — and asked to write
plain Indonesian that cites those ids. Then the output is checked:

* every sentence cites at least one fact, and every cited id exists;
* every number in a sentence occurs in the facts it cites (a changed
  deadline — "30 hari" becoming "15 hari" — is the worst thing a regulation
  summary can do, so numbers are checked mechanically, not trusted);
* every "Pasal N" mentioned belongs to a cited fact.

Anything that fails falls back to the Deterministic output, with the
reason. So does a refusal, an API error, missing credentials, or the
feature being switched off: the system always answers (URD 3.1), and AI
text is only shown when it can be traced to the law.

Confidentiality: documents classified ``internal``/``rahasia`` are never
sent unless ``analysis.ai_allow_internal`` is explicitly set.
"""
from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
from dataclasses import dataclass, field
from typing import Any

from hero.analysis.structured import AnalysisV2
from hero.config import AnalysisSettings

log = logging.getLogger(__name__)

PROMPT_VERSION = "p1"

SYSTEM_PROMPT = """Anda membantu analis regulasi di Otoritas Jasa Keuangan memahami sebuah peraturan dengan cepat.

Anda menerima daftar FAKTA yang sudah diekstrak dari satu peraturan. Setiap fakta punya id (I1, K1, F7, …) dan, bila ada, rujukan pasalnya. Tulis dua hal dalam bahasa Indonesia yang jelas dan wajar untuk pembaca profesional non-hukum:

1. "ringkasan": 4–7 kalimat yang menjelaskan apa yang diatur peraturan ini, siapa yang terdampak, kewajiban dan larangan terpentingnya, sanksinya, serta kapan berlaku dan apa yang dicabutnya — sejauh ada di fakta.
2. "poin_kunci": untuk setiap fakta berawalan F yang diberikan, satu parafrase singkat (maksimal 30 kata) yang mudah dipahami.

Aturan yang tidak boleh dilanggar, karena hasil Anda diperiksa otomatis dan ditolak bila melanggar:
- Setiap kalimat ringkasan harus mencantumkan id fakta yang menjadi dasarnya di "fakta". Jangan menyatakan apa pun yang tidak ada di fakta.
- Salin setiap angka, tanggal, persentase, jangka waktu, dan nomor peraturan persis seperti di fakta. Jangan membulatkan atau menghitung ulang.
- Jangan menyebut nomor pasal yang tidak ada di fakta yang Anda rujuk.
- Bila fakta menyatakan substansi berada di Lampiran, katakan itu; jangan menebak isi Lampiran.
- Ini bahan kerja internal, bukan nasihat hukum: jangan menilai, merekomendasikan, atau menambahkan konteks dari luar fakta."""

OUTPUT_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "ringkasan": {"type": "array", "items": {
            "type": "object",
            "properties": {"kalimat": {"type": "string"},
                           "fakta": {"type": "array", "items": {"type": "string"}}},
            "required": ["kalimat", "fakta"], "additionalProperties": False}},
        "poin_kunci": {"type": "array", "items": {
            "type": "object",
            "properties": {"fakta": {"type": "string"}, "parafrase": {"type": "string"}},
            "required": ["fakta", "parafrase"], "additionalProperties": False}},
    },
    "required": ["ringkasan", "poin_kunci"],
    "additionalProperties": False,
}

SCHEMA = """
CREATE TABLE IF NOT EXISTS analysis_ai (
    doc_id TEXT NOT NULL, fakta_hash TEXT NOT NULL, model TEXT NOT NULL, prompt TEXT NOT NULL,
    status TEXT NOT NULL, hasil TEXT, alasan TEXT, usage TEXT, dibuat TEXT NOT NULL,
    PRIMARY KEY (doc_id, fakta_hash, model, prompt));
"""

_NUM = re.compile(r"\d+(?:[.,]\d+)?")
_PASAL = re.compile(r"Pasal\s+(\d+[A-Z]?)")


@dataclass
class AiResult:
    status: str                      # 'ai' | 'deterministik'
    alasan: str | None
    ringkasan: list[dict[str, Any]] = field(default_factory=list)
    poin_kunci: dict[str, str] = field(default_factory=dict)
    model: str | None = None
    pelanggaran: list[str] = field(default_factory=list)
    usage: dict[str, Any] = field(default_factory=dict)
    dari_cache: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {"status": self.status, "alasan": self.alasan, "ringkasan": self.ringkasan,
                "poin_kunci": self.poin_kunci, "model": self.model, "pelanggaran": self.pelanggaran,
                "usage": self.usage, "dari_cache": self.dari_cache}


# ---------------------------------------------------------------------------
def build_facts(a: AnalysisV2, max_points: int = 24) -> list[dict[str, Any]]:
    """The only material the model may use. Ids are stable per analysis."""
    ident = a.identitas
    facts: list[dict[str, Any]] = []

    def add(fid, teks, pasal=None):
        if teks:
            facts.append({"id": fid, "teks": teks, "pasal": pasal})

    add("I1", f"Jenis dan nomor: {ident.get('jenis') or '-'} Nomor {ident.get('nomor') or '-'}")
    add("I2", f"Tentang: {ident.get('tentang') or '-'}")
    add("I3", f"Status: {ident.get('status') or 'tidak diketahui'}")
    if ident.get("tanggal_terbit"):
        add("I4", f"Tanggal terbit: {ident['tanggal_terbit']}")
    if a.kerangka:
        add("K1", "Kerangka: " + "; ".join(f"{k['bab']} {k['judul']} ({k['pasal']})" for k in a.kerangka))
    if a.subjek_diatur:
        add("K2", "Pihak yang paling banyak dibebani kewajiban: " + ", ".join(s["subjek"] for s in a.subjek_diatur[:4]))
    if a.sanksi:
        add("K3", "Jenis sanksi yang disebut: " + ", ".join(a.sanksi))
    if a.lampiran.get("berat_lampiran"):
        add("K4", "Substansi utama berada di Lampiran, bukan di batang tubuh. Judul bagian Lampiran: "
            + ("; ".join(a.lampiran["judul_bagian"][:8]) or "tidak terbaca"))
    for p in a.poin_utama(max_points):
        add(p.id, f"[{p.kategori}] {p.teks}", p.pasal)
    return facts


def verify(output: dict[str, Any], facts: list[dict[str, Any]]) -> list[str]:
    """Return every rule the model broke; empty means the output is usable."""
    by_id = {f["id"]: f for f in facts}
    problems: list[str] = []
    sentences = output.get("ringkasan") or []
    if not 2 <= len(sentences) <= 10:
        problems.append(f"jumlah kalimat ringkasan {len(sentences)} di luar 2–10")
    for i, s in enumerate(sentences, 1):
        ids = s.get("fakta") or []
        if not ids:
            problems.append(f"kalimat {i} tidak merujuk fakta")
            continue
        unknown = [x for x in ids if x not in by_id]
        if unknown:
            problems.append(f"kalimat {i} merujuk fakta yang tidak ada: {unknown}")
            continue
        source = " ".join(f"{by_id[x]['teks']} {by_id[x].get('pasal') or ''}" for x in ids)
        src_nums = set(_NUM.findall(source))
        extra = [n for n in _NUM.findall(s.get("kalimat", "")) if n not in src_nums]
        if extra:
            problems.append(f"kalimat {i} memuat angka yang tidak ada di faktanya: {extra}")
        src_pasal = set(_PASAL.findall(source))
        bad_pasal = [n for n in _PASAL.findall(s.get("kalimat", "")) if n not in src_pasal]
        if bad_pasal:
            problems.append(f"kalimat {i} menyebut pasal di luar faktanya: {bad_pasal}")
    for item in output.get("poin_kunci") or []:
        f = by_id.get(item.get("fakta"))
        if f is None:
            problems.append(f"parafrase merujuk fakta yang tidak ada: {item.get('fakta')}")
            continue
        extra = [n for n in _NUM.findall(item.get("parafrase", "")) if n not in set(_NUM.findall(f["teks"]))]
        if extra:
            problems.append(f"parafrase {item['fakta']} memuat angka baru: {extra}")
    return problems


def _facts_hash(facts: list[dict[str, Any]]) -> str:
    return hashlib.sha256(json.dumps(facts, ensure_ascii=False, sort_keys=True).encode()).hexdigest()[:20]


def credentials_hint() -> str | None:
    """Best local guess; the SDK also reads `ant auth login` profiles, which we
    cannot see here, so absence of env vars is reported as 'belum terlihat'."""
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "variabel lingkungan"
    if os.path.isdir(os.path.expanduser("~/.config/anthropic")):
        return "profil ant auth"
    return None


class AiNarrator:
    def __init__(self, settings: AnalysisSettings, client: Any | None = None):
        self.settings = settings
        self._client = client

    def status(self) -> dict[str, Any]:
        try:
            import anthropic  # noqa: F401
            sdk = True
        except ImportError:
            sdk = False
        cred = credentials_hint() if self._client is None else "klien disuntikkan"
        ready = self.settings.ai_enabled and sdk and cred is not None
        if not self.settings.ai_enabled:
            summary = "tersedia, dinonaktifkan di konfigurasi (analysis.ai_enabled: false)"
        elif not sdk:
            summary = "diaktifkan, tetapi SDK anthropic belum terpasang (pip install -e \".[ai]\")"
        elif cred is None:
            summary = "diaktifkan, tetapi kredensial Claude belum terlihat"
        else:
            summary = f"aktif ({self.settings.ai_model}, kredensial: {cred})"
        return {"aktif": ready, "sdk": sdk, "kredensial": cred, "model": self.settings.ai_model,
                "ringkas": summary}

    def _get_client(self):
        if self._client is None:
            import anthropic
            self._client = anthropic.Anthropic(max_retries=2, timeout=120.0)
        return self._client

    def narrate(self, a: AnalysisV2, *, akses: str = "publik", conn: sqlite3.Connection | None = None,
                force: bool = False) -> AiResult:
        s = self.settings
        if not s.ai_enabled and not force:
            return AiResult("deterministik", "Mode AI-Assisted dinonaktifkan (analysis.ai_enabled: false)")
        if (akses or "publik") != "publik" and not s.ai_allow_internal:
            return AiResult("deterministik", f"Dokumen berklasifikasi '{akses}' tidak dikirim ke layanan AI "
                                             "eksternal (analysis.ai_allow_internal: false)")
        facts = build_facts(a, s.ai_max_facts)
        fhash = _facts_hash(facts)
        if conn is not None:
            conn.executescript(SCHEMA)
            row = conn.execute("SELECT status, hasil, alasan, usage FROM analysis_ai WHERE doc_id = ? AND "
                               "fakta_hash = ? AND model = ? AND prompt = ? AND status = 'ai'",
                               (a.doc_id, fhash, s.ai_model, PROMPT_VERSION)).fetchone()
            if row:
                d = json.loads(row[1])
                return AiResult("ai", None, d["ringkasan"], d["poin_kunci"], s.ai_model,
                                usage=json.loads(row[3] or "{}"), dari_cache=True)
        try:
            client = self._get_client()
        except ImportError:
            return AiResult("deterministik", "SDK anthropic belum terpasang — pip install -e \".[ai]\"")
        result = self._call(client, a, facts)
        if conn is not None:
            with conn:
                conn.execute("INSERT OR REPLACE INTO analysis_ai VALUES (?, ?, ?, ?, ?, ?, ?, ?, datetime('now'))",
                             (a.doc_id, fhash, s.ai_model, PROMPT_VERSION, result.status,
                              json.dumps({"ringkasan": result.ringkasan, "poin_kunci": result.poin_kunci},
                                         ensure_ascii=False),
                              result.alasan, json.dumps(result.usage)))
        return result

    def _call(self, client, a: AnalysisV2, facts: list[dict[str, Any]]) -> AiResult:
        import anthropic

        s = self.settings
        user = ("FAKTA (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
                + "\n\nTulis ringkasan dan poin_kunci sesuai aturan.")
        try:
            response = client.beta.messages.create(
                model=s.ai_model,
                max_tokens=16000,
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
                system=[{"type": "text", "text": SYSTEM_PROMPT, "cache_control": {"type": "ephemeral"}}],
                messages=[{"role": "user", "content": user}],
                output_config={"effort": s.ai_effort,
                               "format": {"type": "json_schema", "schema": OUTPUT_SCHEMA}},
            )
        except anthropic.AuthenticationError:
            return AiResult("deterministik", "Kredensial Claude tidak valid atau belum diatur")
        except anthropic.PermissionDeniedError:
            return AiResult("deterministik", "Kredensial tidak memiliki izin untuk model ini")
        except anthropic.RateLimitError:
            return AiResult("deterministik", "Batas laju API tercapai — coba lagi nanti")
        except anthropic.APIStatusError as exc:
            return AiResult("deterministik", f"Galat API {exc.status_code}")
        except anthropic.APIConnectionError:
            return AiResult("deterministik", "Tidak dapat terhubung ke layanan AI")

        usage = {k: getattr(response.usage, k, None) for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        if response.stop_reason == "refusal":
            cat = getattr(getattr(response, "stop_details", None), "category", None)
            return AiResult("deterministik", f"Model menolak permintaan (kategori: {cat})", usage=usage)
        if response.stop_reason == "max_tokens":
            return AiResult("deterministik", "Keluaran model terpotong (max_tokens)", usage=usage)
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        try:
            output = json.loads(text or "")
        except ValueError:
            return AiResult("deterministik", "Keluaran model bukan JSON yang valid", usage=usage)
        problems = verify(output, facts)
        if problems:
            log.warning("AI output rejected for %s: %s", a.doc_id, problems)
            return AiResult("deterministik", "Keluaran AI ditolak verifikasi — menampilkan hasil Deterministik",
                            model=getattr(response, "model", s.ai_model), pelanggaran=problems, usage=usage)
        pasal = {f["id"]: f.get("pasal") for f in facts}
        ringkasan = [{"kalimat": x["kalimat"], "fakta": x["fakta"],
                      "rujukan": sorted({pasal[i] for i in x["fakta"] if pasal.get(i)})}
                     for x in output["ringkasan"]]
        return AiResult("ai", None, ringkasan, {x["fakta"]: x["parafrase"] for x in output["poin_kunci"]},
                        getattr(response, "model", s.ai_model), usage=usage)
