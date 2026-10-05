"""Vector layer: chunking, deterministic embedding, both KNN engines, fusion."""
from __future__ import annotations

import numpy as np
import pytest

from hero.vector.chunking import Chunk, section_bodies, windows
from hero.vector.embedders import LsaEmbedder
from hero.vector.store import HAS_SQLITE_VEC, VectorStore, lexical_or_query


def test_long_pasal_is_windowed_so_nothing_past_128_tokens_is_lost():
    text = " ".join(f"kata{i}" for i in range(200))
    parts = windows(text, size=80, overlap=20)
    assert len(parts) == 3
    assert parts[-1].split()[-1] == "kata199"            # the tail is still searchable


def test_section_bodies_are_recovered_from_full_text():
    full = "Pembukaan. I. KETENTUAN UMUM isi umum satu. II. PELAPORAN isi pelaporan dua."
    got = section_bodies([{"number": "I", "title": "KETENTUAN UMUM", "page": "1"},
                          {"number": "II", "title": "PELAPORAN", "page": "2"}], full)
    assert [g[0] for g in got] == ["I. KETENTUAN UMUM", "II. PELAPORAN"]
    assert "isi pelaporan" in got[1][2] and "isi pelaporan" not in got[0][2]


def test_lexical_query_is_an_or_of_content_words():
    assert lexical_or_query("aturan tentang perdagangan karbon") == '"perdagangan" OR "karbon"'
    assert lexical_or_query("dan yang") is None


CORPUS = [
    ("d1", "Bank wajib menyampaikan laporan bulanan kepada Otoritas Jasa Keuangan"),
    ("d1", "Laporan disampaikan paling lambat tanggal 15 bulan berikutnya"),
    ("d2", "Perdagangan karbon dilakukan melalui bursa karbon yang diselenggarakan"),
    ("d2", "Unit karbon yang diperdagangkan wajib tercatat dalam sistem registri"),
    ("d3", "Reksa dana berbentuk kontrak investasi kolektif dengan aset emas"),
    ("d3", "Unit penyertaan reksa dana diperdagangkan di bursa efek"),
]


@pytest.fixture
def store(tmp_path):
    s = VectorStore(tmp_path / "v.db")
    s.replace_chunks([Chunk(f"c{i}", d, "pasal", str(i % 2 + 1), 0, 1, t)
                      for i, (d, t) in enumerate(CORPUS)])
    lsa = LsaEmbedder(dim=4).fit([t for _, t in CORPUS] * 2)   # min_df=2 needs repeats
    s.index(lsa, use_cache=False)
    return s, lsa


def test_lsa_is_deterministic():
    texts = [t for _, t in CORPUS] * 2
    a = LsaEmbedder(dim=4).fit(texts).embed(["laporan bulanan bank"])
    b = LsaEmbedder(dim=4).fit(texts).embed(["laporan bulanan bank"])
    assert np.allclose(a, b)


@pytest.mark.skipif(not HAS_SQLITE_VEC, reason="sqlite-vec not installed")
def test_sqlite_vec_and_numpy_return_the_same_neighbours(store):
    s, lsa = store
    q = lsa.embed(["perdagangan unit karbon di bursa"])[0]
    a = s.knn("lsa", q, 3, engine="sqlite-vec")
    b = s.knn("lsa", q, 3, engine="numpy")
    assert [r for r, _ in a] == [r for r, _ in b]
    assert np.allclose([x for _, x in a], [x for _, x in b], atol=1e-5)


def test_search_returns_documents_with_the_best_passage(store):
    s, lsa = store
    hits = s.search("perdagangan karbon", method="lsa", k=2, embedder=lsa)
    assert hits[0].doc_id == "d2"
    assert "karbon" in hits[0].best_text and hits[0].best_ref in ("1", "2")


def test_filters_restrict_documents(store):
    s, lsa = store
    hits = s.search("bursa", method="lexical", k=5, allowed_docs={"d3"})
    assert {h.doc_id for h in hits} == {"d3"}


def test_hybrid_fuses_both_rankings(store):
    s, lsa = store
    stand_in = type("Sem", (), {"name": "semantic", "dim": lsa.dim, "embed": lsa.embed,
                                "embed_query": lsa.embed_query,
                                "embed_passages": lsa.embed_passages})()
    s.index(stand_in, use_cache=False)                 # stand-in "semantic" index
    hits = s.search("laporan bulanan", method="hybrid", k=3, embedder=lsa)
    assert hits[0].doc_id == "d1"
    assert set(hits[0].ranks) == {"lexical", "semantic"}


def test_cache_means_rebuilds_only_embed_new_text(store, tmp_path):
    s, lsa = store
    first = s.index(lsa, use_cache=True)
    again = s.index(lsa, use_cache=True)
    assert first["baru_diembed"] == len(CORPUS) and again["baru_diembed"] == 0


def test_materialise_moves_symlinked_snapshot_into_real_files(tmp_path):
    """ONNX Runtime ≥1.30 rejects external weights reached through the HF
    cache's blob symlinks. The fix must produce real files — and must move,
    not copy, so a 2.2 GB model does not take 4.4 GB."""
    from hero.vector.embedders import _materialise, flat_model_dir

    blobs = tmp_path / "models--qdrant--multilingual-e5-large-onnx" / "blobs"
    snap = tmp_path / "models--qdrant--multilingual-e5-large-onnx" / "snapshots" / "abc"
    blobs.mkdir(parents=True)
    snap.mkdir(parents=True)
    for name, data in (("model.onnx", b"graph"), ("model.onnx_data", b"weights" * 10)):
        (blobs / f"sha-{name}").write_bytes(data)
        (snap / name).symlink_to(blobs / f"sha-{name}")

    flat = _materialise(tmp_path, "intfloat/multilingual-e5-large")
    assert flat == flat_model_dir(tmp_path, "intfloat/multilingual-e5-large")
    assert (flat / "model.onnx_data").is_file() and not (flat / "model.onnx_data").is_symlink()
    assert (flat / "model.onnx_data").read_bytes() == b"weights" * 10
    assert not (tmp_path / "models--qdrant--multilingual-e5-large-onnx").exists()


def test_repeated_pasal_numbers_get_unique_chunk_ids():
    from hero.vector.chunking import chunk_document
    arts = [("13", 1, "Pasal 13 peraturan A berbunyi begini."), ("13", 4, "Pasal 13 peraturan B berbunyi lain.")]
    chunks, _ = chunk_document("d1", judul="SE", tentang=None, ringkasan=None, articles=arts,
                               sections=[], full_text=None)
    ids = [c.chunk_id for c in chunks]
    assert len(ids) == len(set(ids))
    assert [c.ref for c in chunks if c.level == "pasal"] == ["13", "13"]
