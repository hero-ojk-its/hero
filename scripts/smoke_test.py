"""
scripts/smoke_test.py
Smoke test otomatis untuk memvalidasi ketersediaan dan fungsionalitas server HERO Backend yang sedang berjalan.

Penggunaan:
    python scripts/smoke_test.py [BASE_URL]
    Contoh: python scripts/smoke_test.py http://127.0.0.1:8000
"""
import io
import sys
import time
from typing import List, Tuple
import httpx

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
        b"0000000115 00000 n \n"
        b"0000000206 00000 n \n"
        b"trailer\n<< /Size 5 /Root 1 0 R >>\n"
        b"startxref\n300\n%%EOF\n"
    )


def run_smoke_test(base_url: str = "http://127.0.0.1:8000") -> int:
    print(f"================================================================================")
    print(f"               HERO BACKEND SMOKE TEST - {base_url}")
    print(f"================================================================================")

    results: List[Tuple[str, str, int, str]] = []
    has_failure = False

    client = httpx.Client(base_url=base_url, timeout=15.0)

    # 1. Pengecekan endpoint GET dasar
    endpoints_to_check = [
        "/health",
        "/",
        "/api/v1/categories/",
        "/api/v1/documents/",
        "/api/v1/ingest/jobs",
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

    # 2. Uji alur upload dokumen PDF baru (Timestamp unik)
    uploaded_doc_id = None
    ts = int(time.time() * 1000)
    unique_pdf = make_minimal_pdf(f"Peraturan OJK Smoke Test Timestamp {ts}")
    filename = f"smoke_test_{ts}.pdf"

    # 2a. Upload baru -> Harap success
    try:
        files = {"files": (filename, unique_pdf, "application/pdf")}
        data = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
            "title": f"Regulasi Smoke Test {ts}",
            "regulation_number": f"POJK-SMOKE-{ts}",
        }
        res_upload = client.post("/api/v1/ingest/upload-pdf", files=files, data=data)
        if res_upload.status_code == 200:
            body = res_upload.json()
            if body.get("success_count") == 1 and body.get("details", [{}])[0].get("status") == "success":
                uploaded_doc_id = body["details"][0]["document_id"]
                results.append(("POST", "/api/v1/ingest/upload-pdf (New PDF)", res_upload.status_code, "OK (success_count=1)"))
            else:
                has_failure = True
                results.append(("POST", "/api/v1/ingest/upload-pdf (New PDF)", res_upload.status_code, "FAIL (not success)"))
        else:
            has_failure = True
            results.append(("POST", "/api/v1/ingest/upload-pdf (New PDF)", res_upload.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "/api/v1/ingest/upload-pdf (New PDF)", 0, f"FAIL ({type(exc).__name__})"))

    # 2b. Upload ulang file yang sama -> Harap duplicate
    try:
        files_dup = {"files": (f"copy_{filename}", unique_pdf, "application/pdf")}
        data_dup = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
        }
        res_dup = client.post("/api/v1/ingest/upload-pdf", files=files_dup, data=data_dup)
        if res_dup.status_code == 200:
            body_dup = res_dup.json()
            if body_dup.get("duplicate_count") == 1 and body_dup.get("details", [{}])[0].get("status") == "duplicate":
                results.append(("POST", "/api/v1/ingest/upload-pdf (Duplicate PDF)", res_dup.status_code, "OK (duplicate_count=1)"))
            else:
                has_failure = True
                results.append(("POST", "/api/v1/ingest/upload-pdf (Duplicate PDF)", res_dup.status_code, "FAIL (not duplicate)"))
        else:
            has_failure = True
            results.append(("POST", "/api/v1/ingest/upload-pdf (Duplicate PDF)", res_dup.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "/api/v1/ingest/upload-pdf (Duplicate PDF)", 0, f"FAIL ({type(exc).__name__})"))

    # 2c. Upload file .txt -> Harap failed
    try:
        files_txt = {"files": ("invalid.txt", b"Bukan PDF", "text/plain")}
        data_txt = {
            "access_classification": "publik",
            "document_role": "corpus_eksisting",
        }
        res_txt = client.post("/api/v1/ingest/upload-pdf", files=files_txt, data=data_txt)
        if res_txt.status_code == 200:
            body_txt = res_txt.json()
            if body_txt.get("failed_count") == 1 and body_txt.get("details", [{}])[0].get("status") == "failed":
                results.append(("POST", "/api/v1/ingest/upload-pdf (Non-PDF)", res_txt.status_code, "OK (failed_count=1)"))
            else:
                has_failure = True
                results.append(("POST", "/api/v1/ingest/upload-pdf (Non-PDF)", res_txt.status_code, "FAIL (not failed)"))
        else:
            has_failure = True
            results.append(("POST", "/api/v1/ingest/upload-pdf (Non-PDF)", res_txt.status_code, "FAIL"))
    except Exception as exc:
        has_failure = True
        results.append(("POST", "/api/v1/ingest/upload-pdf (Non-PDF)", 0, f"FAIL ({type(exc).__name__})"))

    # 3. GET /api/v1/documents/{id} untuk dokumen yang baru diunggah
    if uploaded_doc_id:
        try:
            res_doc = client.get(f"/api/v1/documents/{uploaded_doc_id}")
            status_str = "OK" if res_doc.status_code == 200 else "FAIL"
            if res_doc.status_code != 200:
                has_failure = True
            results.append(("GET", f"/api/v1/documents/{uploaded_doc_id}", res_doc.status_code, status_str))
        except Exception as exc:
            has_failure = True
            results.append(("GET", f"/api/v1/documents/{uploaded_doc_id}", 0, f"FAIL ({type(exc).__name__})"))
    else:
        results.append(("GET", "/api/v1/documents/{id}", 0, "SKIPPED (No uploaded doc)"))

    # 4. Cetak tabel ringkas hasil smoke test
    print(f"{'METHOD':<8} | {'ENDPOINT / PATH':<48} | {'STATUS':<7} | {'HASIL'}")
    print("-" * 80)
    for method, path, status_code, outcome in results:
        code_str = str(status_code) if status_code > 0 else "-"
        print(f"{method:<8} | {path:<48} | {code_str:<7} | {outcome}")

    print("=" * 80)
    if has_failure:
        print("[FAIL] HASIL: SMOKE TEST GAGAL - Terdapat endpoint yang tidak lulus.")
        return 1
    else:
        print("[OK] HASIL: SMOKE TEST SUKSES - Seluruh pemeriksaan lulus 100%.")
        return 0


if __name__ == "__main__":
    target_url = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8000"
    exit_code = run_smoke_test(base_url=target_url)
    sys.exit(exit_code)
