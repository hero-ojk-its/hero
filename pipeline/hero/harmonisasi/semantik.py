"""Kemiripan MAKNA antar pasal (#67, FR-HRM-05): "bukan sekadar kecocokan kata".

Model: paraphrase-multilingual-MiniLM-L12-v2 (384 dimensi) dijalankan LOKAL lewat ONNX Runtime
(fastembed) — tidak ada teks yang dikirim ke layanan luar, jadi aman untuk draft non-publik.
Dipilih lewat simulasi (``docs/HARMONISASI_SEMANTIK.md``): pada 45 pasangan perubahan ↔ induk,
rata-rata TF-IDF + MiniLM memberi AUC 0,922 dan pasal induk benar di peringkat #1 seluruh KB 80,3%
(TF-IDF saja 0,915 / 78,9%; e5-large 0,871 dan ±20× lebih lambat). Pada set parafrase, MiniLM
memisahkan parafrase dari pasal pelengkap paling bersih.

Opsional: tanpa fastembed/model, :func:`matriks` mengembalikan None dan harmonisasi berjalan
leksikal murni seperti sebelumnya (mode Deterministik tetap utuh).

Embedding pasal korpus disimpan per hash teks di SQLite terpisah, sehingga hanya draft baru yang
perlu dihitung per permintaan. ``hero harmonisasi siapkan-semantik`` mengisi cache sekali di server.
"""
from __future__ import annotations

import hashlib
import logging
import sqlite3
import threading
from pathlib import Path
from typing import Any

import numpy as np

log = logging.getLogger(__name__)
_LOCK = threading.Lock()
_EMBEDDER: dict[str, Any] = {}
_GAGAL: set[str] = set()


def _sha(teks: str) -> str:
    return hashlib.sha1(teks.encode("utf-8")).hexdigest()


def embedder(model: str, models_dir: Path | None):
    """Embedder lokal yang dimuat sekali per proses; None bila tidak tersedia (dicatat, tidak meledak)."""
    kunci = f"{model}@{models_dir}"
    with _LOCK:
        if kunci in _EMBEDDER:
            return _EMBEDDER[kunci]
        if kunci in _GAGAL:
            return None
        try:
            from hero.vector.embedders import SEMANTIC_MODELS, SemanticEmbedder, semantic_available

            if not semantic_available():
                raise ImportError("fastembed tidak terpasang")
            hf = (SEMANTIC_MODELS.get(model) or {"hf": model})["hf"]
            if not model_lokal_ada(Path(models_dir or "data/models"), hf):
                # Jalur permintaan tidak pernah mengunduh diam-diam (server/tes menunggu jaringan).
                raise FileNotFoundError(f"model {hf} belum ada di {models_dir} — jalankan "
                                        "'hero harmonisasi siapkan-semantik --unduh'")
            e = SemanticEmbedder(Path(models_dir or "data/models"), model=model)
        except Exception as exc:                                   # noqa: BLE001 — fitur opsional
            log.info("kemiripan makna tidak aktif (%s) — harmonisasi memakai leksikal saja", exc)
            _GAGAL.add(kunci)
            return None
        _EMBEDDER[kunci] = e
        return e


def model_lokal_ada(models_dir: Path, hf_name: str) -> bool:
    short = hf_name.split("/")[-1].lower()
    if not models_dir.is_dir():
        return False
    for p in list(models_dir.iterdir()) + (list((models_dir / "flat").iterdir())
                                           if (models_dir / "flat").is_dir() else []):
        if short in p.name.lower():
            return True
    return False


def unduh(model: str, models_dir: Path) -> str:
    """Unduh model secara eksplisit (dipanggil CLI penyiapan, bukan jalur permintaan)."""
    from hero.vector.embedders import SemanticEmbedder

    e = SemanticEmbedder(Path(models_dir), model=model)
    return e.model_name


class Cache:
    """Vektor per (model, hash teks) di berkas SQLite tersendiri — tidak mengunci katalog."""

    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self._conn() as c:
                c.execute("CREATE TABLE IF NOT EXISTS emb (model TEXT, sha TEXT, vec BLOB, "
                          "PRIMARY KEY (model, sha))")

    def _conn(self) -> sqlite3.Connection:
        c = sqlite3.connect(self.path, timeout=30)
        c.execute("PRAGMA journal_mode=WAL")
        return c

    def ambil(self, model: str, shas: list[str]) -> dict[str, np.ndarray]:
        if not self.path or not shas:
            return {}
        out: dict[str, np.ndarray] = {}
        with self._conn() as c:
            for i in range(0, len(shas), 900):
                part = shas[i:i + 900]
                q = f"SELECT sha, vec FROM emb WHERE model = ? AND sha IN ({','.join('?' * len(part))})"
                for sha, blob in c.execute(q, [model, *part]):
                    out[sha] = np.frombuffer(blob, dtype=np.float32)
        return out

    def simpan(self, model: str, pasangan: list[tuple[str, np.ndarray]]) -> None:
        if not self.path or not pasangan:
            return
        with self._conn() as c:
            c.executemany("INSERT OR REPLACE INTO emb VALUES (?, ?, ?)",
                          [(model, s, v.astype(np.float32).tobytes()) for s, v in pasangan])


def vektor(teks: list[str], cfg: dict[str, Any], *, maks_baru: int | None = None) -> np.ndarray | None:
    """Embedding L2-normal untuk ``teks`` (cache dulu). None = semantik tidak aktif / terlalu banyak
    teks yang belum ter-cache untuk dihitung dalam satu permintaan."""
    sc = cfg.get("semantik") or {}
    if (sc.get("metode") or "auto") == "mati":
        return None
    model = sc.get("model") or "minilm"
    e = embedder(model, sc.get("models_dir"))
    if e is None:
        return None
    cache = Cache(sc.get("cache"))
    shas = [_sha(t) for t in teks]
    ada = cache.ambil(model, list(dict.fromkeys(shas)))
    hilang = list(dict.fromkeys(s for s in shas if s not in ada))
    if maks_baru is not None and len(hilang) > maks_baru:
        log.warning("kemiripan makna dilewati: %d pasal belum ter-cache (> %d) — jalankan "
                    "'hero harmonisasi siapkan-semantik'", len(hilang), maks_baru)
        return None
    if hilang:
        teks_hilang = {s: t for s, t in zip(shas, teks)}
        baru = e.embed_passages([teks_hilang[s] for s in hilang])
        pas = list(zip(hilang, baru))
        cache.simpan(model, pas)
        ada.update(pas)
    return np.vstack([ada[s] for s in shas]).astype(np.float32)


def matriks(draft: list[str], korpus: list[str], cfg: dict[str, Any]) -> np.ndarray | None:
    """Kosinus makna [pasal draft × pasal korpus], atau None bila semantik tidak tersedia."""
    sc = cfg.get("semantik") or {}
    K = vektor(korpus, cfg, maks_baru=sc.get("maks_tanpa_cache", 2000))
    if K is None:
        return None
    D = vektor(draft, cfg)
    if D is None:
        return None
    return np.clip(D @ K.T, -1.0, 1.0)


def status_ringan(cfg: dict[str, Any]) -> dict[str, Any]:
    """Untuk /health: siap atau tidak TANPA memuat model (health dipanggil sering)."""
    sc = cfg.get("semantik") or {}
    if (sc.get("metode") or "auto") == "mati":
        return {"aktif": False, "alasan": "semantik.metode: mati"}
    from hero.vector.embedders import SEMANTIC_MODELS, semantic_available

    hf = (SEMANTIC_MODELS.get(sc.get("model") or "minilm") or {"hf": sc.get("model")})["hf"]
    if not semantic_available():
        return {"aktif": False, "alasan": "fastembed tidak terpasang"}
    if not model_lokal_ada(Path(sc.get("models_dir") or "data/models"), hf):
        return {"aktif": False, "alasan": f"model {hf} belum diunduh (hero harmonisasi siapkan-semantik --unduh)"}
    return {"aktif": True, "model": hf}


def status(cfg: dict[str, Any]) -> dict[str, Any]:
    sc = cfg.get("semantik") or {}
    if (sc.get("metode") or "auto") == "mati":
        return {"aktif": False, "alasan": "semantik.metode: mati"}
    e = embedder(sc.get("model") or "minilm", sc.get("models_dir"))
    return {"aktif": e is not None, "model": getattr(e, "model_name", None),
            "cache": str(sc.get("cache")) if sc.get("cache") else None}
