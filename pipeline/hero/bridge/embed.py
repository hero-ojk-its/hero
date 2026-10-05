"""Vektor per pasal untuk kolom ``articles.embedding`` (pgvector) di backend.

Tiga keputusan yang perlu diketahui sebelum membaca kodenya:

**1. Dimensi.** Kolom backend adalah ``Vector(1536)`` — dimensi OpenAI
``text-embedding-ada-002``. Model lokal HERO berdimensi 256 (LSA), 384
(MiniLM) atau 1024 (e5-large). Vektor yang lebih pendek **di-zero-pad** ke
1536. Untuk vektor ber-norma 1 ini tidak kehilangan apa pun: dot product dan
norma tidak berubah oleh nol, sehingga cosine similarity antar dua vektor
yang dipadatkan sama persis dengan sebelum dipadatkan. Yang terbuang hanya
ruang: 1536 × 4 byte per baris, sekitar 6 KB, padahal 1024 dims hanya butuh
4 KB. Rekomendasi jangka panjang ada di ``docs/INTEGRASI_BACKEND.md``:
samakan dimensi kolom dengan model yang dipakai lewat migrasi aditif.

**2. Satu vektor per pasal, bukan per jendela.** Backend menyimpan satu
embedding per baris ``articles``, sedangkan indeks vektor HERO memotong pasal
panjang menjadi jendela 80 kata (model terkecil hanya membaca 128 token).
Di sini vektor pasal = rata-rata vektor jendelanya, dinormalisasi ulang —
sehingga seluruh isi pasal terwakili, bukan paragraf pertamanya saja. Indeks
jendela tetap hidup di basis data vektor HERO; perbandingan keduanya diukur
oleh ``hero bench vektor``.

**3. LSA butuh model yang sudah dilatih.** Vektor LSA hanya sebanding bila
berasal dari satu ruang TF-IDF/SVD yang sama. Jembatan memuat
``data/vectors/lsa.pkl`` hasil ``hero vector build``; ia **tidak** melatih
ulang per dokumen, karena vektor dari ruang berbeda tidak bisa dibandingkan
satu sama lain dan pencarian di backend akan hening-hening salah.
"""
from __future__ import annotations

import logging
from pathlib import Path

import numpy as np

from hero.bridge.config import BridgeSettings
from hero.config import Settings
from hero.vector.chunking import windows

log = logging.getLogger("hero.bridge.embed")


class EmbedderUnavailable(RuntimeError):
    """Embedder yang diminta tidak siap — dengan cara memperbaikinya di pesannya."""


def pad_to(vec: np.ndarray, dim: int) -> list[float]:
    """Zero-pad ke ``dim``. Cosine similarity tidak berubah (lihat docstring modul)."""
    v = np.asarray(vec, dtype=np.float32).reshape(-1)
    if v.size > dim:
        raise ValueError(f"vektor {v.size} dimensi tidak muat di kolom {dim} dimensi — "
                         f"ubah kolom backend atau pilih model yang lebih kecil")
    if v.size == dim:
        return [float(x) for x in v]
    out = np.zeros(dim, dtype=np.float32)
    out[:v.size] = v
    return [float(x) for x in out]


def unpad(vec: list[float], dim: int) -> np.ndarray:
    """Kebalikan ``pad_to``: ambil ``dim`` komponen pertama."""
    return np.asarray(vec[:dim], dtype=np.float32)


def _mean_unit(rows: np.ndarray) -> np.ndarray:
    """Rata-rata baris ber-norma 1, dinormalisasi ulang (0 bila semuanya nol)."""
    if rows.size == 0:
        return np.zeros(0, dtype=np.float32)
    m = np.asarray(rows, dtype=np.float32).mean(axis=0)
    n = float(np.linalg.norm(m))
    return m / n if n else m


class ArticleEmbedder:
    """Teks pasal → vektor siap kirim ke backend (sudah dipadatkan ke ``backend_dim``)."""

    def __init__(self, settings: Settings, bridge: BridgeSettings | None = None):
        self.settings = settings
        self.bridge = bridge or BridgeSettings()
        self.kind = (self.bridge.embedder or "none").lower()
        self.backend_dim = int(self.bridge.backend_dim)
        self._emb = None
        if self.kind not in ("none", "lsa", "semantic"):
            raise EmbedderUnavailable(f"embedder '{self.kind}' tidak dikenal — "
                                      f"pilih: lsa | semantic | none")

    # -- siklus hidup ----------------------------------------------------
    @property
    def enabled(self) -> bool:
        return self.kind != "none"

    def load(self):
        """Muat model sekali per proses. Dipanggil otomatis saat pemakaian pertama."""
        if self._emb is not None or not self.enabled:
            return self._emb
        from hero.vector import vector_paths
        from hero.vector.embedders import LsaEmbedder, SemanticEmbedder, semantic_available

        paths = vector_paths(self.settings)
        if self.kind == "lsa":
            lsa_path: Path = paths["lsa"]
            if not lsa_path.exists():
                raise EmbedderUnavailable(
                    f"model LSA belum ada di {lsa_path}. Jalankan 'hero vector build --lsa-only' "
                    f"sekali di workspace ini — vektor LSA hanya sebanding bila berasal dari satu "
                    f"ruang TF-IDF/SVD yang sama, jadi jembatan tidak melatihnya ulang per dokumen.")
            self._emb = LsaEmbedder.load(lsa_path)
        else:
            if not semantic_available():
                raise EmbedderUnavailable(
                    "fastembed belum terpasang. Pasang dengan: pip install -e '.[semantic]' "
                    "— atau setel bridge.embedder: lsa (deterministik) / none.")
            self._emb = SemanticEmbedder(paths["models"], model=self.settings.vector.semantic_model)
        log.info("embedder jembatan: %s (%s dims) → kolom %s dims",
                 self.name, self.source_dim, self.backend_dim)
        return self._emb

    @property
    def name(self) -> str:
        if not self.enabled:
            return "none"
        if self.kind == "semantic":
            return f"semantic:{self.settings.vector.semantic_model}"
        return "lsa"

    @property
    def source_dim(self) -> int:
        return int(getattr(self.load(), "dim", 0)) if self.enabled else 0

    @property
    def mode(self) -> str:
        """``deterministik`` | ``ai-assisted`` | ``nonaktif`` — untuk pelaporan."""
        if not self.enabled:
            return "nonaktif"
        return "deterministik" if self.kind == "lsa" else "ai-assisted"

    # -- pemakaian -------------------------------------------------------
    def article_vectors(self, texts: list[str]) -> list[list[float] | None]:
        """Satu vektor terpadat per teks pasal; ``None`` bila embedder nonaktif."""
        if not self.enabled or not texts:
            return [None] * len(texts)
        emb = self.load()
        # Satu panggilan embed untuk semua jendela dari semua pasal: model ONNX
        # jauh lebih cepat per batch daripada per potongan.
        flat: list[str] = []
        spans: list[tuple[int, int]] = []
        for t in texts:
            parts = windows(t) or ([t.strip()] if t.strip() else [])
            start = len(flat)
            flat.extend(parts)
            spans.append((start, len(flat)))
        if not flat:
            return [None] * len(texts)
        rows = (emb.embed_passages(flat) if hasattr(emb, "embed_passages") else emb.embed(flat))
        out: list[list[float] | None] = []
        for start, end in spans:
            if end <= start:
                out.append(None)
                continue
            out.append(pad_to(_mean_unit(rows[start:end]), self.backend_dim))
        return out

    def query_vector(self, text: str) -> list[float]:
        """Vektor kueri terpadat — prefix asimetris e5 ikut diterapkan bila ada."""
        emb = self.load()
        if emb is None:
            raise EmbedderUnavailable("embedder nonaktif: tidak ada vektor kueri")
        return pad_to(np.asarray(emb.embed_query(text), dtype=np.float32), self.backend_dim)
