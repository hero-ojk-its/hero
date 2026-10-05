"""
tests/test_placement.py
Pengujian otomatis untuk penamaan baku dan penempatan folder KB (Langkah 3: P01-P11).
"""
import io
from datetime import date
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.models.category import Category
from app.models.document import Document
from app.services.storage_service import StorageService
from app.services.file_validation import fingerprint
from tests.conftest import make_pdf


def test_p01_single_upload_with_full_metadata_auto_placed(client: TestClient, db_session: Session, test_storage: StorageService):
    """P01: Unggah tunggal dengan metadata lengkap -> Berkas otomatis dipindah ke kb/POJK/2022/<nama baku>, placement.placed=true."""
    pdf_bytes = make_pdf("Dokumen regulasi POJK 11/2022 P01")
    files = [("files", ("raw_original_name.pdf", io.BytesIO(pdf_bytes), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "regulation_number": "11/POJK.03/2022",
        "regulation_type": "POJK",
        "release_date": "2022-07-07",
        "title": "Penyelenggaraan Teknologi Informasi oleh Bank Umum",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["success_count"] == 1
    detail = res_data["details"][0]
    assert detail["placement"]["placed"] is True
    assert detail["placement"]["category_path"] == ["POJK", "2022"]

    doc = db_session.query(Document).filter(Document.id == detail["document_id"]).first()
    assert doc is not None
    assert doc.file_path_pdf.startswith("kb/POJK/2022/")
    assert doc.file_path_pdf.endswith("11-POJK.03-2022 Penyelenggaraan Teknologi Informasi oleh Bank Umum 2022.pdf")
    assert test_storage.exists(doc.file_path_pdf)
    # Tidak tersisa di pdf/_inbox
    assert not test_storage.exists("pdf/_inbox/raw_original_name.pdf")


def test_p02_batch_upload_without_metadata_remains_in_inbox(client: TestClient, db_session: Session, test_storage: StorageService):
    """P02: Unggah jamak tanpa metadata -> Berkas di pdf/_inbox/, category_id null, placement.reason='metadata_belum_cukup'."""
    pdf1 = make_pdf("Batch doc 1 P02")
    pdf2 = make_pdf("Batch doc 2 P02")
    files = [
        ("files", ("batch1.pdf", io.BytesIO(pdf1), "application/pdf")),
        ("files", ("batch2.pdf", io.BytesIO(pdf2), "application/pdf")),
    ]
    data = {
        "access_classification": "non_publik",
        "document_role": "corpus_eksisting",
    }
    res = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    assert res.status_code == 200
    for item in res.json()["details"]:
        assert item["placement"]["placed"] is False
        assert item["placement"]["reason"] == "metadata_belum_cukup"
        doc = db_session.query(Document).filter(Document.id == item["document_id"]).first()
        assert doc.file_path_pdf.startswith("pdf/_inbox/")
        assert doc.category_id is None
        assert test_storage.exists(doc.file_path_pdf)


def test_p03_manual_trigger_place_after_metadata_update(client: TestClient, db_session: Session, test_storage: StorageService):
    """P03: Set metadata dokumen P02 di DB -> POST /documents/{id}/place -> Pindah ke kb/..., hash cocok."""
    pdf_bytes = make_pdf("Dokumen P03 yang baru dilengkapi metadata")
    fp = fingerprint(pdf_bytes)
    rel_path = test_storage.save_pdf(pdf_bytes, filename_hint=f"{fp.sha256[:12]}_doc_p03.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Peraturan P03 Baru",
        file_path_pdf=rel_path,
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
        regulation_number="15/POJK.03/2021",
        regulation_type="POJK",
        release_date=date(2021, 8, 1),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    res = client.post(f"/api/v1/documents/{doc.id}/place")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["placed"] is True
    assert res_data["reason"] == "ditempatkan"
    assert res_data["new_path"].startswith("kb/POJK/2021/")

    db_session.refresh(doc)
    assert test_storage.exists(doc.file_path_pdf)
    assert not test_storage.exists(rel_path)
    file_bytes_on_disk = test_storage.read_pdf(doc.file_path_pdf)
    assert fingerprint(file_bytes_on_disk).sha256 == doc.file_hash


def test_p04_duplicate_metadata_different_docs_non_overwrite(client: TestClient, db_session: Session, test_storage: StorageService):
    """P04: Dua dokumen berbeda dengan metadata identik -> Nama kedua bersufiks -1, kedua berkas utuh & hash sesuai."""
    pdf1 = make_pdf("Konten unik 1 untuk metadata sama")
    pdf2 = make_pdf("Konten unik 2 untuk metadata sama")

    # Upload doc 1
    res1 = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("doc1.pdf", io.BytesIO(pdf1), "application/pdf"))],
        data={
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "regulation_number": "5/POJK.01/2023",
            "regulation_type": "POJK",
            "release_date": "2023-03-01",
            "title": "Ketentuan Sama",
        },
    )
    assert res1.status_code == 200
    doc_id_1 = res1.json()["details"][0]["document_id"]
    doc1 = db_session.query(Document).filter(Document.id == doc_id_1).first()

    # Upload doc 2 dengan metadata identik tapi isi bytes berbeda
    res2 = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("doc2.pdf", io.BytesIO(pdf2), "application/pdf"))],
        data={
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "regulation_number": "5/POJK.01/2023",
            "regulation_type": "POJK",
            "release_date": "2023-03-01",
            "title": "Ketentuan Sama",
        },
    )
    assert res2.status_code == 200
    doc_id_2 = res2.json()["details"][0]["document_id"]
    doc2 = db_session.query(Document).filter(Document.id == doc_id_2).first()

    assert doc1.file_path_pdf != doc2.file_path_pdf
    assert "-1.pdf" in doc2.file_path_pdf
    assert test_storage.exists(doc1.file_path_pdf)
    assert test_storage.exists(doc2.file_path_pdf)
    assert test_storage.read_pdf(doc1.file_path_pdf) == pdf1
    assert test_storage.read_pdf(doc2.file_path_pdf) == pdf2


def test_p05_explicit_category_id_placement(client: TestClient, db_session: Session, test_storage: StorageService):
    """P05: Unggah dengan category_id eksplisit (mis. Peraturan Internal DPEA) + metadata cukup -> Berkas di folder kategori tsb."""
    cat = db_session.query(Category).filter(Category.name == "Peraturan Internal DPEA").first()
    assert cat is not None

    pdf_bytes = make_pdf("Peraturan Internal DPEA P05")
    res = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("internal.pdf", io.BytesIO(pdf_bytes), "application/pdf"))],
        data={
            "access_classification": "non_publik",
            "document_role": "corpus_eksisting",
            "category_id": str(cat.id),
            "regulation_number": "INT-01/2022",
            "regulation_type": "INTERNAL",
            "release_date": "2022-01-10",
            "title": "Pedoman Kerja DPEA",
        },
    )
    assert res.status_code == 200
    doc_id = res.json()["details"][0]["document_id"]
    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc.file_path_pdf.startswith("kb/Peraturan Internal DPEA/")
    assert test_storage.exists(doc.file_path_pdf)


def test_p06_draft_kajian_placement(client: TestClient, db_session: Session, test_storage: StorageService):
    """P06: Unggah draft_kajian dengan metadata cukup -> Berkas di kb/Draft Kajian/<tahun>/..."""
    pdf_bytes = make_pdf("Draft Kajian Regulasi 2024 P06")
    res = client.post(
        "/api/v1/ingest/upload-pdf",
        files=[("files", ("draft.pdf", io.BytesIO(pdf_bytes), "application/pdf"))],
        data={
            "access_classification": "non_publik",
            "document_role": "draft_kajian",
            "regulation_number": "DK-01/2024",
            "release_date": "2024-05-15",
            "title": "Kajian Implementasi AI",
        },
    )
    assert res.status_code == 200
    doc_id = res.json()["details"][0]["document_id"]
    doc = db_session.query(Document).filter(Document.id == doc_id).first()
    assert doc.file_path_pdf.startswith("kb/Draft Kajian/2024/")
    assert test_storage.exists(doc.file_path_pdf)


def test_p07_get_categories_tree_nested(client: TestClient, db_session: Session):
    """P07: GET /categories/tree -> Bertingkat, total_document_count akar POJK mencakup dokumen di 2022."""
    # Pastikan kategori POJK dan subkategori 2022 ada
    pojk_root = db_session.query(Category).filter(Category.name == "POJK", Category.parent_id.is_(None)).first()
    cat_2022 = Category(name="2022", parent_id=pojk_root.id, auto_created=True)
    db_session.add(cat_2022)
    db_session.commit()
    db_session.refresh(cat_2022)

    # Tambah dokumen di bawah subkategori 2022
    pdf_bytes = make_pdf("Doc under 2022")
    fp = fingerprint(pdf_bytes)
    doc = Document(
        title="Dokumen di 2022",
        file_path_pdf="kb/POJK/2022/test.pdf",
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
        category_id=cat_2022.id,
    )
    db_session.add(doc)
    db_session.commit()

    res = client.get("/api/v1/categories/tree")
    assert res.status_code == 200
    tree = res.json()
    pojk_node = next((node for node in tree if node["name"] == "POJK"), None)
    assert pojk_node is not None
    assert pojk_node["total_document_count"] >= 1
    child_2022 = next((c for c in pojk_node["children"] if c["name"] == "2022"), None)
    assert child_2022 is not None
    assert child_2022["document_count"] == 1


def test_p08_post_categories_duplicate_rejected(client: TestClient, db_session: Session):
    """P08: POST /categories duplikat nama di induk yang sama -> 409 Conflict."""
    pojk_root = db_session.query(Category).filter(Category.name == "POJK").first()

    # Buat subkategori
    res1 = client.post("/api/v1/categories/", json={"name": "2025", "parent_id": pojk_root.id})
    assert res1.status_code == 201

    # Coba buat lagi dengan nama yang sama di parent yang sama
    res2 = client.post("/api/v1/categories/", json={"name": "2025", "parent_id": pojk_root.id})
    assert res2.status_code == 409


def test_p09_placement_rollback_on_commit_failure(client: TestClient, db_session: Session, test_storage: StorageService, monkeypatch):
    """P09: Simulasi commit gagal saat place -> Berkas kembali ke old_path, baris DB tidak berubah."""
    pdf_bytes = make_pdf("Dokumen P09 rollback test")
    fp = fingerprint(pdf_bytes)
    old_rel = test_storage.save_pdf(pdf_bytes, filename_hint=f"{fp.sha256[:12]}_doc_p09.pdf", subdir="pdf/_inbox")

    doc = Document(
        title="Dokumen Rollback P09",
        file_path_pdf=old_rel,
        file_hash=fp.sha256,
        file_size_bytes=fp.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
        regulation_number="99/POJK.03/2023",
        regulation_type="POJK",
        release_date=date(2023, 9, 9),
    )
    db_session.add(doc)
    db_session.commit()
    db_session.refresh(doc)

    # Monkeypatch commit saat place agar gagal
    orig_commit = db_session.commit
    def failing_commit():
        raise Exception("DB error saat place commit")

    monkeypatch.setattr(db_session, "commit", failing_commit)

    res = client.post(f"/api/v1/documents/{doc.id}/place")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["placed"] is False
    assert "gagal" in res_data["reason"]

    # Berkas harus tetap berada di old_rel
    assert test_storage.exists(old_rel)


def test_p10_place_pending_endpoint(client: TestClient, db_session: Session, test_storage: StorageService):
    """P10: POST /documents/place-pending -> Hanya dokumen dengan metadata cukup yang dipindah."""
    # Doc 1: Metadata cukup
    pdf1 = make_pdf("Doc 1 place pending")
    fp1 = fingerprint(pdf1)
    p1 = test_storage.save_pdf(pdf1, filename_hint=f"{fp1.sha256[:12]}_doc1.pdf", subdir="pdf/_inbox")
    d1 = Document(
        title="Doc 1",
        file_path_pdf=p1,
        file_hash=fp1.sha256,
        file_size_bytes=fp1.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
        regulation_number="1/UU/2020",
        regulation_type="UU",
        release_date=date(2020, 1, 1),
    )

    # Doc 2: Metadata belum cukup
    pdf2 = make_pdf("Doc 2 place pending no meta")
    fp2 = fingerprint(pdf2)
    p2 = test_storage.save_pdf(pdf2, filename_hint=f"{fp2.sha256[:12]}_doc2.pdf", subdir="pdf/_inbox")
    d2 = Document(
        title="Doc 2 No Meta",
        file_path_pdf=p2,
        file_hash=fp2.sha256,
        file_size_bytes=fp2.size_bytes,
        access_classification="publik",
        document_role="corpus_eksisting",
    )
    db_session.add_all([d1, d2])
    db_session.commit()

    res = client.post("/api/v1/documents/place-pending?limit=10")
    assert res.status_code == 200
    res_data = res.json()
    assert res_data["placed"] == 1
    assert res_data["skipped"] == 1

    db_session.refresh(d1)
    db_session.refresh(d2)
    assert d1.file_path_pdf.startswith("kb/UU/2020/")
    assert d2.file_path_pdf.startswith("pdf/_inbox/")


def test_p11_get_document_detail_contains_placement_info(client: TestClient, db_session: Session, test_storage: StorageService):
    """P11: GET /documents/{id} -> Memuat category_path dan is_placed."""
    pdf = make_pdf("Doc P11 info")
    files = [("files", ("p11.pdf", io.BytesIO(pdf), "application/pdf"))]
    data = {
        "access_classification": "publik",
        "document_role": "corpus_eksisting",
        "regulation_number": "7/PP/2022",
        "regulation_type": "PP",
        "release_date": "2022-04-01",
        "title": "Peraturan Pemerintah P11",
    }
    res_up = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
    doc_id = res_up.json()["details"][0]["document_id"]

    res_doc = client.get(f"/api/v1/documents/{doc_id}")
    assert res_doc.status_code == 200
    doc_json = res_doc.json()
    assert "category_path" in doc_json
    assert doc_json["category_path"] == ["PP", "2022"]
    assert doc_json["is_placed"] is True
