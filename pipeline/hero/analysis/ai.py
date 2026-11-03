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


ANTHROPIC, GEMINI = "anthropic", "gemini"
_ALIAS = {"anthropic": ANTHROPIC, "claude": ANTHROPIC,
          "gemini": GEMINI, "google": GEMINI, "google-genai": GEMINI, "google-ai": GEMINI}
_SDK = {ANTHROPIC: ("anthropic", 'pip install -e ".[ai]"'),
        GEMINI: ("google.genai", 'pip install -e ".[ai-gemini]"')}


def provider_of(settings: AnalysisSettings) -> str:
    """Penyedia yang dipakai: dari ``ai_provider``, atau ditebak dari nama model.

    Menebak dari nama model membuat "ganti ai_model ke gemini-…" cukup dengan
    satu baris konfigurasi, dan menghindari keadaan tak masuk akal seperti
    provider anthropic dengan model gemini.
    """
    raw = (getattr(settings, "ai_provider", "") or "").strip().lower()
    if raw:
        if raw not in _ALIAS:
            raise ValueError(f"analysis.ai_provider '{raw}' tidak dikenal "
                             f"(pilih: anthropic, gemini)")
        return _ALIAS[raw]
    return GEMINI if (settings.ai_model or "").lower().startswith("gemini") else ANTHROPIC


def _tanpa_additional_properties(node: Any) -> Any:
    """Skema untuk Gemini: ``additionalProperties`` tidak didukung di sana.

    Skema yang sama dipakai dua penyedia supaya kontrak keluaran tidak bercabang;
    yang berbeda hanya kata kunci yang tidak dikenal Gemini dan akan membuat
    permintaannya ditolak sebelum model dipanggil.
    """
    if isinstance(node, dict):
        return {k: _tanpa_additional_properties(v) for k, v in node.items()
                if k != "additionalProperties"}
    if isinstance(node, list):
        return [_tanpa_additional_properties(v) for v in node]
    return node


def credentials_hint(provider: str = ANTHROPIC) -> str | None:
    """Best local guess; the SDK also reads `ant auth login` profiles, which we
    cannot see here, so absence of env vars is reported as 'belum terlihat'."""
    if provider == GEMINI:
        if os.environ.get("GOOGLE_API_KEY") or os.environ.get("GEMINI_API_KEY"):
            return "variabel lingkungan"
        if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS"):
            return "kredensial akun layanan Google"
        return None
    if os.environ.get("ANTHROPIC_API_KEY") or os.environ.get("ANTHROPIC_AUTH_TOKEN"):
        return "variabel lingkungan"
    if os.path.isdir(os.path.expanduser("~/.config/anthropic")):
        return "profil ant auth"
    return None


class _TidakPernahTerjadi(Exception):
    """Penampung ``except`` saat SDK tidak terpasang: tidak ada yang melemparnya."""


_KOSONG = dict.fromkeys(("auth", "izin", "laju", "status", "koneksi"), _TidakPernahTerjadi)


def _sdk_errors(provider: str = ANTHROPIC) -> dict[str, type[BaseException] | tuple[type[BaseException], ...]]:
    """Kelas galat SDK bila ada; penampung yang tidak pernah terpicu bila tidak.

    Tanpa SDK, galat apa pun dari klien yang disuntikkan akan naik ke pemanggil
    apa adanya — itu memang yang benar: kita tidak tahu artinya, jadi jangan
    menyamarkannya sebagai "layanan AI tidak tersedia"."""
    if provider == GEMINI:
        # google-genai menyatukan galat HTTP di APIError (ClientError/ServerError
        # turunannya), tanpa kelas terpisah per sebab. Jadi semuanya ditangkap di
        # satu pintu dan dipilah dari kode statusnya di ``_pilah_galat_gemini``.
        try:
            from google.genai import errors
        except ImportError:
            return dict(_KOSONG)
        return dict(_KOSONG, status=errors.APIError)
    try:
        import anthropic
    except ImportError:
        return dict(_KOSONG)
    return {"auth": anthropic.AuthenticationError,
            "izin": anthropic.PermissionDeniedError,
            "laju": anthropic.RateLimitError,
            "status": anthropic.APIStatusError,
            "koneksi": anthropic.APIConnectionError}


def _pilah_galat_gemini(exc: BaseException) -> str:
    """Pesan yang bisa dibaca manusia dari satu APIError Google.

    Kodenya dibaca dari atribut, bukan dari teks pesan: 401/403 berarti
    kredensial atau izin, 429 berarti kuota — pembedaan yang menentukan apakah
    operator perlu memperbaiki kunci atau sekadar menunggu.
    """
    kode = getattr(exc, "code", None) or getattr(exc, "status_code", None)
    try:
        kode = int(kode)
    except (TypeError, ValueError):
        kode = None
    if kode in (401, 403):
        return "Kredensial Google AI tidak valid atau tidak punya izin untuk model ini"
    if kode == 429:
        return "Kuota/batas laju Google AI tercapai — coba lagi nanti"
    if kode == 404:
        return "Model Gemini tidak ditemukan — periksa analysis.ai_model"
    if kode and 500 <= kode < 600:
        return f"Layanan Google AI sedang bermasalah (galat {kode})"
    return f"Galat API Google AI {kode or '?'}"


class AiNarrator:
    def __init__(self, settings: AnalysisSettings, client: Any | None = None):
        self.settings = settings
        self._client = client

    @property
    def provider(self) -> str:
        return provider_of(self.settings)

    def status(self) -> dict[str, Any]:
        import importlib

        prov = self.provider
        modul, pasang = _SDK[prov]
        try:
            importlib.import_module(modul)
            sdk = True
        except ImportError:
            sdk = False
        cred = credentials_hint(prov) if self._client is None else "klien disuntikkan"
        ready = self.settings.ai_enabled and sdk and cred is not None
        nama = "Claude" if prov == ANTHROPIC else "Google AI"
        if not self.settings.ai_enabled:
            summary = "tersedia, dinonaktifkan di konfigurasi (analysis.ai_enabled: false)"
        elif not sdk:
            summary = f"diaktifkan, tetapi SDK {modul} belum terpasang ({pasang})"
        elif cred is None:
            summary = f"diaktifkan, tetapi kredensial {nama} belum terlihat"
        else:
            summary = f"aktif ({prov}/{self.settings.ai_model}, kredensial: {cred})"
        return {"aktif": ready, "sdk": sdk, "kredensial": cred, "penyedia": prov,
                "model": self.settings.ai_model, "ringkas": summary}

    def _get_client(self):
        if self._client is None:
            if self.provider == GEMINI:
                from google import genai
                self._client = genai.Client()
            else:
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
            modul, pasang = _SDK[self.provider]
            return AiResult("deterministik", f"SDK {modul} belum terpasang — {pasang}")
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
        """Panggil penyedia, lalu verifikasi hasilnya dengan aturan yang sama.

        Hanya bentuk panggilan dan pembacaan galat yang berbeda antar penyedia.
        ``build_facts`` dan ``verify`` tidak bercabang: jaminan "model hanya
        boleh memakai fakta yang diberikan" harus identik di Claude maupun
        Gemini, kalau tidak jaminannya bukan jaminan.
        """
        user = ("FAKTA (JSON):\n" + json.dumps(facts, ensure_ascii=False, indent=1)
                + "\n\nTulis ringkasan dan poin_kunci sesuai aturan.")
        if self.provider == GEMINI:
            text, usage, model, gagal = self._minta_gemini(client, user)
        else:
            text, usage, model, gagal = self._minta_anthropic(client, user)
        if gagal is not None:
            return AiResult("deterministik", gagal, model=model, usage=usage)
        return self._periksa(text, usage, model, a, facts)

    def _minta_anthropic(self, client, user: str):
        # Kelas galat SDK diambil lewat ``_sdk_errors`` dan bukan lewat
        # ``import anthropic`` di sini: klien boleh disuntikkan (uji, atau
        # gateway lain), dan menuntut SDK hanya untuk membaca nama galatnya
        # akan menjatuhkan jalur yang justru dirancang untuk tetap jalan tanpa
        # layanan AI (NFR-04).
        err = _sdk_errors(ANTHROPIC)
        s = self.settings
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
        except err["auth"]:
            return None, {}, None, "Kredensial Claude tidak valid atau belum diatur"
        except err["izin"]:
            return None, {}, None, "Kredensial tidak memiliki izin untuk model ini"
        except err["laju"]:
            return None, {}, None, "Batas laju API tercapai — coba lagi nanti"
        except err["status"] as exc:
            return None, {}, None, f"Galat API {getattr(exc, 'status_code', '?')}"
        except err["koneksi"]:
            return None, {}, None, "Tidak dapat terhubung ke layanan AI"

        usage = {k: getattr(response.usage, k, None) for k in
                 ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens")}
        model = getattr(response, "model", s.ai_model)
        if response.stop_reason == "refusal":
            cat = getattr(getattr(response, "stop_details", None), "category", None)
            return None, usage, model, f"Model menolak permintaan (kategori: {cat})"
        if response.stop_reason == "max_tokens":
            return None, usage, model, "Keluaran model terpotong (max_tokens)"
        text = next((b.text for b in response.content if getattr(b, "type", None) == "text"), None)
        return text, usage, model, None

    def _minta_gemini(self, client, user: str):
        err = _sdk_errors(GEMINI)
        s = self.settings
        try:
            response = client.models.generate_content(
                model=s.ai_model,
                contents=user,
                config={
                    "system_instruction": SYSTEM_PROMPT,
                    "response_mime_type": "application/json",
                    # Gemini menolak 'additionalProperties', jadi dibuang di sini.
                    "response_schema": _tanpa_additional_properties(OUTPUT_SCHEMA),
                    # Parafrase fakta, bukan karangan: jangan beri ruang kreatif.
                    "temperature": 0,
                },
            )
        except err["status"] as exc:
            return None, {}, None, _pilah_galat_gemini(exc)

        meta = getattr(response, "usage_metadata", None)
        usage = {
            "input_tokens": getattr(meta, "prompt_token_count", None),
            "output_tokens": getattr(meta, "candidates_token_count", None),
            "cache_read_input_tokens": getattr(meta, "cached_content_token_count", None),
            "cache_creation_input_tokens": None,
        }
        model = getattr(response, "model_version", None) or s.ai_model
        alasan = _finish_reason_gemini(response)
        if alasan is not None:
            return None, usage, model, alasan
        return getattr(response, "text", None), usage, model, None

    def _periksa(self, text: str | None, usage: dict[str, Any], model: str | None,
                 a: AnalysisV2, facts: list[dict[str, Any]]) -> AiResult:
        s = self.settings
        try:
            output = json.loads(text or "")
        except ValueError:
            return AiResult("deterministik", "Keluaran model bukan JSON yang valid", usage=usage)
        problems = verify(output, facts)
        if problems:
            log.warning("AI output rejected for %s: %s", a.doc_id, problems)
            return AiResult("deterministik", "Keluaran AI ditolak verifikasi — menampilkan hasil Deterministik",
                            model=model or s.ai_model, pelanggaran=problems, usage=usage)
        pasal = {f["id"]: f.get("pasal") for f in facts}
        ringkasan = [{"kalimat": x["kalimat"], "fakta": x["fakta"],
                      "rujukan": sorted({pasal[i] for i in x["fakta"] if pasal.get(i)})}
                     for x in output["ringkasan"]]
        return AiResult("ai", None, ringkasan, {x["fakta"]: x["parafrase"] for x in output["poin_kunci"]},
                        model or s.ai_model, usage=usage)


def _finish_reason_gemini(response: Any) -> str | None:
    """Alasan berhenti yang membuat keluaran tak terpakai, atau None bila wajar.

    Kandidat kosong juga dihitung gagal: itu yang terjadi saat filter keamanan
    Google memblokir permintaan, dan tanpa pemeriksaan ini ``response.text``
    bernilai None lalu muncul sebagai "bukan JSON yang valid" — pesan yang
    menyesatkan operator.
    """
    kandidat = getattr(response, "candidates", None) or []
    if not kandidat:
        blokir = getattr(getattr(response, "prompt_feedback", None), "block_reason", None)
        return f"Permintaan diblokir filter Google AI (alasan: {blokir or '?'})"
    alasan = getattr(kandidat[0], "finish_reason", None)
    nama = getattr(alasan, "name", None) or (str(alasan) if alasan is not None else "")
    nama = nama.upper()
    if nama in ("", "STOP", "FINISH_REASON_STOP"):
        return None
    if "MAX_TOKEN" in nama:
        return "Keluaran model terpotong (max_tokens)"
    if "SAFETY" in nama or "BLOCK" in nama or "RECITATION" in nama:
        return f"Model menolak permintaan (kategori: {nama})"
    return f"Model berhenti tidak wajar ({nama})"
