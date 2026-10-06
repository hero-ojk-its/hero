"""Uji jembatan ke backend tim — seluruhnya offline, tanpa backend sungguhan.

Yang dijaga di sini adalah hal-hal yang kalau salah tidak akan terlihat
sampai data sudah rusak di produksi: dimensi vektor, nama field kontrak,
idempotensi pengiriman pasal, dan jumlah panggilan ``done=true``.
"""
from __future__ import annotations

import json
import shutil
from pathlib import Path

import numpy as np
import pytest

from hero.bridge import mapping
from hero.bridge.config import BridgeSettings, load_bridge_settings
from hero.bridge.embed import pad_to, unpad
from hero.bridge.state import BridgeState


# ---------------------------------------------------------------------------
# Dimensi vektor: padding harus benar-benar netral
# ---------------------------------------------------------------------------
def _unit(rng, n):
    v = rng.normal(size=n).astype(np.float32)
    return v / np.linalg.norm(v)


def test_padding_tidak_mengubah_cosine():
    """Klaim di embed.py: zero-pad tidak mengubah cosine similarity. Dibuktikan."""
    rng = np.random.default_rng(42)
    for _ in range(20):
        a, b = _unit(rng, 1024), _unit(rng, 1024)
        before = float(a @ b)
        pa, pb = np.array(pad_to(a, 1536)), np.array(pad_to(b, 1536))
        after = float(pa @ pb)
        assert after == pytest.approx(before, abs=1e-6)
        assert np.linalg.norm(pa) == pytest.approx(1.0, abs=1e-6)


def test_padding_dapat_dibalik():
    rng = np.random.default_rng(7)
    v = _unit(rng, 384)
    assert unpad(pad_to(v, 1536), 384) == pytest.approx(v, abs=1e-7)


def test_padding_menolak_vektor_lebih_panjang_dari_kolom():
    with pytest.raises(ValueError, match="tidak muat"):
        pad_to(np.zeros(2048, dtype=np.float32), 1536)


# ---------------------------------------------------------------------------
# Pemetaan kontrak: kandidat hasil pindai
# ---------------------------------------------------------------------------
JDIH_ROW = {
    "record_key": "https://jdih.ojk.go.id/Web/Detail/123",
    "source": "jdih-ojk",
    "title": "Penyelenggaraan Teknologi Informasi oleh Bank Umum",
    "number": "11/POJK.03/2022", "doc_type": "POJK", "jenis": "Peraturan OJK",
    "sektor": "Perbankan", "category": "perbankan", "year": 2022,
    "status": "berlaku", "status_label": "Berlaku",
    "detail_url": "https://jdih.ojk.go.id/Web/Detail/123",
    "document_url": "https://jdih.ojk.go.id/Download/abc/POJK%2011%20Tahun%202022.pdf",
    "document_name": "POJK 11 Tahun 2022.pdf",
    "file_size": 1048576, "file_method": "head", "file_error": None,
    "fields_json": json.dumps({"Tanggal Penetapan (ISO)": "2022-07-07",
                               "Tanggal Pengundangan (ISO)": "2022-07-11",
                               "Sub Klasifikasi": "Bank Umum"}),
    "attachments_json": json.dumps([
        {"name": "POJK 11 Tahun 2022.pdf", "url": "https://jdih.ojk.go.id/Download/abc/POJK%2011%20Tahun%202022.pdf",
         "kind": "utama", "ext": "pdf"},
        {"name": "Abstrak POJK 11.pdf", "url": "https://jdih.ojk.go.id/Download/def/abstrak.pdf",
         "kind": "abstrak", "ext": "pdf"},
    ]),
}


def test_kandidat_dari_register_memakai_nama_field_backend():
    c = mapping.candidate_from_inventory(JDIH_ROW)
    assert c["url"].endswith(".pdf")
    assert c["filename"] == "POJK 11 Tahun 2022.pdf"
    assert c["size_bytes"] == 1048576 and c["size_source"] == "head"
    assert c["regulation_number"] == "11/POJK.03/2022"
    assert c["regulation_type"] == "POJK"
    assert c["bidang"] == "Perbankan" and c["sub_bidang"] == "Bank Umum"
    assert c["regulation_year"] == 2022
    assert c["status_keberlakuan"] == "berlaku"
    assert c["doc_kind"] == "utama"
    # Tanggal penetapan dipakai sebagai release_date; "mulai berlaku" tidak
    # dikarang dari tanggal pengundangan.
    assert c["release_date"] == "2022-07-07"
    assert c["effective_date"] is None


def test_rancangan_tidak_dipaksa_jadi_berlaku():
    row = dict(JDIH_ROW, status="rancangan")
    assert mapping.candidate_from_inventory(row)["status_keberlakuan"] == "tidak_diketahui"


def test_rekaman_tanpa_tautan_berkas_bukan_kandidat():
    row = dict(JDIH_ROW, document_url=None, attachments_json="[]")
    assert mapping.candidate_from_inventory(row) is None
    assert mapping.candidates_from_inventory_row(row) == []


def test_lampiran_pendamping_hanya_ikut_bila_diminta():
    tanpa = mapping.candidates_from_inventory_row(JDIH_ROW)
    dengan = mapping.candidates_from_inventory_row(JDIH_ROW, include_companions=True)
    assert [c["doc_kind"] for c in tanpa] == ["utama"]
    assert sorted(c["doc_kind"] for c in dengan) == ["abstrak", "utama"]


# ---------------------------------------------------------------------------
# Pemetaan kontrak: pasal
# ---------------------------------------------------------------------------
class _Art:
    def __init__(self, number, text, bab=None, page=None, ayat=None, in_attachment=False):
        self.number, self.text, self.bab, self.page = number, text, bab, page
        self.ayat = ayat or []
        self.in_attachment = in_attachment


def test_pasal_lampiran_tidak_dikirim_dan_urutan_tetap():
    arts = [_Art("Pasal 1", "Dalam Peraturan ini…", bab="BAB I KETENTUAN UMUM"),
            _Art("Pasal 7A", "Pasal sisipan…"),
            _Art("Pasal 2", "Rujukan di lampiran", in_attachment=True)]
    rows = mapping.article_payloads(42, arts)
    assert [r["article_number"] for r in rows] == ["Pasal 1", "Pasal 7A"]
    assert [r["order_index"] for r in rows] == [0, 1]
    assert all(r["document_id"] == 42 and r["level"] == "pasal" for r in rows)
    assert rows[0]["chapter_title"] == "BAB I KETENTUAN UMUM"
    assert "embedding" not in rows[0]


def test_ayat_hanya_dikirim_bila_dinyalakan():
    arts = [_Art("Pasal 2", "Bank wajib…", ayat=[("1", "Bank wajib menerapkan…"),
                                                 ("2", "Bank dilarang…")])]
    assert len(mapping.article_payloads(1, arts)) == 1
    rows = mapping.article_payloads(1, arts, push_ayat=True)
    assert [r["level"] for r in rows] == ["pasal", "ayat", "ayat"]
    assert all(len(r["article_number"]) <= 50 for r in rows)


def test_embedding_ikut_per_pasal():
    arts = [_Art("Pasal 1", "a" * 50), _Art("Pasal 2", "b" * 50)]
    vecs = [[0.1] * 1536, None]
    rows = mapping.article_payloads(9, arts, vectors=vecs)
    assert len(rows[0]["embedding"]) == 1536
    assert "embedding" not in rows[1]


# ---------------------------------------------------------------------------
# Keyakinan per field
# ---------------------------------------------------------------------------
class _Md:
    def __init__(self, **kw):
        self.number = kw.get("number")
        self.doc_type = kw.get("doc_type")
        self.issued_date = kw.get("issued_date")
        self.title = kw.get("title")
        self.subject = kw.get("subject")


class _El:
    def __init__(self, nilai, sumber=None):
        self.nilai, self.sumber = nilai, sumber


class _Ident:
    def __init__(self, **kw):
        for k in ("jenis", "nomor", "tahun", "tanggal", "judul"):
            setattr(self, k, kw.get(k) or _El(None))


def test_keyakinan_hanya_untuk_field_yang_terbaca():
    from datetime import date

    md = _Md(number="11/POJK.03/2022", doc_type="POJK", issued_date=date(2022, 7, 7),
             title="POJK 11", subject="Penyelenggaraan TI")
    ident = _Ident(nomor=_El("11/POJK.03/2022", "halaman-1"),
                   tanggal=_El(date(2022, 7, 7), "penutup"), jenis=_El("POJK", "halaman-1"))
    conf = mapping.field_confidence(md, identity=ident)
    assert conf["regulation_number"] == 0.95
    assert conf["release_date"] == 0.85
    assert conf["regulation_type"] == 0.95
    assert conf["title"] == 0.95

    kosong = mapping.field_confidence(_Md(), identity=None)
    assert kosong == {}, "field yang tidak terbaca tidak boleh punya keyakinan"


def test_keyakinan_diturunkan_oleh_ocr():
    md = _Md(number="11/POJK.03/2022")
    penuh = mapping.field_confidence(md)
    ocr = mapping.field_confidence(md, from_ocr=True, ocr_confidence=60.0)
    assert ocr["regulation_number"] < penuh["regulation_number"]
    assert ocr["regulation_number"] == pytest.approx(0.75 * 0.6, abs=0.01)


def test_judul_dari_nama_berkas_tidak_mengklaim_yakin():
    md = _Md(title="Salinan POJK 11 2022", subject=None)
    assert mapping.field_confidence(md)["title"] == 0.35


# ---------------------------------------------------------------------------
# Konfigurasi
# ---------------------------------------------------------------------------
def test_kunci_api_tidak_pernah_dibaca_dari_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("bridge:\n  base_url: http://contoh:9000\n  api_key: JANGAN-DIPAKAI\n"
                   "  embedder: semantic\n", encoding="utf-8")
    monkeypatch.delenv("HERO_BACKEND_INTERNAL_KEY", raising=False)
    monkeypatch.delenv("INTERNAL_API_KEY", raising=False)
    monkeypatch.chdir(tmp_path)          # agar .env lain tidak terbaca
    s = load_bridge_settings(cfg)
    assert s.base_url == "http://contoh:9000"
    assert s.embedder == "semantic"
    assert s.api_key == ""
    assert "JANGAN-DIPAKAI" not in json.dumps(s.redacted())


def test_environment_menimpa_yaml(tmp_path, monkeypatch):
    cfg = tmp_path / "sources.yaml"
    cfg.write_text("bridge:\n  base_url: http://dari-yaml:1\n", encoding="utf-8")
    monkeypatch.setenv("HERO_BACKEND_URL", "http://dari-env:2")
    monkeypatch.setenv("HERO_BACKEND_INTERNAL_KEY", "rahasia")
    monkeypatch.chdir(tmp_path)
    s = load_bridge_settings(cfg)
    assert s.base_url == "http://dari-env:2" and s.api_key == "rahasia"
    assert s.url("/api/v1/internal/x") == "http://dari-env:2/api/v1/internal/x"


# ---------------------------------------------------------------------------
# Buku besar: idempotensi
# ---------------------------------------------------------------------------
def test_pasal_tidak_dikirim_dua_kali(tmp_path):
    st = BridgeState(tmp_path / "bridge.db")
    assert st.articles_already_sent(1, "hash-a") == 0
    st.begin_extraction(1, file_hash="hash-a", attempt=1)
    st.finish_extraction(1, status="selesai", articles=12, vectors=12)
    assert st.articles_already_sent(1, "hash-a") == 12
    # Berkasnya diganti → pasal lama tidak lagi mewakili isinya.
    assert st.articles_already_sent(1, "hash-b") == 0
    st.close()


def test_peta_identitas_dan_halaman_pasal(tmp_path):
    st = BridgeState(tmp_path / "bridge.db")
    st.map_document(77, "a1b2c3", "hash")
    assert st.doc_id_for(77) == "a1b2c3"
    assert st.document_id_for("a1b2c3") == 77
    st.record_article_pages(77, [("Pasal 1", 1), ("Pasal 2", 3), ("Pasal 3", None)])
    assert st.pages_for(77) == {"Pasal 1": 1, "Pasal 2": 3}
    assert st.all_pages()[77]["Pasal 2"] == 3
    st.close()


def test_migrasi_buku_besar_idempoten(tmp_path):
    p = tmp_path / "bridge.db"
    BridgeState(p).close()
    st = BridgeState(p)          # dibuka ulang: migrasi tidak boleh gagal
    assert st.summary()["pasal_terkirim"] == 0
    st.close()


# ---------------------------------------------------------------------------
# Klien HTTP
# ---------------------------------------------------------------------------
class _Resp:
    def __init__(self, status=200, body=None, content=b""):
        self.status_code = status
        self._body = body
        self.content = content or (json.dumps(body).encode() if body is not None else b"")
        self.text = self.content.decode("utf-8", "replace")

    def json(self):
        if self._body is None:
            raise ValueError("bukan JSON")
        return self._body

    def iter_content(self, chunk_size=1):
        yield self.content

    def close(self):
        pass


class _Session:
    """Sesi requests tiruan: urutan respons yang sudah ditentukan."""

    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []
        self.headers = {}

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        r = self.responses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r

    def close(self):
        pass


def _client(responses):
    from hero.bridge.client import BackendClient

    s = _Session(responses)
    c = BackendClient(BridgeSettings(base_url="http://b", api_key="k"), session=s)
    return c, s


def test_klien_mengulang_503_lalu_berhasil(monkeypatch):
    monkeypatch.setattr("time.sleep", lambda *_: None)
    c, s = _client([_Resp(503, {"detail": "sibuk"}), _Resp(200, [{"document_id": 1}])])
    assert c.claim_extraction(1) == [{"document_id": 1}]
    assert len(s.calls) == 2


def test_klien_tidak_mengulang_404():
    from hero.bridge.client import BackendError

    c, s = _client([_Resp(404, {"detail": "tidak ada"})])
    with pytest.raises(BackendError) as exc:
        c.patch_extraction(9, {"title": "x"})
    assert exc.value.status == 404 and "tidak ada" in str(exc.value)
    assert len(s.calls) == 1


def test_klien_mengirim_kunci_internal():
    c, _ = _client([])
    assert c.http.headers["X-Internal-API-Key"] == "k"


def test_unduh_pdf_menulis_berkas_utuh(tmp_path):
    c, _ = _client([_Resp(200, None, content=b"%PDF-1.7 isi")])
    dest = tmp_path / "x" / "doc.pdf"
    c.download_pdf(5, dest)
    assert dest.read_bytes().startswith(b"%PDF-")
    assert not (tmp_path / "x" / "doc.pdf.part").exists()


def test_batch_kandidat_hanya_sekali_done():
    """done=true memicu perbandingan KB di backend — tidak boleh lebih dari sekali."""
    from hero.bridge.scan_worker import ScanWorker

    calls = []

    class _Stub:
        def push_candidates(self, scan_id, candidates, **kw):
            calls.append((len(list(candidates)), kw["done"]))
            return {"candidates_total": 0, "status": "siap_dipilih"}

    class _St:
        def bump_scan(self, *a, **k):
            pass

    w = ScanWorker.__new__(ScanWorker)
    w.bridge = BridgeSettings(batch_candidates=2)
    w.client = _Stub()
    w.state = _St()
    sent = w._send(1, [{"url": f"u{i}"} for i in range(5)], pages_visited=3,
                   truncated=False, errors=[], say=lambda m: None)
    assert sent == 5
    assert [d for _, d in calls] == [False, False, True]
    assert [n for n, _ in calls] == [2, 2, 1]


# ---------------------------------------------------------------------------
# Pemilihan sumber untuk sesi pindai
# ---------------------------------------------------------------------------
def test_sesi_pindai_memakai_konfigurasi_sumber_yang_sudah_ada(tmp_settings):
    from hero.config import SiteSource
    from hero.bridge.scan_worker import site_for

    tmp_settings.sites = [SiteSource(
        name="JDIH OJK", url="https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
        adapter="jdih_ojk", sektor=["01", "02"], jenis_peraturan=["06"],
        exclude_patterns=["abstrak"])]
    s = site_for("https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
                 tmp_settings, depth=2, max_pages=10, max_candidates=100)
    assert s.resolved_adapter() == "jdih_ojk"
    assert s.sektor == ["01", "02"] and s.exclude_patterns == ["abstrak"]
    assert s.max_depth == 2 and s.max_pages == 10

    lain = site_for("https://contoh.go.id/peraturan", tmp_settings,
                    depth=1, max_pages=5, max_candidates=50)
    assert lain.resolved_adapter() == "generic"


# ---------------------------------------------------------------------------
# Worker ekstraksi, ujung ke ujung dengan backend tiruan
# ---------------------------------------------------------------------------
class FakeBackend:
    """Backend tiruan yang mencatat apa yang diterimanya."""

    def __init__(self, pdf: Path, status: str = "terindeks"):
        self.pdf = pdf
        self.status = status
        self.patched: list[dict] = []
        self.articles: list[dict] = []
        self.requeued: list[int] = []

    def download_pdf(self, document_id, dest, **kw):
        Path(dest).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy(self.pdf, dest)
        return Path(dest)

    def patch_extraction(self, document_id, payload, force=False):
        self.patched.append({"document_id": document_id, **payload})
        if "error" in payload:
            return {"status": "gagal_dicatat", "failure_id": 1}
        return {"status": self.status, "changed_fields": ["title"], "ignored_fields": [],
                "low_confidence_fields": [], "placement": {"placed": True}}

    def post_articles(self, articles):
        self.articles.extend(articles)
        return {"status": "ok", "inserted_count": len(articles)}

    def requeue(self, document_id):
        self.requeued.append(document_id)
        return {"status": "requeued"}

    def close(self):
        pass


def _worker(tmp_settings, backend, tmp_path, **bridge_kw):
    from hero.bridge.extract_worker import ExtractionWorker

    bridge = BridgeSettings(embedder="none", **bridge_kw)
    st = BridgeState(tmp_path / "bridge.db")
    return ExtractionWorker(tmp_settings, bridge, client=backend, state=st,
                            staging=tmp_path / "staging"), st


def test_ekstraksi_mengirim_metadata_pasal_dan_halaman(tmp_settings, tmp_path, regulation_pdf):
    pdf = regulation_pdf(tmp_path / "pojk.pdf", nomor=11, tahun=2026)
    be = FakeBackend(pdf)
    w, st = _worker(tmp_settings, be, tmp_path)
    out = w.process_one({"document_id": 42, "file_hash": "h1", "attempt": 1,
                         "original_filename": "pojk.pdf"})
    assert out.status == "terindeks"
    assert out.articles == 3                      # Pasal 1..3 di fixture
    body = be.patched[0]
    assert body["regulation_number"] and body["regulation_type"] == "POJK"
    assert body["extraction_method"] == "teks_langsung"
    assert body["extraction_engine"].startswith("hero-pipeline")
    assert set(body["confidence"]) <= {"title", "regulation_number", "regulation_type",
                                       "release_date"}
    assert [a["article_number"] for a in be.articles] == ["Pasal 1", "Pasal 2", "Pasal 3"]
    # Halaman pasal tersimpan lokal walau backend tidak punya kolomnya.
    assert st.pages_for(42)
    st.close()


def test_ekstraksi_tidak_mengirim_pasal_dua_kali(tmp_settings, tmp_path, regulation_pdf):
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf)
    w, st = _worker(tmp_settings, be, tmp_path)
    item = {"document_id": 7, "file_hash": "h", "attempt": 1, "original_filename": "pojk.pdf"}
    w.process_one(item)
    jumlah_awal = len(be.articles)
    w.process_one(dict(item, attempt=2))          # diklaim ulang
    assert len(be.articles) == jumlah_awal, "klaim ulang tidak boleh menggandakan pasal"
    st.close()


def test_pdf_rusak_dilaporkan_sebagai_kegagalan(tmp_settings, tmp_path):
    bad = tmp_path / "bukan.pdf"
    bad.write_bytes(b"<html>404</html>")
    be = FakeBackend(bad)
    w, st = _worker(tmp_settings, be, tmp_path)
    out = w.process_one({"document_id": 3, "file_hash": "h", "attempt": 1})
    assert out.status == "gagal_dicatat"
    assert be.patched[0]["error"]["code"] in ("ekstraksi_gagal", "ocr_gagal")
    assert not be.articles
    st.close()


def test_teks_lengkap_dipotong_sesuai_batas_indeks_backend(tmp_settings, tmp_path, regulation_pdf):
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf)
    w, st = _worker(tmp_settings, be, tmp_path, max_full_text_chars=50)
    w.process_one({"document_id": 5, "file_hash": "h", "attempt": 1})
    assert len(be.patched[0]["full_text"]) <= 50
    st.close()


def test_url_dengan_sektor_eksplisit_tidak_mewarisi_matriks_penuh(tmp_settings):
    """Pengguna memilih satu kanal di layar; jangan diperluas jadi 120 pasangan."""
    from hero.bridge.scan_worker import site_for
    from hero.config import SiteSource

    tmp_settings.sites = [SiteSource(
        name="JDIH OJK", url="https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
        adapter="jdih_ojk", sektor=["01", "02", "03"], jenis_peraturan=["06", "07"])]
    sempit = site_for("https://jdih.ojk.go.id/Web/ViewPeraturan/Index?sektor=06&jenisPeraturan=06",
                      tmp_settings, depth=1, max_pages=5, max_candidates=20)
    assert sempit.sektor == [] and sempit.jenis_peraturan == []

    luas = site_for("https://jdih.ojk.go.id/Web/ViewPeraturan/Index",
                    tmp_settings, depth=1, max_pages=5, max_candidates=20)
    assert luas.sektor == ["01", "02", "03"] and luas.jenis_peraturan == ["06", "07"]
