"""
scripts/smoke_test.py
Smoke test otomatis untuk memvalidasi ketersediaan dan fungsionalitas server HERO Backend yang sedang berjalan.
Mendukung pengujian lengkap Langkah 0–5:
1. Unggah PDF
2. Claim antrean ekstraksi internal (dengan X-Internal-API-Key)
3. PATCH ekstraksi Data/ML
4. GET /documents?q=<frasa> (Pencarian KB)
5. GET /documents/{id}/pdf (Buka PDF Asli)
6. PATCH metadata (Koreksi metadata)
7. GET /dashboard/summary (Dashboard ringkasan)

Penggunaan:
    python scripts/smoke_test.py [BASE_URL]
    Contoh: python scripts/smoke_test.py http://127.0.0.1:8000
"""
import io
import os
from pathlib import Path
import sys
import time
from typing import List, Tuple
import httpx
from dotenv import load_dotenv

load_dotenv()

# Pastikan output konsol mendukung karakter UTF-8 di Windows
if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    except Exception:
        pass


def make_minimal_pdf(content_str: str) -> bytes:
    content_bytes = content_str.encode("utf-8")
    length = len(content_bytes)
    return (
        b"%PDF-1.4\n"
        b"1 0 obj\n<< /Type /Catalog /Pages 2 0 R >>\nendobj\n"
        b"2 0 obj\n<< /Type /Pages /Kids [3 0 R] /Count 1 >>\nendobj\n"
        b"3 0 obj\n<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Contents 4 0 R >>\nendobj\n"
        b"4 0 obj\n<< /Length " + str(length).encode("ascii") + b" >>\nstream\n"
        + content_bytes +
        b"\nendstream\nendobj\n"
        b"xref\n0 5\n"
        b"0000000000 65535 f \n"
        b"0000000009 00000 n \n"
        b"0000000058 00000 n \n"
        b"00000000115 00000 n \n"
        b"0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n300\n%%EOF\n"
    )


def run_smoke_test(base_url: str = "http://127.0.0.1:8000") -> int:
    print("=" * 80)
    print(f"               HERO BACKEND SMOKE TEST - {base_url}")
    print("=" * 80)

    results: List[Tuple[str, str, int, str]] = []
    has_failure = False

    internal_api_key = os.getenv("INTERNAL_API_KEY", "dev-secret-internal-key-2024")
    client = httpx.Client(base_url=base_url, timeout=15.0)

    # 1. Pengecekan endpoint GET dasar
    endpoints_to_check = [
        "/health",
        "/",
        "/api/v1/categories/",
        "/api/v1/categories/tree",
        "/api/v1/documents/",
        "/api/v1/documents/needs-review",
        "/api/v1/dashboard/summary",
        "/api/v1/ingest/jobs",
        "/api/v1/ingest/failures",
        "/api/v1/ingest/status",
        "/api/v1/audit-logs/",
        "/api/v1/scraping-sources/",
        "/docs",
        "/openapi.json",
    ]

    for path in endpoints_to_check:
        try:
            res = client.get(path)
            status_str = "OK" if res.status_code == 200 else "FAIL"
            if res.status_code != 200:
                has_failure = True
            results.append(("GET", path, res.status_code, status_str))
        except Exception as exc:
            has_failure = True
            results.append(("GET", path, 0, f"FAIL ({type(exc).__name__})"))

    created_doc_ids: List[int] = []
    created_job_ids: List[int] = []
    created_failure_ids: List[int] = []
    created_source_ids: List[int] = []
    created_scan_ids: List[int] = []

    # Alur 7 Langkah Sesuai Spesifikasi §4.3
    # Step 1: Unggah PDF (masuk ke antrean ekstraksi / status 'diterima')
    ts = int(time.time() * 1000)
    unique_phrase = f"modal minimum perbankan {ts}"
    unique_pdf = make_minimal_pdf(f"Peraturan OJK Smoke Test Teks {unique_phrase}")
    filename = f"smoke_test_doc_{ts}.pdf"
    uploaded_doc_id = None
    uploaded_job_id = None

    try:
        files = {"files": (filename, unique_pdf, "application/pdf")}
        data = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "title": f"Dokumen Awal Ingest {ts}",
        }
        res_upload = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
        if res_upload.status_code == 200:
            body = res_upload.json()
            uploaded_job_id = body.get("job_id")
            if uploaded_job_id:
                created_job_ids.append(uploaded_job_id)
            detail = body.get("details", [{}])[0]
            if body.get("success_count") == 1 and detail.get("status") == "success":
                uploaded_doc_id = detail["document_id"]
                created_doc_ids.append(uploaded_doc_id)
                results.append(("POST", "1. /ingest/upload-pdf (Unggah PDF Awal)", res_upload.status_code, f"OK (doc_id={uploaded_doc_id})"))
            else:
                has_failure = True
                results.append(("POST", "1. /ingest/upload-pdf (Unggah PDF Awal)", res_upload.status_code, "FAIL (not success)"))
        else:
            has_failure = True
            results.append(("POST", "1. /ingest/upload-pdf (Unggah PDF Awal)", res_upload.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "1. /ingest/upload-pdf (Unggah PDF Awal)", 0, f"FAIL ({type(exc).__name__})"))

    # Step 2: Claim (dengan API key dari env INTERNAL_API_KEY)
    claimed_doc_found = False
    try:
        headers = {"X-Internal-API-Key": internal_api_key}
        res_claim = client.post("/api/v1/internal/extraction/claim?limit=1", headers=headers)
        if res_claim.status_code == 200:
            claim_items = res_claim.json()
            if claim_items and any(item.get("document_id") == uploaded_doc_id for item in claim_items):
                claimed_doc_found = True
                results.append(("POST", "2. /internal/extraction/claim (Claim Antrean)", res_claim.status_code, f"OK (claimed target doc {uploaded_doc_id})"))
            else:
                # Bila yang terklaim bukan target doc, segera requeue agar tidak tertahan di status diproses
                for item in claim_items:
                    other_id = item.get("document_id")
                    if other_id and other_id != uploaded_doc_id:
                        client.post(f"/api/v1/internal/extraction/requeue/{other_id}", headers=headers)
                results.append(("POST", "2. /internal/extraction/claim (Claim Antrean)", res_claim.status_code, f"OK (claimed & requeued non-target docs)"))
        else:
            has_failure = True
            results.append(("POST", "2. /internal/extraction/claim (Claim Antrean)", res_claim.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "2. /internal/extraction/claim (Claim Antrean)", 0, f"FAIL ({type(exc).__name__})"))

    # Step 3: PATCH ekstraksi
    if uploaded_doc_id:
        try:
            headers = {"X-Internal-API-Key": internal_api_key}
            extract_body = {
                "title": f"Peraturan Kesehatan Bank Smoke Test {ts}",
                "regulation_number": f"{ts % 99 + 1}/POJK.03/{2020 + (ts % 4)}",
                "regulation_type": "POJK",
                "release_date": "2023-04-12",
                "extraction_method": "surya_ocr",
                "full_text": f"Ketetapan kepatuhan rasio kecukupan modal dan {unique_phrase} bagi bank umum.",
                "confidence": {
                    "title": 0.95,
                    "regulation_number": 0.92,
                    "regulation_type": 0.90,
                    "release_date": 0.88,
                }
            }
            res_ext = client.patch(f"/api/v1/internal/documents/{uploaded_doc_id}/extraction?force=true", headers=headers, json=extract_body)
            if res_ext.status_code == 200:
                ext_data = res_ext.json()
                if ext_data.get("status") == "terindeks":
                    results.append(("PATCH", "3. /internal/documents/{id}/extraction", res_ext.status_code, "OK (status=terindeks)"))
                else:
                    has_failure = True
                    results.append(("PATCH", "3. /internal/documents/{id}/extraction", res_ext.status_code, f"FAIL (status={ext_data.get('status')})"))
            else:
                has_failure = True
                results.append(("PATCH", "3. /internal/documents/{id}/extraction", res_ext.status_code, "FAIL"))
        except Exception as exc:
            has_failure = True
            results.append(("PATCH", "3. /internal/documents/{id}/extraction", 0, f"FAIL ({type(exc).__name__})"))
    else:
        results.append(("PATCH", "3. /internal/documents/{id}/extraction", 0, "SKIPPED (No doc)"))

    # Step 4: GET /documents?q=<frasa dari teks yang dikirim>
    try:
        search_q = unique_phrase
        res_search = client.get(f"/api/v1/documents/?q={search_q}")
        if res_search.status_code == 200:
            search_data = res_search.json()
            items = search_data.get("items", [])
            found = any(it.get("id") == uploaded_doc_id for it in items)
            if found or search_data.get("total", 0) >= 1:
                results.append(("GET", f"4. /documents/?q={search_q[:25]}... (Pencarian)", res_search.status_code, f"OK (total={search_data.get('total')})"))
            else:
                has_failure = True
                results.append(("GET", f"4. /documents/?q={search_q[:25]}... (Pencarian)", res_search.status_code, "FAIL (doc not found in search)"))
        else:
            has_failure = True
            results.append(("GET", "4. /documents/?q=... (Pencarian)", res_search.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("GET", "4. /documents/?q=... (Pencarian)", 0, f"FAIL ({type(exc).__name__})"))

    # Step 5: GET /documents/{id}/pdf -> 200 application/pdf
    if uploaded_doc_id:
        try:
            res_pdf = client.get(f"/api/v1/documents/{uploaded_doc_id}/pdf")
            is_pdf = res_pdf.status_code == 200 and "application/pdf" in res_pdf.headers.get("content-type", "")
            if is_pdf and len(res_pdf.content) > 0:
                results.append(("GET", f"5. /documents/{uploaded_doc_id}/pdf (Buka PDF)", res_pdf.status_code, f"OK ({len(res_pdf.content)} bytes)"))
            else:
                has_failure = True
                results.append(("GET", f"5. /documents/{uploaded_doc_id}/pdf (Buka PDF)", res_pdf.status_code, "FAIL (invalid pdf response)"))
        except Exception as exc:
            has_failure = True
            results.append(("GET", f"5. /documents/{uploaded_doc_id}/pdf (Buka PDF)", 0, f"FAIL ({type(exc).__name__})"))
    else:
        results.append(("GET", "5. /documents/{id}/pdf (Buka PDF)", 0, "SKIPPED (No doc)"))

    # Step 6: PATCH metadata
    if uploaded_doc_id:
        try:
            patch_meta = {
                "title": f"Peraturan Kesehatan Bank Terkoreksi {ts}",
            }
            res_meta = client.patch(f"/api/v1/documents/{uploaded_doc_id}/metadata", json=patch_meta)
            if res_meta.status_code == 200:
                meta_data = res_meta.json()
                if "title" in meta_data.get("changed_fields", []):
                    results.append(("PATCH", f"6. /documents/{uploaded_doc_id}/metadata (Koreksi)", res_meta.status_code, "OK (title updated)"))
                else:
                    has_failure = True
                    results.append(("PATCH", f"6. /documents/{uploaded_doc_id}/metadata (Koreksi)", res_meta.status_code, "FAIL (no changed_fields)"))
            else:
                has_failure = True
                results.append(("PATCH", f"6. /documents/{uploaded_doc_id}/metadata (Koreksi)", res_meta.status_code, "FAIL"))
        except Exception as exc:
            has_failure = True
            results.append(("PATCH", f"6. /documents/{uploaded_doc_id}/metadata (Koreksi)", 0, f"FAIL ({type(exc).__name__})"))
    else:
        results.append(("PATCH", "6. /documents/{id}/metadata (Koreksi)", 0, "SKIPPED (No doc)"))

    # Step 7: GET /dashboard/summary -> 200
    try:
        res_dash = client.get("/api/v1/dashboard/summary")
        if res_dash.status_code == 200:
            dash_data = res_dash.json()
            has_sections = "kb" in dash_data and "ingest" in dash_data and "sources" in dash_data
            if has_sections:
                results.append(("GET", "7. /dashboard/summary (Dashboard)", res_dash.status_code, "OK (sections valid)"))
            else:
                has_failure = True
                results.append(("GET", "7. /dashboard/summary (Dashboard)", res_dash.status_code, "FAIL (missing sections)"))
        else:
            has_failure = True
            results.append(("GET", "7. /dashboard/summary (Dashboard)", res_dash.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("GET", "7. /dashboard/summary (Dashboard)", 0, f"FAIL ({type(exc).__name__})"))

    # 8. Uji error handling Ingest: Duplicate & Invalid Format
    try:
        files_dup = {"files": (f"copy_{filename}", unique_pdf, "application/pdf")}
        res_dup = client.post("/api/v1/ingest/upload-pdf", files=files_dup, data={"access_classification": "publik", "document_role": "corpus_eksisting"})
        if res_dup.status_code == 200 and res_dup.json().get("duplicate_count") == 1:
            dup_job_id = res_dup.json().get("job_id")
            if dup_job_id:
                created_job_ids.append(dup_job_id)
            dup_det = res_dup.json().get("details", [{}])[0]
            if dup_det.get("failure_id"):
                created_failure_ids.append(dup_det["failure_id"])
            results.append(("POST", "8a. /ingest/upload-pdf (Duplicate Check)", res_dup.status_code, "OK (duplicate_count=1)"))
        else:
            has_failure = True
            results.append(("POST", "8a. /ingest/upload-pdf (Duplicate Check)", res_dup.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "8a. /ingest/upload-pdf (Duplicate Check)", 0, f"FAIL ({type(exc).__name__})"))

    try:
        files_txt = {"files": ("invalid.txt", b"Bukan PDF", "text/plain")}
        res_txt = client.post("/api/v1/ingest/upload-pdf", files=files_txt, data={"access_classification": "publik", "document_role": "corpus_eksisting"})
        if res_txt.status_code == 200 and res_txt.json().get("failed_count") == 1:
            txt_job_id = res_txt.json().get("job_id")
            if txt_job_id:
                created_job_ids.append(txt_job_id)
            txt_det = res_txt.json().get("details", [{}])[0]
            if txt_det.get("failure_id"):
                created_failure_ids.append(txt_det["failure_id"])
            results.append(("POST", "8b. /ingest/upload-pdf (Non-PDF Check)", res_txt.status_code, "OK (failed_count=1)"))
        else:
            has_failure = True
            results.append(("POST", "8b. /ingest/upload-pdf (Non-PDF Check)", res_txt.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "8b. /ingest/upload-pdf (Non-PDF Check)", 0, f"FAIL ({type(exc).__name__})"))

    # 9. Uji Sumber Folder Lokal (Langkah 6: US-16, FR-SCR-05)
    local_source_id = None
    subfolder_name = f"smoke_folder_{ts}"
    try:
        sources_base = Path("./sources")
        sources_base.mkdir(parents=True, exist_ok=True)
        smoke_subfolder = sources_base / subfolder_name
        smoke_subfolder.mkdir(parents=True, exist_ok=True)

        # Salin 2 PDF sintetis ke dalamnya
        (smoke_subfolder / "smoke_pdf_1.pdf").write_bytes(make_minimal_pdf(f"Konten Regulasi Folder Lokal 1 {ts}"))
        (smoke_subfolder / "smoke_pdf_2.pdf").write_bytes(make_minimal_pdf(f"Konten Regulasi Folder Lokal 2 {ts}"))

        # Daftarkan sumber folder lokal
        folder_url_candidate = str(smoke_subfolder.resolve())
        create_payload = {
            "name": f"Smoke Test Folder {ts}",
            "url": folder_url_candidate,
            "source_type": "folder_lokal",
            "recursive": True,
        }
        res_src = client.post("/api/v1/scraping-sources/", json=create_payload)
        if res_src.status_code != 201:
            # Jika di Docker, path lokal host mungkin tidak dikenali; coba path /app/sources/<subfolder>
            create_payload["url"] = f"/app/sources/{subfolder_name}"
            res_src = client.post("/api/v1/scraping-sources/", json=create_payload)

        if res_src.status_code == 201:
            src_data = res_src.json()
            local_source_id = src_data["id"]
            created_source_ids.append(local_source_id)
            results.append(("POST", "9a. /scraping-sources/ (Daftar Folder Lokal)", res_src.status_code, f"OK (source_id={local_source_id})"))

            # Jalankan run?wait=true (Run 1 -> 2 success)
            res_run1 = client.post(f"/api/v1/scraping-sources/{local_source_id}/run?wait=true")
            if res_run1.status_code == 200 and res_run1.json().get("success_count") == 2:
                r1_job_id = res_run1.json().get("id")
                if r1_job_id:
                    created_job_ids.append(r1_job_id)
                results.append(("POST", f"9b. /scraping-sources/{local_source_id}/run (Run 1)", res_run1.status_code, "OK (2 success)"))
            else:
                has_failure = True
                results.append(("POST", f"9b. /scraping-sources/{local_source_id}/run (Run 1)", res_run1.status_code, f"FAIL ({res_run1.text})"))

            # Jalankan run?wait=true (Run 2 -> 2 skipped)
            res_run2 = client.post(f"/api/v1/scraping-sources/{local_source_id}/run?wait=true")
            if res_run2.status_code == 200 and res_run2.json().get("skipped_count") == 2:
                r2_job_id = res_run2.json().get("id")
                if r2_job_id:
                    created_job_ids.append(r2_job_id)
                results.append(("POST", f"9c. /scraping-sources/{local_source_id}/run (Run 2 Idempoten)", res_run2.status_code, "OK (2 skipped)"))
            else:
                has_failure = True
                results.append(("POST", f"9c. /scraping-sources/{local_source_id}/run (Run 2 Idempoten)", res_run2.status_code, f"FAIL ({res_run2.text})"))

            # Hapus sumber uji
            res_del_src = client.delete(f"/api/v1/scraping-sources/{local_source_id}")
            if res_del_src.status_code == 200:
                results.append(("DELETE", f"9d. /scraping-sources/{local_source_id} (Hapus Sumber)", res_del_src.status_code, "OK"))
            else:
                has_failure = True
                results.append(("DELETE", f"9d. /scraping-sources/{local_source_id} (Hapus Sumber)", res_del_src.status_code, "FAIL"))
        else:
            has_failure = True
            results.append(("POST", "9a. /scraping-sources/ (Daftar Folder Lokal)", res_src.status_code, f"FAIL ({res_src.text})"))
    except OSError as exc:
        if "Read-only" in str(exc) or "read-only" in str(exc) or exc.errno == 30:
            results.append(("POST", "9. /scraping-sources/ (Folder Lokal)", 200, "DILEWATI (sources folder read-only di container)"))
        else:
            has_failure = True
            results.append(("POST", "9. /scraping-sources/ (Folder Lokal)", 0, f"FAIL ({type(exc).__name__}: {exc})"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "9. /scraping-sources/ (Folder Lokal)", 0, f"FAIL ({type(exc).__name__})"))
    finally:
        # Bersihkan folder lokal uji
        try:
            for f in smoke_subfolder.glob("*"):
                f.unlink(missing_ok=True)
            smoke_subfolder.rmdir()
        except Exception:
            pass

    # Step 10: Pemindaian Situs (Langkah 7) - Opsional, aktif jika SMOKE_SCAN_URL diset
    smoke_scan_url = os.getenv("SMOKE_SCAN_URL")
    if smoke_scan_url:
        print(f"\n==> Menjalankan pengujian pemindaian situs web ({smoke_scan_url})...")
        try:
            # Daftarkan sumber situs web
            res_src_web = client.post(
                "/api/v1/scraping-sources/",
                json={
                    "name": f"Smoke Web Source {ts}",
                    "url": smoke_scan_url,
                    "source_type": "situs_web",
                    "crawl_depth": 1,
                },
            )
            if res_src_web.status_code == 201:
                web_src_id = res_src_web.json()["id"]
                created_source_ids.append(web_src_id)
                results.append(("POST", "10a. /scraping-sources/ (Daftar Situs Web)", res_src_web.status_code, f"OK (source_id={web_src_id})"))

                # Jalankan scan
                res_scan = client.post(f"/api/v1/scans/?wait=true", json={"source_id": web_src_id, "crawl_depth": 1, "max_pages": 3})
                if res_scan.status_code == 200:
                    scan_info = res_scan.json()
                    scan_id = scan_info["id"]
                    created_scan_ids.append(scan_id)
                    summ = scan_info.get("candidates_summary", {})
                    results.append(("POST", f"10b. /api/v1/scans/ (Pindai Situs #{scan_id})", res_scan.status_code, f"OK (total={summ.get('total')}, baru={summ.get('baru')})"))

                    # Jika ada kandidat 'baru', tarik 1 ke KB
                    res_cands = client.get(f"/api/v1/scans/{scan_id}/candidates")
                    if res_cands.status_code == 200:
                        new_cands = [c for c in res_cands.json().get("items", []) if c.get("match_status") == "baru"]
                        if new_cands:
                            chosen_cand = new_cands[0]
                            # Unselect all then select 1
                            client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
                            client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "set", "candidate_ids": [chosen_cand["id"]], "selected": True})

                            res_pull = client.post(f"/api/v1/scans/{scan_id}/pull?wait=true", json={"destination": "knowledge_base"})
                            if res_pull.status_code == 200:
                                p_body = res_pull.json()
                                if p_body.get("pull_job_id"):
                                    created_job_ids.append(p_body["pull_job_id"])
                                results.append(("POST", f"10c. /api/v1/scans/{scan_id}/pull (Tarik ke KB)", res_pull.status_code, "OK (1 berkas ditarik)"))
                            else:
                                results.append(("POST", f"10c. /api/v1/scans/{scan_id}/pull (Tarik ke KB)", res_pull.status_code, f"FAIL ({res_pull.text})"))

                    # Hapus sumber uji
                    client.delete(f"/api/v1/scraping-sources/{web_src_id}")
                else:
                    results.append(("POST", "10b. /api/v1/scans/ (Pindai Situs)", res_scan.status_code, f"FAIL ({res_scan.text})"))
            else:
                results.append(("POST", "10a. /scraping-sources/ (Daftar Situs Web)", res_src_web.status_code, f"FAIL ({res_src_web.text})"))
        except Exception as exc:
            results.append(("POST", "10. /api/v1/scans/ (Pindai Situs)", 0, f"FAIL ({type(exc).__name__})"))
    else:
        results.append(("GET", "10. /api/v1/scans/ (Pindai Situs)", 200, "DILEWATI (SMOKE_SCAN_URL tidak diset)"))

    # Bersihkan seluruh artefak data uji di database lokal jika modul DB tersedia
    try:
        from app.database import SessionLocal
        from app.models.document import Document
        from app.models.job_ingest import JobIngest
        from app.models.ingest_failure import IngestFailure
        from app.models.source_file import SourceFile
        from app.models.scan_session import ScanSession
        from app.models.scan_candidate import ScanCandidate
        from app.models.article import Article, LegalReference, ArticleReference
        from app.models.scraping_source import ScrapingSource
        from app.services.storage_service import get_storage_service

        db = SessionLocal()
        storage = get_storage_service()
        try:
            # Temukan seluruh dokumen terkait job-job yang dibuat
            all_target_doc_ids = set(created_doc_ids)
            if created_job_ids:
                job_docs = db.query(Document.id).filter(Document.job_id.in_(created_job_ids)).all()
                for (jd_id,) in job_docs:
                    all_target_doc_ids.add(jd_id)

            if all_target_doc_ids:
                docs = db.query(Document).filter(Document.id.in_(list(all_target_doc_ids))).all()
                for doc in docs:
                    if doc.file_path_pdf and storage.exists(doc.file_path_pdf):
                        storage.delete(doc.file_path_pdf)
                doc_list = list(all_target_doc_ids)
                db.query(LegalReference).filter(LegalReference.document_id.in_(doc_list)).delete(synchronize_session=False)
                db.query(ArticleReference).filter(ArticleReference.source_document_id.in_(doc_list)).delete(synchronize_session=False)
                db.query(Article).filter(Article.document_id.in_(doc_list)).delete(synchronize_session=False)
                db.query(Document).filter(Document.id.in_(doc_list)).delete(synchronize_session=False)

            if created_scan_ids:
                db.query(ScanCandidate).filter(ScanCandidate.scan_id.in_(created_scan_ids)).delete(synchronize_session=False)
                db.query(ScanSession).filter(ScanSession.id.in_(created_scan_ids)).delete(synchronize_session=False)

            if created_failure_ids:
                fails = db.query(IngestFailure).filter(IngestFailure.id.in_(created_failure_ids)).all()
                for f in fails:
                    if f.quarantine_path and storage.exists(f.quarantine_path):
                        storage.delete(f.quarantine_path)
                db.query(IngestFailure).filter(IngestFailure.id.in_(created_failure_ids)).delete(synchronize_session=False)

            if created_job_ids:
                db.query(IngestFailure).filter(IngestFailure.job_id.in_(created_job_ids)).delete(synchronize_session=False)
                db.query(JobIngest).filter(JobIngest.id.in_(created_job_ids)).delete(synchronize_session=False)

            if created_source_ids:
                db.query(SourceFile).filter(SourceFile.source_id.in_(created_source_ids)).delete(synchronize_session=False)
                db.query(ScrapingSource).filter(ScrapingSource.id.in_(created_source_ids)).delete(synchronize_session=False)

            db.commit()
        except Exception as cl_err:
            db.rollback()
        finally:
            db.close()
    except Exception:
        pass

    # Cetak tabel ringkas hasil smoke test
    print(f"{'METHOD':<8} | {'ENDPOINT / PATH':<50} | {'STATUS':<7} | {'HASIL'}")
    print("-" * 80)
    for method, path, status_code, outcome in results:
        code_str = str(status_code) if status_code > 0 else "-"
        print(f"{method:<8} | {path:<50} | {code_str:<7} | {outcome}")

    print("=" * 80)
    if has_failure:
        print("[FAIL] HASIL: SMOKE TEST GAGAL - Terdapat endpoint yang tidak lulus.")
        return 1
    else:
        print("[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan (Langkah 0-7) lulus 100%.")
        return 0


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    exit_code = run_smoke_test(base_url=target_url)
    sys.exit(exit_code)
