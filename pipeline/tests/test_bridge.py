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
    rows = mapping.article_payloads(1, arts, push_ayat=True, with_parent=True)
    assert [r["level"] for r in rows] == ["pasal", "ayat", "ayat"]
    assert all(len(r["article_number"]) <= 50 for r in rows)


def test_ayat_menunjuk_order_index_pasal_induknya():
    """Tanpa induk yang benar, ayat menjadi baris menggantung di backend."""
    arts = [_Art("Pasal 1", "Ketentuan umum…", ayat=[("1", "Dalam hal ini…")]),
            _Art("Pasal 2", "Bank wajib…", ayat=[("1", "Wajib a…"), ("2", "Wajib b…")])]
    rows = mapping.article_payloads(1, arts, push_ayat=True, with_parent=True)
    assert [r["order_index"] for r in rows] == [0, 1, 2, 3, 4]
    assert [r.get("parent_order_index") for r in rows] == [None, 0, None, 2, 2]
    # Induk tiap ayat harus benar-benar ada di kiriman yang sama, kalau tidak
    # backend menjawab 422.
    ada = {r["order_index"] for r in rows}
    assert all(r["parent_order_index"] in ada for r in rows if r.get("parent_order_index") is not None)


def test_ayat_tanpa_induk_ditolak_di_tempat_bukan_dikirim_menggantung():
    arts = [_Art("Pasal 1", "isi", ayat=[("1", "a")])]
    with pytest.raises(ValueError, match="with_parent"):
        mapping.article_payloads(1, arts, push_ayat=True, with_parent=False)


def test_halaman_dikirim_hanya_bila_backend_punya_kolomnya():
    arts = [_Art("Pasal 1", "isi pasal satu", page=3)]
    assert "page" not in mapping.article_payloads(1, arts)[0]
    assert mapping.article_payloads(1, arts, with_page=True)[0]["page"] == 3


def test_halaman_tak_masuk_akal_dikosongkan_bukan_ditebak():
    """Backend menolak page < 1; halaman yang ditebak menyesatkan pemeriksa."""
    for buruk in (0, -2, None, "halaman tiga"):
        rows = mapping.article_payloads(1, [_Art("Pasal 1", "isi", page=buruk)], with_page=True)
        assert "page" not in rows[0]


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
    """Backend tiruan yang mencatat apa yang diterimanya.

    ``contract="v2"`` meniru backend dengan kontrak pasal Langkah 13 (upsert
    pada ``(document_id, order_index)``, ``page``, ``parent_order_index``,
    ``replace_document_ids``). ``contract="v1"`` meniru backend sebelumnya —
    termasuk sifat yang berbahaya itu: **field yang tidak dikenalnya
    diabaikan tanpa galat**, sehingga pengirim mengira halamannya sampai.
    """

    def __init__(self, pdf: Path, status: str = "terindeks", contract: str = "v2"):
        self.pdf = pdf
        self.status = status
        self.contract = contract
        self.patched: list[dict] = []
        self.articles: list[dict] = []
        self.requeued: list[int] = []
        self.replace_calls: list[list[int]] = []

    # -- kemampuan -------------------------------------------------------
    def article_contract(self) -> dict:
        baru = self.contract == "v2"
        return {"page": baru, "parent_order_index": baru,
                "replace_document_ids": baru, "terdeteksi": True}

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

    def post_articles(self, articles, *, replace_document_ids=None):
        if self.contract != "v2":
            # Backend lama: field asing dibuang diam-diam, tidak ada upsert,
            # dan jawabannya tidak punya updated_count/deleted_count.
            self.articles.extend({k: v for k, v in a.items()
                                  if k not in ("page", "parent_order_index")}
                                 for a in articles)
            return {"status": "ok", "inserted_count": len(articles), "message": "ok"}

        deleted = 0
        if replace_document_ids:
            self.replace_calls.append(list(replace_document_ids))
            sisa = [a for a in self.articles if a["document_id"] not in set(replace_document_ids)]
            deleted = len(self.articles) - len(sisa)
            self.articles = sisa
        inserted = updated = 0
        for a in articles:
            kunci = (a["document_id"], a.get("order_index"))
            ada = next((x for x in self.articles
                        if (x["document_id"], x.get("order_index")) == kunci), None)
            if ada is not None and kunci[1] is not None:
                ada.update({k: v for k, v in a.items()
                            if k != "embedding" or v is not None})
                updated += 1
            else:
                self.articles.append(dict(a))
                inserted += 1
        return {"status": "ok", "inserted_count": inserted, "updated_count": updated,
                "deleted_count": deleted, "message": "ok"}

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


# ---------------------------------------------------------------------------
# Kontrak pasal Langkah 13: deteksi kemampuan backend
#
# Bahayanya satu arah dan senyap: backend lama **mengabaikan** field yang tidak
# dikenalnya tanpa galat. Mengirim `replace_document_ids` ke sana tidak
# menghapus apa pun, sehingga kiriman berikutnya menggandakan pasal — dan
# pasal ganda langsung merusak unit pembanding harmonisasi.
# ---------------------------------------------------------------------------
_OPENAPI_V2 = {"components": {"schemas": {
    "ArticleChunkIn": {"properties": {"document_id": {}, "page": {}, "parent_order_index": {}}},
    "BulkArticleIn": {"properties": {"articles": {}, "replace_document_ids": {}}}}}}
_OPENAPI_V1 = {"components": {"schemas": {
    "ArticleChunkIn": {"properties": {"document_id": {}, "order_index": {}}},
    "BulkArticleIn": {"properties": {"articles": {}}}}}}


def test_kontrak_pasal_terbaca_dari_openapi():
    c, _ = _client([_Resp(200, _OPENAPI_V2)])
    k = c.article_contract()
    assert k["page"] and k["parent_order_index"] and k["replace_document_ids"]
    assert k["terdeteksi"] and k["sumber"] == "openapi"


def test_backend_lama_terbaca_sebagai_kontrak_lama():
    c, _ = _client([_Resp(200, _OPENAPI_V1)])
    k = c.article_contract()
    assert not any(k[f] for f in ("page", "parent_order_index", "replace_document_ids"))


def test_openapi_dimatikan_berarti_jalur_aman_bukan_asumsi_optimis():
    """Backend produksi boleh mematikan /openapi.json. Yang tidak diketahui
    harus diperlakukan sebagai 'belum punya', bukan 'mungkin punya'."""
    c, _ = _client([_Resp(404, {"detail": "not found"})])
    k = c.article_contract()
    assert not k["replace_document_ids"] and k["terdeteksi"] is False


def test_kontrak_hanya_ditanyakan_sekali():
    c, s = _client([_Resp(200, _OPENAPI_V2)])
    c.article_contract()
    c.article_contract()
    assert len(s.calls) == 1


def test_bentuk_jawaban_memperbaiki_tebakan_yang_terlalu_hati_hati():
    """Tanpa OpenAPI kita menebak 'lama'. Jawaban yang membawa updated_count /
    deleted_count hanya ada pada kontrak Langkah 13, jadi itu bukti cukup."""
    c, _ = _client([_Resp(404, {"detail": "x"}),
                    _Resp(200, {"status": "ok", "inserted_count": 2,
                                "updated_count": 0, "deleted_count": 0})])
    assert c.article_contract()["replace_document_ids"] is False
    c.post_articles([{"document_id": 1, "order_index": 0}])
    k = c.article_contract()
    assert k["replace_document_ids"] and k["sumber"] == "jawaban backend"


def test_jawaban_lama_tidak_menurunkan_kontrak_yang_sudah_pasti():
    """Proksi yang memangkas field tidak boleh membuat satu dokumen dikirim
    dengan dua aturan berbeda di tengah jalan."""
    c, _ = _client([_Resp(200, _OPENAPI_V2),
                    _Resp(200, {"status": "ok", "inserted_count": 1})])
    assert c.article_contract()["replace_document_ids"]
    c.post_articles([{"document_id": 1, "order_index": 0}])
    assert c.article_contract()["replace_document_ids"]


def test_kontrak_dapat_dipaksa_lewat_konfigurasi():
    """Untuk backend yang mematikan dokumentasi dan tidak boleh dicoba-coba."""
    from hero.bridge.client import BackendClient

    s = _Session([])
    c = BackendClient(BridgeSettings(base_url="http://b", api_key="k",
                                     article_contract="v2"), session=s)
    assert c.article_contract()["replace_document_ids"]
    assert not s.calls, "pemaksaan tidak boleh memanggil backend"


def test_replace_hanya_dikirim_bila_diminta():
    c, s = _client([_Resp(200, {"status": "ok", "inserted_count": 1, "updated_count": 0}),
                    _Resp(200, {"status": "ok", "inserted_count": 1, "updated_count": 0})])
    c.post_articles([{"document_id": 3, "order_index": 0}])
    assert "replace_document_ids" not in s.calls[0][2]["json"]
    c.post_articles([{"document_id": 3, "order_index": 0}], replace_document_ids=[3])
    assert s.calls[1][2]["json"]["replace_document_ids"] == [3]


# ---------------------------------------------------------------------------
# Worker ekstraksi terhadap kedua versi backend
# ---------------------------------------------------------------------------
def test_worker_mengirim_halaman_dan_ganti_bersih_ke_backend_baru(
        tmp_settings, tmp_path, regulation_pdf):
    pdf = regulation_pdf(tmp_path / "pojk.pdf", nomor=11, tahun=2026)
    be = FakeBackend(pdf, contract="v2")
    w, st = _worker(tmp_settings, be, tmp_path)
    out = w.process_one({"document_id": 42, "file_hash": "h1", "attempt": 1,
                         "original_filename": "pojk.pdf"})
    assert out.status == "terindeks" and out.articles == 3
    assert be.replace_calls == [[42]], "batch pertama harus membersihkan pasal lama"
    assert all(a.get("page") for a in be.articles), "halaman harus ikut terkirim"
    st.close()


def test_worker_tidak_mengirim_ganti_bersih_ke_backend_lama(
        tmp_settings, tmp_path, regulation_pdf):
    """Pada backend lama field itu diabaikan diam-diam, jadi mengirimnya hanya
    menciptakan rasa aman palsu — penjaga sebenarnya adalah buku besar lokal."""
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf, contract="v1")
    w, st = _worker(tmp_settings, be, tmp_path)
    out = w.process_one({"document_id": 7, "file_hash": "h", "attempt": 1})
    assert out.status == "terindeks" and out.articles == 3
    assert be.replace_calls == []
    assert all("page" not in a for a in be.articles)
    st.close()


def test_ayat_tidak_dikirim_ke_backend_yang_belum_punya_induk(
        tmp_settings, tmp_path, regulation_pdf):
    """Diminta push_ayat, tetapi backend lama akan menyimpannya menggantung."""
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf, contract="v1")
    w, st = _worker(tmp_settings, be, tmp_path, push_ayat=True)
    out = w.process_one({"document_id": 8, "file_hash": "h", "attempt": 1})
    assert out.status == "terindeks"
    assert {a["level"] for a in be.articles} == {"pasal"}
    st.close()


def test_ekstraksi_ulang_berkas_berubah_membuang_pasal_lama(
        tmp_settings, tmp_path, regulation_pdf):
    """Berkas diganti dengan yang pasalnya lebih sedikit: sisa pasal lama
    tidak boleh tertinggal sebagai unit pembanding hantu."""
    besar = regulation_pdf(tmp_path / "besar.pdf", nomor=11, tahun=2026)
    be = FakeBackend(besar, contract="v2")
    w, st = _worker(tmp_settings, be, tmp_path)
    w.process_one({"document_id": 55, "file_hash": "lama", "attempt": 1})
    semula = len(be.articles)
    assert semula == 3

    # Dokumen yang sama, berkas baru (hash berbeda) dengan satu pasal saja.
    be.articles.append({"document_id": 55, "order_index": 99, "level": "pasal",
                        "article_number": "Pasal 99", "content_text": "sisa lama"})
    be.pdf = regulation_pdf(tmp_path / "kecil.pdf", nomor=12, tahun=2026)
    w.process_one({"document_id": 55, "file_hash": "baru", "attempt": 1})
    assert all(a["order_index"] != 99 for a in be.articles), "pasal hantu masih tertinggal"
    assert be.replace_calls == [[55], [55]]
    st.close()


def test_ganti_bersih_tidak_menghapus_batch_sebelumnya(tmp_settings, tmp_path, regulation_pdf):
    """Regresi: replace_document_ids pada SETIAP batch akan menghapus hasil
    batch sebelumnya, menyisakan ≤ satu batch terakhir saja."""
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf, contract="v2")
    w, st = _worker(tmp_settings, be, tmp_path, batch_articles=1)   # 3 pasal → 3 batch
    out = w.process_one({"document_id": 61, "file_hash": "h", "attempt": 1})
    assert len(be.articles) == 3, "batch berikutnya menghapus hasil batch sebelumnya"
    assert out.articles == 3
    assert be.replace_calls == [[61]], "ganti-bersih hanya pada batch pertama"
    st.close()


def test_pasal_yang_diperbarui_tetap_terhitung(tmp_settings, tmp_path, regulation_pdf):
    """Upsert melaporkan kiriman ulang sebagai updated_count. Menghitung
    inserted_count saja membuat dokumen yang lengkap terlapor '0 pasal'."""
    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf, contract="v2")
    w, st = _worker(tmp_settings, be, tmp_path)
    w.process_one({"document_id": 71, "file_hash": "h1", "attempt": 1})
    st.close()

    # Buku besar baru = worker lain yang mengerjakan dokumen yang sama.
    w2, st2 = _worker(tmp_settings, be, tmp_path / "lain")
    out = w2.process_one({"document_id": 71, "file_hash": "h1", "attempt": 1})
    assert out.articles == 3, "pasal yang diperbarui tidak terhitung"
    assert len(be.articles) == 3, "upsert tidak boleh menggandakan"
    st2.close()


def test_penjaga_kiriman_ulang_memakai_hash_milik_pasal_bukan_percobaan_sekarang(tmp_path):
    """Regresi: ``begin_extraction`` menimpa ``file_hash`` di awal percobaan.
    Bila penjaga membandingkan kolom itu, ia membandingkan hash baru dengan
    dirinya sendiri — berkas yang diganti tidak pernah diekstraksi ulang."""
    st = BridgeState(tmp_path / "bridge.db")
    st.begin_extraction(3, file_hash="lama", attempt=1)
    st.finish_extraction(3, status="selesai", articles=12, articles_hash="lama")
    assert st.articles_already_sent(3, "lama") == 12          # kiriman ulang: ditahan

    st.begin_extraction(3, file_hash="baru", attempt=2)       # berkas diganti
    assert st.articles_already_sent(3, "baru") == 0, "pasal lama harus digantikan"
    st.close()


def test_baris_buku_besar_lama_tanpa_articles_hash_tetap_terbaca(tmp_path):
    """Buku besar yang sudah ada di VPS tidak punya kolom itu; migrasi aditif
    tidak boleh membuat semua dokumennya terkirim ulang."""
    st = BridgeState(tmp_path / "bridge.db")
    st.begin_extraction(4, file_hash="h", attempt=1)
    st.conn.execute("UPDATE extraction SET articles = 5, articles_hash = NULL "
                    "WHERE document_id = 4")
    st.conn.commit()
    assert st.articles_already_sent(4, "h") == 5
    st.close()


# ---------------------------------------------------------------------------
# Cermin korpus: halaman pasal
# ---------------------------------------------------------------------------
class _Cur:
    def __init__(self, hasil):
        self.hasil = hasil
        self.sql = None

    def __enter__(self):
        return self

    def __exit__(self, *e):
        return False

    def execute(self, sql, params=None):
        self.sql = sql

    def fetchone(self):
        return self.hasil


class _Conn:
    def __init__(self, punya_page):
        self.punya_page = punya_page
        self.terakhir = None

    def cursor(self):
        self.terakhir = _Cur((1,) if self.punya_page else None)
        return self.terakhir


def test_kolom_halaman_ditanyakan_bukan_diasumsikan():
    """Menyebut ``a.page`` pada backend yang belum dimigrasi akan menggagalkan
    seluruh cermin korpus, bukan hanya halamannya."""
    from hero.bridge.sync import _punya_kolom_halaman

    assert _punya_kolom_halaman(_Conn(True)) is True
    assert _punya_kolom_halaman(_Conn(False)) is False


def test_sql_pasal_hanya_menyebut_halaman_bila_kolomnya_ada():
    from hero.bridge.sync import ART_SQL

    assert "a.page" in ART_SQL.format(kolom_halaman=", a.page")
    assert "a.page" not in ART_SQL.format(kolom_halaman="")


def test_halaman_backend_disaring_sama_ketatnya():
    """Halaman yang ditebak mengirim pemeriksa ke halaman yang salah."""
    from hero.bridge.sync import _halaman

    assert _halaman(3) == 3
    assert _halaman("7") == 7
    for buruk in (0, -1, None, "", "hal 3"):
        assert _halaman(buruk) is None


# ---------------------------------------------------------------------------
# Layanan analisa: pemanasan
# ---------------------------------------------------------------------------
def test_pemanasan_tidak_menjatuhkan_layanan_tanpa_indeks(tmp_settings, tmp_path):
    """Server baru tanpa indeks vektor harus tetap naik; pemanasan hanya gagal diam-diam."""
    from hero.bridge.ml_api import MlState

    ml = MlState(tmp_settings, BridgeSettings(embedder="none"))
    assert ml.prewarm() is False


def test_pemanasan_hanya_menyentuh_lsa_tidak_memuat_model_semantik(tmp_settings):
    from hero.bridge.ml_api import MlState

    dipanggil = []

    class _VS:
        def ready(self, m):
            dipanggil.append(("ready", m))
            return m == "lsa"

        def search(self, q, metode, k=10):
            dipanggil.append(("search", metode))
            return []

    ml = MlState(tmp_settings, BridgeSettings(embedder="none"))
    ml._vs = _VS()
    assert ml.prewarm() is True
    assert ("search", "lsa") in dipanggil
    assert not any(m in ("semantic", "hybrid") for _, m in dipanggil), \
        "pemanasan tidak boleh menyentuh model semantik di server kecil"


def test_pemanasan_yang_gagal_dilaporkan_bukan_meledak(tmp_settings):
    from hero.bridge.ml_api import MlState

    class _VS:
        def ready(self, m):
            return True

        def search(self, *a, **k):
            raise RuntimeError("indeks rusak")

    ml = MlState(tmp_settings, BridgeSettings(embedder="none"))
    ml._vs = _VS()
    assert ml.prewarm() is False


# ---------------------------------------------------------------------------
# Metadata yang melampaui batas kolom backend (insiden VPS 13 Okt 2026)
#
# Lembar ringkasan SEOJK satu halaman: judul terbaca 298 karakter (potongan butir
# isi) dan nomor terbaca nomor peraturan LAIN yang disebut sebagai dicabut. PATCH
# menjawab 200, lalu commit penempatan meledak di varchar(255); dokumen tetap
# 'diproses' dan diklaim ulang tanpa akhir.
# ---------------------------------------------------------------------------
class _MdKop:
    def __init__(self, subject, number="31/SEOJK.03/2025", doc_type="SEOJK", title=None, issued=None):
        self.subject, self.number, self.doc_type = subject, number, doc_type
        self.title = title or subject
        self.issued_date = issued


def test_judul_dipotong_ke_batas_kolom_backend_di_batas_kata():
    md = _MdKop("Pelaporan Bank Umum " + "butir isi yang bukan judul " * 30)
    assert len(md.subject) > 255
    p = mapping.extraction_payload(md, "teks", send_full_text=False)
    assert len(p["title"]) <= 255
    assert p["title"].endswith("…") and not p["title"][:-1].endswith(" ")
    assert p["title"].startswith("Pelaporan Bank Umum")


def test_semua_kolom_string_dibatasi_sesuai_skema_backend():
    md = _MdKop("x " * 400, number="N" * 300, doc_type="J" * 300)
    p = mapping.extraction_payload(md, "teks", bidang="B" * 400, engine="E" * 300, send_full_text=False)
    for kolom, batas in mapping.BATAS_KOLOM.items():
        assert len(p[kolom] or "") <= batas, kolom


def test_judul_normal_tidak_diubah_sama_sekali():
    md = _MdKop("PELAPORAN BANK UMUM KONVENSIONAL MELALUI SISTEM PELAPORAN")
    p = mapping.extraction_payload(md, "teks", send_full_text=False)
    assert p["title"] == "PELAPORAN BANK UMUM KONVENSIONAL MELALUI SISTEM PELAPORAN"


def test_kop_gagal_dibaca_menurunkan_keyakinan_agar_masuk_antrean_koreksi():
    """Ambang backend 0,7. Tanpa ini nomor yang salah lolos sebagai 'terindeks'."""
    rusak = _MdKop("kalimat isi " * 30)
    conf = mapping.extraction_payload(rusak, "teks", send_full_text=False)["confidence"]
    assert mapping.header_gagal_dibaca(rusak)
    assert conf and all(v < 0.7 for v in conf.values()), conf

    sehat = _MdKop("PELAPORAN BANK UMUM KONVENSIONAL")
    conf2 = mapping.extraction_payload(sehat, "teks", send_full_text=False)["confidence"]
    assert not mapping.header_gagal_dibaca(sehat)
    assert conf2["title"] >= 0.7 and conf2["regulation_number"] >= 0.7


def test_fit_tidak_memotong_kata_dan_menjaga_panjang_total():
    assert mapping._fit("abc def", 20) == "abc def"
    assert mapping._fit("", 5) is None and mapping._fit(None, 5) is None
    hasil = mapping._fit("kata " * 100, 50)
    assert len(hasil) <= 50 and hasil.endswith("…")
    assert mapping._fit("satu_kata_sangat_panjang_tanpa_spasi", 12) == "satu_kata_s…"


def test_status_tetap_diproses_dilaporkan_bukan_dianggap_sukses_diam_diam(
        tmp_settings, tmp_path, regulation_pdf, caplog):
    import logging

    pdf = regulation_pdf(tmp_path / "pojk.pdf")
    be = FakeBackend(pdf, status="diproses")        # PATCH 200, tetapi tidak pernah final
    w, st = _worker(tmp_settings, be, tmp_path)
    with caplog.at_level(logging.WARNING, logger="hero.bridge.extract"):
        out = w.process_one({"document_id": 9, "file_hash": "h", "attempt": 1})
    assert "backend belum menuntaskan" in out.detail
    assert any("status tetap 'diproses'" in r.message for r in caplog.records)
    st.close()


# ---------------------------------------------------------------------------
# Byte NUL (insiden VPS 13 Okt: dokumen 137 'PostgreSQL text fields cannot contain NUL')
# ---------------------------------------------------------------------------
def test_byte_nul_dibuang_dari_teks_penuh_judul_dan_pasal():
    nul = "\x00"
    md = _MdKop("PELAPORAN" + nul + " BANK")
    p = mapping.extraction_payload(md, "isi" + nul + "teks" + nul, send_full_text=True)
    assert nul not in p["full_text"] and p["full_text"] == "isiteks"
    assert nul not in p["title"] and p["title"] == "PELAPORAN BANK"

    rows = mapping.article_payloads(
        1, [_Art("Pasal 1", "Bank" + nul + " wajib", bab="BAB" + nul + " I",
                 ayat=[("1", "ayat" + nul + " satu")])],
        push_ayat=True, with_parent=True)
    for r in rows:
        for k, v in r.items():
            if isinstance(v, str):
                assert nul not in v, (k, v)
    assert rows[0]["content_text"] == "Bank wajib"


def test_karakter_kontrol_lain_tidak_diubah_hanya_nul():
    """PostgreSQL hanya menolak NUL; menghapus sisanya akan mengubah teks tanpa alasan."""
    assert mapping.bersihkan_teks("a\x0cb\tc\nd") == "a\x0cb\tc\nd"
    assert mapping.bersihkan_teks("\x00\x00") == ""
    assert mapping.bersihkan_teks(None) == "" and mapping.bersihkan_teks("") == ""
