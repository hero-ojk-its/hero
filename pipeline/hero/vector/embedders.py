"""Text → vector. Two interchangeable embedders, deliberately different in kind.

``lsa``      TF-IDF followed by truncated SVD (Latent Semantic Analysis).
             Pure linear algebra fitted on this corpus: no model download, no
             AI service, bit-for-bit reproducible. It is the vector option
             that satisfies the *Deterministic* mode (URD 3.1) — proof that a
             vector database is not the same thing as "using AI".

``semantic`` A multilingual sentence-transformer (paraphrase-multilingual-
             MiniLM-L12-v2, 384 dims) run locally through ONNX Runtime. It
             recognises that "wajib menyampaikan laporan" and "diwajibkan
             melaporkan" mean the same thing, which LSA only partly can. It
             belongs to the *AI-Assisted* mode: optional, switchable off, and
             the system keeps working without it.

Both return L2-normalised float32 rows, so cosine similarity is a dot
product everywhere downstream.
"""
from __future__ import annotations

import pickle
from pathlib import Path
from typing import Protocol

import numpy as np

# Selectable in config/sources.yaml → vector.semantic_model. Retrieval-trained
# models (e5) expect asymmetric prefixes: the query and the passages it should
# find are embedded differently. Leaving them out quietly degrades ranking.
SEMANTIC_MODELS: dict[str, dict] = {
    "minilm": {"hf": "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
               "dim": 384, "query": "", "passage": "", "ukuran_gb": 0.22},
    "e5-large": {"hf": "intfloat/multilingual-e5-large",
                 "dim": 1024, "query": "query: ", "passage": "passage: ", "ukuran_gb": 2.24},
}
SEMANTIC_MODEL = SEMANTIC_MODELS["minilm"]["hf"]


class Embedder(Protocol):
    name: str
    dim: int
    mode: str        # 'deterministik' | 'ai-assisted'

    def embed(self, texts: list[str]) -> np.ndarray: ...
    def embed_query(self, text: str) -> np.ndarray: ...
    def embed_passages(self, texts: list[str]) -> np.ndarray: ...


def _normalise(m: np.ndarray) -> np.ndarray:
    m = np.asarray(m, dtype=np.float32)
    norms = np.linalg.norm(m, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    return m / norms


class LsaEmbedder:
    """TF-IDF (word 1–2 grams, sublinear tf) → SVD. Must be ``fit`` on the corpus."""

    name = "lsa"
    mode = "deterministik"

    def __init__(self, dim: int = 256, seed: int = 42, *, fit_sample: int | None = None,
                 max_features: int | None = None):
        # fit_sample / max_features bound memory on large corpora: counting
        # bigrams peaks at ~700 MB for 7.8k chunks (SPIKE #42), so 80k chunks
        # on a 2 GB server must fit on a sample and cap the vocabulary.
        self.dim = dim
        self.seed = seed
        self.fit_sample = fit_sample
        self.max_features = max_features
        self._tfidf = None
        self._svd = None

    def fit(self, texts: list[str]) -> "LsaEmbedder":
        from sklearn.decomposition import TruncatedSVD
        from sklearn.feature_extraction.text import TfidfVectorizer

        self._tfidf = TfidfVectorizer(ngram_range=(1, 2), min_df=2, max_df=0.6,
                                      sublinear_tf=True, strip_accents="unicode",
                                      token_pattern=r"(?u)\b[a-zA-Z][a-zA-Z]+\b",
                                      max_features=self.max_features, dtype=np.float32)
        if self.fit_sample and len(texts) > self.fit_sample:
            import random
            texts = random.Random(self.seed).sample(list(texts), self.fit_sample)
        x = self._tfidf.fit_transform(texts)
        # SVD cannot have more components than features/rows.
        k = max(2, min(self.dim, x.shape[1] - 1, x.shape[0] - 1))
        self._svd = TruncatedSVD(n_components=k, random_state=self.seed, algorithm="randomized")
        self._svd.fit(x)
        self.dim = k
        return self

    def embed(self, texts: list[str]) -> np.ndarray:
        if self._tfidf is None:
            raise RuntimeError("LsaEmbedder must be fitted (or loaded) before use")
        return _normalise(self._svd.transform(self._tfidf.transform(texts)))

    def embed_query(self, text: str) -> np.ndarray:
        return self.embed([text])[0]

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self.embed(texts)

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(pickle.dumps({"dim": self.dim, "seed": self.seed,
                                       "tfidf": self._tfidf, "svd": self._svd}))

    @classmethod
    def load(cls, path: Path) -> "LsaEmbedder":
        data = pickle.loads(path.read_bytes())    # our own file, written by save()
        obj = cls(dim=data["dim"], seed=data["seed"])
        obj._tfidf, obj._svd = data["tfidf"], data["svd"]
        return obj


def flat_model_dir(cache_dir: Path, hf_name: str) -> Path:
    return Path(cache_dir) / "flat" / hf_name.replace("/", "--")


def _materialise(cache_dir: Path, hf_name: str) -> Path | None:
    """Turn a symlinked Hugging Face snapshot into a directory of real files.

    The HF cache stores files as symlinks into ``blobs/``. ONNX Runtime ≥1.30
    refuses external weight files (``model.onnx_data``, used by models over
    2 GB such as e5-large) whose resolved path leaves the model directory:
    "External data path escapes model directory". Files are *moved* out of
    the cache rather than copied, so a 2.2 GB model does not occupy 4.4 GB.
    Returns None when there is no such snapshot (nothing to fix).
    """
    import shutil

    short = hf_name.split("/")[-1].lower()
    snaps = [c.parent for c in Path(cache_dir).glob("models--*/snapshots/*/model.onnx_data")
             if short in str(c).lower()]
    if not snaps:
        return None
    flat = flat_model_dir(cache_dir, hf_name)
    flat.mkdir(parents=True, exist_ok=True)
    for f in snaps[0].iterdir():
        target = flat / f.name
        if not target.exists():
            shutil.move(str(f.resolve()), target)
    shutil.rmtree(snaps[0].parents[1], ignore_errors=True)   # the now-empty models--… entry
    return flat


class SemanticEmbedder:
    """Local multilingual sentence embeddings via fastembed/ONNX (no API calls)."""

    name = "semantic"
    mode = "ai-assisted"

    def __init__(self, cache_dir: Path, model: str = "minilm", batch_size: int = 32):
        from fastembed import TextEmbedding   # optional dependency — imported lazily

        spec = SEMANTIC_MODELS.get(model) or {"hf": model, "dim": 384, "query": "", "passage": ""}
        self.model_key = model
        self.model_name = spec["hf"]
        self.dim = spec["dim"]
        self._q, self._p = spec["query"], spec["passage"]
        self.batch_size = batch_size
        cache_dir = Path(cache_dir)
        flat = flat_model_dir(cache_dir, spec["hf"])
        if (flat / "model.onnx").exists():
            self._model = TextEmbedding(spec["hf"], cache_dir=str(cache_dir),
                                        specific_model_path=str(flat))
            return
        try:
            self._model = TextEmbedding(spec["hf"], cache_dir=str(cache_dir))
        except Exception as exc:  # noqa: BLE001 — ONNX external-data path check, see above
            if "escapes model directory" not in str(exc):
                raise
            flat = _materialise(cache_dir, spec["hf"])
            self._model = TextEmbedding(spec["hf"], cache_dir=str(cache_dir),
                                        specific_model_path=str(flat))

    def _run(self, texts: list[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        return _normalise(np.array(list(self._model.embed(texts, batch_size=self.batch_size))))

    def embed(self, texts: list[str]) -> np.ndarray:
        """Symmetric embedding (no prefix) — for similarity between passages."""
        return self._run(texts)

    def embed_query(self, text: str) -> np.ndarray:
        return self._run([self._q + text])[0]

    def embed_passages(self, texts: list[str]) -> np.ndarray:
        return self._run([self._p + t for t in texts])


def semantic_available() -> bool:
    try:
        import fastembed  # noqa: F401
        return True
    except ImportError:
        return False
