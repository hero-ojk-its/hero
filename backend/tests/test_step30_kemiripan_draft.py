"""
tests/test_step30_kemiripan_draft.py
Pengujian Langkah 30: Kemiripan draft berulang (persen teks) dan perbandingan per pasal antar-draft.
Kasus Uji: D01 - D14.
"""
import hashlib
import io
from datetime import datetime, timezone
from unittest.mock import patch

import bcrypt
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import PeranPengguna
from app.models.article import Article
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen, StatusPemrosesan
from app.models.user import User


def make_test_pdf(text: str = "PDF Uji Kemiripan") -> bytes:
    """PDF helper minimal untuk pengujian."""
    raw = text.encode("utf-8")
    length = len(raw)
    return (
        b"%PDF-1.4\n1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + raw
        + b"\nendstream\nendobj\nxref\n0 5\n"
        b"0000000000 65535 f \n0000000009 00000 n \n0000000058 00000 n \n0000000115 00000 n \n0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\nstartxref\n300\n%%EOF\n"
    )


def create_draft(
    db: Session,
    title: str,
    full_text: str | None = None,
    role: PeranDokumen = PeranDokumen.draft_kajian,
    access: KlasifikasiAkses = KlasifikasiAkses.publik,
    status: StatusPemrosesan = StatusPemrosesan.terindeks,
    is_active: bool = True,
    filename: str = "draft.pdf",
    file_path: str | None = None,
    file_hash: str | None = None,
    file_size_bytes: int = 1024,
) -> Document:
    """Helper membuat dokumen draft kajian di DB."""
    if file_path is None:
        file_path = f"kb/Draft Kajian/{title}_{filename}"
    if file_hash is None:
        file_hash = hashlib.sha256(f"{title}_{file_path}_{full_text}".encode("utf-8")).hexdigest()
    doc = Document(
        title=title,
        original_filename=filename,
        file_path_pdf=file_path,
        file_hash=file_hash,
        file_size_bytes=file_size_bytes,
        full_text=full_text,
        document_role=role,
        access_classification=access,
        processing_status=status,
        is_active=is_active,
        created_at=datetime.now(timezone.utc),
    )
    db.add(doc)
    db.commit()
    db.refresh(doc)
    return doc


# ============================================================================
# D01: Dua draft dengan teks identik (byte PDF berbeda)
# Ekspektasi: persen >= 99.5, status=identik
# ============================================================================
def test_d01_draft_teks_identik(client: TestClient, db_session: Session):
    teks_regulasi = (
        "Ketentuan permodalan bank umum syariah wajib memenuhi rasio kecukupan modal "
        "minimal dua belas persen dari aset tertimbang menurut risiko. Pelanggaran atas "
        "ketentuan ini dikenai sanksi administratif dan penghentian kegiatan usaha sementara."
    )
    doc_a = create_draft(
        db_session,
        title="Draft A Identik",
        full_text=teks_regulasi,
        file_path="kb/Draft Kajian/draft_a.pdf",
    )
    doc_b = create_draft(
        db_session,
        title="Draft B Identik",
        full_text=teks_regulasi,
        file_path="kb/Draft Kajian/draft_b.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["document_id"] == doc_b.id
    assert data["dibandingkan"] >= 1
    assert data["terdekat"] is not None
    assert data["terdekat"]["document_id"] == doc_a.id
    assert data["terdekat"]["persen"] >= 99.5

    assert len(data["draft_mirip"]) >= 1
    mirip_a = next(d for d in data["draft_mirip"] if d["document_id"] == doc_a.id)
    assert mirip_a["status"] == "identik"
    assert mirip_a["persen"] >= 99.5


# ============================================================================
# D02: Draft B = draft A dengan 1 dari 20 paragraf diubah
# Ekspektasi: persen di antara ambang (80.0) dan 99.5, status=sangat_mirip
# ============================================================================
def test_d02_draft_sangat_mirip(client: TestClient, db_session: Session):
    paragraf_dasar = [
        f"Paragraf nomor {i} memuat ketentuan tata kelola operasional lembaga keuangan syariah "
        f"terkait kepatuhan syariah dan manajemen risiko likuiditas perbankan nasional."
        for i in range(1, 21)
    ]
    teks_a = "\n\n".join(paragraf_dasar)

    paragraf_b = list(paragraf_dasar)
    paragraf_b[19] = (
        "Paragraf nomor 20 diubah total memuat mekanisme penyelesaian sengketa alternatif "
        "melalui mediasi perbankan dan arbitrase syariah internasional di Jakarta."
    )
    teks_b = "\n\n".join(paragraf_b)

    doc_a = create_draft(
        db_session,
        title="Draft A Revisi 1",
        full_text=teks_a,
        file_path="kb/Draft Kajian/d02_a.pdf",
    )
    doc_b = create_draft(
        db_session,
        title="Draft B Revisi 2",
        full_text=teks_b,
        file_path="kb/Draft Kajian/d02_b.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    mirip_a = next(d for d in data["draft_mirip"] if d["document_id"] == doc_a.id)
    assert 80.0 <= mirip_a["persen"] < 99.5
    assert mirip_a["status"] == "sangat_mirip"


# ============================================================================
# D03: Draft tak terkait
# Ekspektasi: tidak masuk draft_mirip; terdekat tetap terisi dengan persen rendah
# ============================================================================
def test_d03_draft_tak_terkait(client: TestClient, db_session: Session):
    teks_hukum = (
        "Peraturan Otoritas Jasa Keuangan tentang tata kelola bank umum konvensional "
        "dan penerapan fungsi kepatuhan audit internal lembaga jasa keuangan perbankan."
    )
    teks_resep = (
        "Resep memasak rendang daging sapi tradisional Minangkabau dengan santan kental, "
        "rempah kelapa sangrai, cabai merah keriting, bawang merah, lengkuas, serai, daun jeruk."
    )

    doc_a = create_draft(
        db_session,
        title="Draft POJK Tata Kelola",
        full_text=teks_hukum,
        file_path="kb/Draft Kajian/d03_a.pdf",
    )
    doc_c = create_draft(
        db_session,
        title="Draft Resep Kuliner",
        full_text=teks_resep,
        file_path="kb/Draft Kajian/d03_c.pdf",
    )

    # Bandingkan doc_a (hanya doc_c sebagai kandidat pembanding relevan)
    resp = client.get(f"/api/v1/documents/{doc_a.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    # doc_c tidak boleh ada di draft_mirip
    mirip_ids = [d["document_id"] for d in data["draft_mirip"]]
    assert doc_c.id not in mirip_ids

    # terdekat tetap terisi dengan doc_c dan persen rendah (< 80)
    assert data["terdekat"] is not None
    assert data["terdekat"]["document_id"] == doc_c.id
    assert data["terdekat"]["persen"] < 80.0


# ============================================================================
# D04: ambang=95 vs ambang=50 pada data D02
# Ekspektasi: keanggotaan draft_mirip berubah sesuai ambang
# ============================================================================
def test_d04_ambang_dinamis(client: TestClient, db_session: Session):
    paragraf_dasar = [
        f"Paragraf nomor {i} memuat ketentuan tata kelola operasional lembaga keuangan syariah "
        f"terkait kepatuhan syariah dan manajemen risiko likuiditas perbankan nasional."
        for i in range(1, 21)
    ]
    teks_a = "\n\n".join(paragraf_dasar)

    paragraf_b = list(paragraf_dasar)
    paragraf_b[19] = (
        "Paragraf nomor 20 diubah total memuat mekanisme penyelesaian sengketa alternatif "
        "melalui mediasi perbankan dan arbitrase syariah internasional di Jakarta."
    )
    teks_b = "\n\n".join(paragraf_b)

    doc_a = create_draft(
        db_session,
        title="Draft A D04",
        full_text=teks_a,
        file_path="kb/Draft Kajian/d04_a.pdf",
    )
    doc_b = create_draft(
        db_session,
        title="Draft B D04",
        full_text=teks_b,
        file_path="kb/Draft Kajian/d04_b.pdf",
    )

    # Uji ambang ketat (95%): kemiripan ~90% tidak masuk
    resp_95 = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft?ambang=95")
    assert resp_95.status_code == 200
    data_95 = resp_95.json()
    mirip_95_ids = [d["document_id"] for d in data_95["draft_mirip"]]
    assert doc_a.id not in mirip_95_ids

    # Uji ambang longgar (50%): kemiripan ~90% masuk
    resp_50 = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft?ambang=50")
    assert resp_50.status_code == 200
    data_50 = resp_50.json()
    mirip_50_ids = [d["document_id"] for d in data_50["draft_mirip"]]
    assert doc_a.id in mirip_50_ids


# ============================================================================
# D05: Per pasal: A punya Pasal 1–4; B punya Pasal 1 sama, Pasal 2 diubah, Pasal 3 dihapus, Pasal 5 baru
# Ekspektasi: ringkas = {sama:2, berubah:1, baru:1, dihapus:1} dan status per pasal benar
# ============================================================================
def test_d05_perbandingan_per_pasal(client: TestClient, db_session: Session):
    teks_dasar = " ".join([
        f"Ketentuan peraturan perbankan syariah bagian {i} mengatur tata kelola modal dan risiko likuiditas lembaga keuangan."
        for i in range(1, 20)
    ])
    teks_a = f"{teks_dasar}\nPasal 1 Ketentuan umum.\nPasal 2 Modal disetor.\nPasal 3 Dewan pengawas.\nPasal 4 Ketentuan penutup."
    teks_b = f"{teks_dasar}\nPasal 1 Ketentuan umum.\nPasal 2 Modal disetor dua puluh triliun tunai.\nPasal 4 Ketentuan penutup.\nPasal 5 Sanksi denda."

    doc_a = create_draft(
        db_session,
        title="Draft A Pasal",
        full_text=teks_a,
        file_path="kb/Draft Kajian/d05_a.pdf",
    )
    doc_b = create_draft(
        db_session,
        title="Draft B Pasal",
        full_text=teks_b,
        file_path="kb/Draft Kajian/d05_b.pdf",
    )

    # Seed pasal untuk Draft A (Pasal 1 s.d. 4)
    db_session.add_all([
        Article(
            document_id=doc_a.id,
            article_number="Pasal 1",
            content_text="Ketentuan umum definisi bank dan nasabah perbankan syariah.",
            order_index=1,
            parent_id=None,
        ),
        Article(
            document_id=doc_a.id,
            article_number="Pasal 2",
            content_text="Modal disetor bank umum syariah minimal sepuluh triliun rupiah.",
            order_index=2,
            parent_id=None,
        ),
        Article(
            document_id=doc_a.id,
            article_number="Pasal 3",
            content_text="Kewajiban pembentukan dewan pengawas syariah pada setiap kantor cabang.",
            order_index=3,
            parent_id=None,
        ),
        Article(
            document_id=doc_a.id,
            article_number="Pasal 4",
            content_text="Peraturan ini mulai berlaku efektif pada tanggal diundangkan.",
            order_index=4,
            parent_id=None,
        ),
    ])

    # Seed pasal untuk Draft B (Pasal 1 sama, Pasal 2 diubah, Pasal 4 sama, Pasal 5 baru)
    db_session.add_all([
        Article(
            document_id=doc_b.id,
            article_number="Pasal 1",
            content_text="Ketentuan umum definisi bank dan nasabah perbankan syariah.",
            order_index=1,
            parent_id=None,
        ),
        Article(
            document_id=doc_b.id,
            article_number="Pasal 2",
            content_text="Modal disetor bank umum syariah minimal dua puluh triliun rupiah disetor tunai.",
            order_index=2,
            parent_id=None,
        ),
        Article(
            document_id=doc_b.id,
            article_number="Pasal 4",
            content_text="Peraturan ini mulai berlaku efektif pada tanggal diundangkan.",
            order_index=3,
            parent_id=None,
        ),
        Article(
            document_id=doc_b.id,
            article_number="Pasal 5",
            content_text="Sanksi denda keterlambatan pelaporan dihitung proporsional harian.",
            order_index=4,
            parent_id=None,
        ),
    ])
    db_session.commit()

    # Gunakan ambang=50 agar lolos perhitungan per_pasal
    resp = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft?ambang=50")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["per_pasal"] is not None
    assert data["per_pasal"]["dibanding_dengan"] == doc_a.id

    ringkas = data["per_pasal"]["ringkas"]
    assert ringkas == {"sama": 2, "berubah": 1, "baru": 1, "dihapus": 1}

    pasal_list = data["per_pasal"]["pasal"]
    pasal_map = {p["pasal"]: p for p in pasal_list}

    assert pasal_map["Pasal 1"]["status"] == "sama"
    assert pasal_map["Pasal 2"]["status"] == "berubah"
    assert "persen" in pasal_map["Pasal 2"]
    assert pasal_map["Pasal 3"]["status"] == "dihapus"
    assert pasal_map["Pasal 4"]["status"] == "sama"
    assert pasal_map["Pasal 5"]["status"] == "baru"


# ============================================================================
# D06: Salah satu draft tanpa articles
# Ekspektasi: per_pasal=null, catatan sesuai
# ============================================================================
def test_d06_draft_tanpa_articles(client: TestClient, db_session: Session):
    teks = "Draft substansi regulasi tanpa pemecahan pasal ke tabel articles."
    doc_a = create_draft(
        db_session,
        title="Draft A Tanpa Pasal",
        full_text=teks,
        file_path="kb/Draft Kajian/d06_a.pdf",
    )
    doc_b = create_draft(
        db_session,
        title="Draft B Tanpa Pasal",
        full_text=teks,
        file_path="kb/Draft Kajian/d06_b.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_b.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["terdekat"]["document_id"] == doc_a.id
    assert data["terdekat"]["persen"] >= 80.0
    assert data["per_pasal"] is None
    assert data["catatan"] == "perbandingan per pasal belum tersedia (pasal belum dipecah)"


# ============================================================================
# D07: Dokumen corpus_eksisting
# Ekspektasi: 422 "Kemiripan draft hanya untuk dokumen draft kajian"
# ============================================================================
def test_d07_dokumen_corpus_eksisting_422(client: TestClient, db_session: Session):
    doc = create_draft(
        db_session,
        title="POJK Corpus Eksisting",
        full_text="Peraturan OJK yang sudah berlaku definitif.",
        role=PeranDokumen.corpus_eksisting,
        file_path="kb/POJK/2026/pojk.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc.id}/kemiripan-draft")
    assert resp.status_code == 422, resp.text
    assert "Kemiripan draft hanya untuk dokumen draft kajian" in resp.json()["detail"]


# ============================================================================
# D08: Draft belum diekstraksi (full_text null)
# Ekspektasi: 409 "Draft belum selesai diekstraksi"
# ============================================================================
def test_d08_draft_belum_ekstraksi_409(client: TestClient, db_session: Session):
    doc = create_draft(
        db_session,
        title="Draft Baru Diunggah",
        full_text=None,
        file_path="kb/Draft Kajian/d08.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc.id}/kemiripan-draft")
    assert resp.status_code == 409, resp.text
    assert "Draft belum selesai diekstraksi" in resp.json()["detail"]


# ============================================================================
# D09: Draft lain non-publik saat auth mati
# Ekspektasi: tidak muncul di draft_mirip maupun terdekat; dibandingkan tidak menghitungnya
# ============================================================================
def test_d09_draft_lain_nonpublik_auth_mati(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)

    teks = "Naskah akademik rahasia perbankan syariah tertutup."
    doc_target = create_draft(
        db_session,
        title="Draft Target Publik",
        full_text=teks,
        access=KlasifikasiAkses.publik,
        file_path="kb/Draft Kajian/d09_pub.pdf",
    )
    doc_rahasia = create_draft(
        db_session,
        title="Draft Rahasia Non-Publik",
        full_text=teks,
        access=KlasifikasiAkses.non_publik,
        file_path="kb/Draft Kajian/d09_rahasia.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    mirip_ids = [d["document_id"] for d in data["draft_mirip"]]
    assert doc_rahasia.id not in mirip_ids
    if data["terdekat"] is not None:
        assert data["terdekat"]["document_id"] != doc_rahasia.id


# ============================================================================
# D10: Draft target non-publik saat auth mati
# Ekspektasi: 403 (sama seperti membuka dokumen)
# ============================================================================
def test_d10_target_nonpublik_auth_mati_403(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", False)
    monkeypatch.setattr(settings, "protect_non_public_when_auth_disabled", True)

    doc_rahasia = create_draft(
        db_session,
        title="Draft Target Rahasia",
        full_text="Teks rahasia internal draft kajian.",
        access=KlasifikasiAkses.non_publik,
        file_path="kb/Draft Kajian/d10_rahasia.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_rahasia.id}/kemiripan-draft")
    assert resp.status_code == 403, resp.text


# ============================================================================
# D11: Auth aktif, token tanpa KB_BACA
# Ekspektasi: 403
# ============================================================================
def test_d11_auth_aktif_token_tanpa_kb_baca_403(client: TestClient, db_session: Session, monkeypatch):
    monkeypatch.setattr(settings, "auth_enabled", True)

    # Buat pengguna pilot_user (tanpa KB_BACA)
    plain_pw = "PilotSecret123!"
    hashed_pw = bcrypt.hashpw(plain_pw.encode("utf-8"), bcrypt.gensalt()).decode("utf-8")
    user = db_session.query(User).filter(User.username == "pilot_user_d11").first()
    if not user:
        user = User(
            username="pilot_user_d11",
            hashed_password=hashed_pw,
            role=PeranPengguna.pilot_user.value,
            nama_lengkap="Pengguna Pilot D11",
            unit_kerja="Unit Pilot",
            is_active=True,
        )
        db_session.add(user)
        db_session.commit()

    # Login untuk mendapatkan access token
    login_res = client.post(
        "/api/v1/auth/login",
        data={"username": "pilot_user_d11", "password": plain_pw},
    )
    assert login_res.status_code == 200, login_res.text
    token = login_res.json()["access_token"]

    doc = create_draft(
        db_session,
        title="Draft Publik D11",
        full_text="Ketentuan umum draft publik untuk uji izin otorisasi.",
        file_path="kb/Draft Kajian/d11.pdf",
    )

    resp = client.get(
        f"/api/v1/documents/{doc.id}/kemiripan-draft",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403, resp.text


# ============================================================================
# D12: Lebih dari 200 draft
# Ekspektasi: hanya 200 terbaru yang dibandingkan (dibandingkan=200)
# ============================================================================
def test_d12_maksimal_200_draft_terbaru(client: TestClient, db_session: Session):
    doc_target = create_draft(
        db_session,
        title="Target D12",
        full_text="Target naskah regulasi perbankan syariah nasional.",
        file_path="kb/Draft Kajian/d12_target.pdf",
    )

    # Buat 205 dokumen draft kajian
    docs_to_add = [
        Document(
            title=f"Kandidat D12 #{i}",
            original_filename=f"kandidat_{i}.pdf",
            file_path_pdf=f"kb/Draft Kajian/kandidat_{i}.pdf",
            file_hash=hashlib.sha256(f"kandidat_{i}".encode("utf-8")).hexdigest(),
            file_size_bytes=1024,
            full_text=f"Isi kandidat nomor {i} tentang pasar modal dan perasuransian.",
            document_role=PeranDokumen.draft_kajian,
            access_classification=KlasifikasiAkses.publik,
            processing_status=StatusPemrosesan.terindeks,
            is_active=True,
            created_at=datetime.now(timezone.utc),
        )
        for i in range(1, 206)
    ]
    db_session.add_all(docs_to_add)
    db_session.commit()

    resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dibandingkan"] == 200


# ============================================================================
# D13: Batas atas cepat
# Ekspektasi: kandidat yang panjang teksnya sangat berbeda tidak dihitung penuh (spy Jaccard),
# dan hasilnya tetap benar
# ============================================================================
def test_d13_batas_atas_cepat_skip_jaccard(client: TestClient, db_session: Session):
    # Dokumen target panjang (~500 kata)
    teks_panjang = " ".join([f"ketentuan tata kelola kepatuhan hukum perbankan pasal {i}" for i in range(1, 101)])
    doc_target = create_draft(
        db_session,
        title="Target Panjang D13",
        full_text=teks_panjang,
        file_path="kb/Draft Kajian/d13_target.pdf",
    )

    # Kandidat 1: teks sangat pendek (10 karakter / 2 kata), batas < 80%
    teks_sangat_pendek = "halo dunia"
    create_draft(
        db_session,
        title="Kandidat Pendek D13",
        full_text=teks_sangat_pendek,
        file_path="kb/Draft Kajian/d13_pendek.pdf",
    )

    # Kandidat 2: teks seimbang dan mirip target
    doc_mirip = create_draft(
        db_session,
        title="Kandidat Mirip D13",
        full_text=teks_panjang,
        file_path="kb/Draft Kajian/d13_mirip.pdf",
    )

    from app.services import kemiripan_service

    real_persen = kemiripan_service.persen_kemiripan
    call_args_list = []

    def spy_persen(a, b, k=5):
        call_args_list.append((a, b))
        return real_persen(a, b, k=k)

    with patch("app.services.kemiripan_service.persen_kemiripan", side_effect=spy_persen):
        resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft?limit=5")
        assert resp.status_code == 200, resp.text
        data = resp.json()

    # Pastikan teks_sangat_pendek tidak pernah masuk sebagai argumen pemanggilan Jaccard
    for arg_a, arg_b in call_args_list:
        assert arg_a != teks_sangat_pendek
        assert arg_b != teks_sangat_pendek

    # Hasil tetap benar: doc_mirip terdeteksi identik
    assert data["terdekat"]["document_id"] == doc_mirip.id
    assert data["terdekat"]["persen"] >= 99.5
    assert len(data["draft_mirip"]) == 1
    assert data["draft_mirip"][0]["document_id"] == doc_mirip.id


# ============================================================================
# D14: Unggah ulang PDF byte-identik sebagai draft_kajian
# Ekspektasi: tetap duplicate dengan duplicate_of_document_id
# ============================================================================
def test_d14_unggah_ulang_pdf_byte_identik_duplicate(client: TestClient, db_session: Session):
    pdf_content = make_test_pdf("Dokumen Draft Kajian Byte Identik")

    # Unggah pertama
    files1 = [("files", ("draft_kajian_v1.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "draft_kajian",
    }
    resp1 = client.post("/api/v1/ingest/upload-pdf", files=files1, data=data)
    assert resp1.status_code == 200, resp1.text
    body1 = resp1.json()
    assert body1["success_count"] == 1
    first_doc_id = body1["details"][0]["document_id"]

    # Unggah kedua dengan byte yang identik
    files2 = [("files", ("draft_kajian_v2_identik.pdf", io.BytesIO(pdf_content), "application/pdf"))]
    resp2 = client.post("/api/v1/ingest/upload-pdf", files=files2, data=data)
    assert resp2.status_code == 200, resp2.text
    body2 = resp2.json()

    assert body2["duplicate_count"] == 1
    assert body2["details"][0]["status"] == "duplicate"
    assert body2["details"][0]["duplicate_of_document_id"] == first_doc_id


# ============================================================================
# D15: Satu kandidat: teks berbeda total, panjang karakter rasio sekitar 0,7, ambang 80
# Ekspektasi: terdekat.persen = Jaccard sebenarnya (< 20), bukan 70
# ============================================================================
def test_d15_terdekat_angka_kemiripan_sebenarnya_bukan_batas_atas(client: TestClient, db_session: Session):
    # Target: teks perbankan 1000 karakter
    teks_target = ("Ketentuan tata kelola kepatuhan bank syariah dan konvensional nasional. " * 15)[:1000]
    doc_target = create_draft(
        db_session,
        title="Target D15",
        full_text=teks_target,
        file_path="kb/Draft Kajian/d15_target.pdf",
    )

    # Kandidat: teks resep masakan berbeda total, panjang 680 karakter (rasio 68% ~ 0,7)
    # batas = min(1000, 680) / max(1000, 680) * 100 = 68.0%
    # 68.0 < ambang (80) - margin (10) = 70.0 -> dilewati batas atas
    # Karena tidak ada kandidat lain yang dihitung, fallback menghitung kemiripan kandidat ini.
    teks_kandidat = ("Resep membuat rendang daging sapi padang bumbu rempah alami tradisional. " * 15)[:680]
    cand = create_draft(
        db_session,
        title="Kandidat Beda Total D15",
        full_text=teks_kandidat,
        file_path="kb/Draft Kajian/d15_cand.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft?ambang=80")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dibandingkan"] == 1
    assert data["draft_mirip"] == []
    assert data["terdekat"] is not None
    assert data["terdekat"]["document_id"] == cand.id
    # Kemiripan sebenarnya harus jauh lebih kecil dari 20 (bukan ~68 atau ~70)
    assert data["terdekat"]["persen"] < 20.0
    assert data["terdekat"]["persen"] != 68.0


# ============================================================================
# D16: Dua kandidat yang sama-sama dilewati batas atas
# Ekspektasi: terdekat diisi hasil hitung penuh dari kandidat batas tertinggi;
# fungsi Jaccard dipanggil tepat sekali (spy)
# ============================================================================
def test_d16_dua_kandidat_dilewati_hitung_penuh_tertinggi_tepat_sekali(client: TestClient, db_session: Session):
    # Target: teks panjang 1000 karakter
    teks_target = ("Kewajiban kepatuhan regulasi sektor jasa keuangan dan investasi pasar modal. " * 15)[:1000]
    doc_target = create_draft(
        db_session,
        title="Target D16",
        full_text=teks_target,
        file_path="kb/Draft Kajian/d16_target.pdf",
    )

    # Kandidat 1: panjang 400 karakter (rasio 40.0% < 70)
    create_draft(
        db_session,
        title="Kandidat Rasio 40 D16",
        full_text=("Teks singkat resep masakan kuliner khas nusantara daerah pesisir. " * 10)[:400],
        file_path="kb/Draft Kajian/d16_low.pdf",
    )

    # Kandidat 2: panjang 550 karakter (rasio 55.0% < 70, lebih tinggi dari kandidat 1)
    cand_high = create_draft(
        db_session,
        title="Kandidat Rasio 55 D16",
        full_text=("Panduan budidaya tanaman hias hidroponik pekarangan rumah tangga perkotaan. " * 10)[:550],
        file_path="kb/Draft Kajian/d16_high.pdf",
    )

    from app.services import kemiripan_service

    real_persen = kemiripan_service.persen_kemiripan
    call_args_list = []

    def spy_persen(a, b, k=5):
        call_args_list.append((a, b))
        return real_persen(a, b, k=k)

    with patch("app.services.kemiripan_service.persen_kemiripan", side_effect=spy_persen):
        resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft?ambang=80")
        assert resp.status_code == 200, resp.text
        data = resp.json()

    # Fungsi Jaccard dipanggil tepat satu kali (hanya untuk kandidat dengan batas tertinggi)
    assert len(call_args_list) == 1
    assert data["dibandingkan"] == 2
    assert data["draft_mirip"] == []
    assert data["terdekat"] is not None
    assert data["terdekat"]["document_id"] == cand_high.id
    assert data["terdekat"]["persen"] < 20.0


# ============================================================================
# D17: Kandidat isi identik + header/nomor halaman berulang sehingga rasio ~0,75, ambang 80
# Ekspektasi: tidak dilewati; masuk draft_mirip dengan persen >= 80
# ============================================================================
def test_d17_margin_batas_atas_loloskan_kandidat_dengan_header_halaman(client: TestClient, db_session: Session):
    # Dokumen target: teks hukum substansial ~3000 karakter
    paragraf = [
        f"Pasal {i} Ketentuan umum pelaksanaan tata kelola perbankan dan integritas sistem pembayaran digital terpadu."
        for i in range(1, 26)
    ]
    teks_substantif = "\n\n".join(paragraf)
    # Target murni tanpa header halaman
    doc_target = create_draft(
        db_session,
        title="Target Substantif D17",
        full_text=teks_substantif,
        file_path="kb/Draft Kajian/d17_target.pdf",
    )

    # Kandidat: teks substantif yang sama persis, tetapi disisipi header berulang dan nomor halaman:
    # "Halaman 1 dari 25\n- 1 -\nPage 1 of 25\n"
    # sehingga panjang karakter bertambah sekitar 35% (rasio min/max ~ 0.74 - 0.75)
    cand_paragraphs = []
    for i, p in enumerate(paragraf, start=1):
        cand_paragraphs.append(f"Halaman {i} dari 25\n- {i} -\nPage {i} of 25\n{p}")
    teks_kandidat_dengan_header = "\n\n".join(cand_paragraphs)

    cand = create_draft(
        db_session,
        title="Kandidat Dengan Header D17",
        full_text=teks_kandidat_dengan_header,
        file_path="kb/Draft Kajian/d17_cand.pdf",
    )

    # Rasio karakter sekitar 0.75 (antara 70% dan 78%)
    rasio = min(len(teks_substantif), len(teks_kandidat_dengan_header)) / max(len(teks_substantif), len(teks_kandidat_dengan_header)) * 100
    assert 70.0 <= rasio <= 78.0

    resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft?ambang=80")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dibandingkan"] == 1
    # Karena ada margin 10 poin, rasio ~75% tidak dilewati (75 >= 80 - 10 = 70).
    # Karena header & nomor halaman dibersihkan saat normalisasi, isi substantif identik -> persen >= 80
    assert len(data["draft_mirip"]) == 1
    assert data["draft_mirip"][0]["document_id"] == cand.id
    assert data["draft_mirip"][0]["persen"] >= 80.0
    assert data["terdekat"]["document_id"] == cand.id
    assert data["terdekat"]["persen"] >= 80.0


# ============================================================================
# D18: Tanpa kandidat
# Ekspektasi: terdekat = null
# ============================================================================
def test_d18_tanpa_kandidat_terdekat_null(client: TestClient, db_session: Session):
    doc_target = create_draft(
        db_session,
        title="Target Sendirian D18",
        full_text="Ketentuan hukum regulasi tunggal tanpa ada draft pembanding di database sistem.",
        file_path="kb/Draft Kajian/d18_target.pdf",
    )

    resp = client.get(f"/api/v1/documents/{doc_target.id}/kemiripan-draft")
    assert resp.status_code == 200, resp.text
    data = resp.json()

    assert data["dibandingkan"] == 0
    assert data["draft_mirip"] == []
    assert data["terdekat"] is None
    assert data["per_pasal"] is None
    assert data["catatan"] is None
