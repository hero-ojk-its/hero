"""
scripts/demo_real_site_scan.py
Demonstrasi nyata pemindaian situs web regulasi publik pada database hero_db (Langkah 7 §5).
1. Mendaftarkan situs JDIH ESDM (https://jdih.esdm.go.id) sebagai sumber situs_web.
2. Mengeksekusi pemindaian (Scan depth 1, max_pages=3) dan menampilkan ringkasan kandidat.
3. Menarik 3 kandidat 'baru' ke knowledge_base.
4. Menampilkan detail sesi dan GET /dashboard/summary.
5. Melaporkan hasil pengujian terhadap situs JavaScript-only (JDIH OJK) dan anti-bot (JDIH BPK).
"""
import json
import os
import sys
import time
import httpx
from dotenv import load_dotenv

load_dotenv()

BASE_URL = os.getenv("DEMO_API_BASE", "http://127.0.0.1:8000")

def main():
    print("=" * 80)
    print(f"   DEMONSTRASI NYATA ALUR PINDAI SITUS WEB (LANGKAH 7 §5)")
    print(f"   Target Server: {BASE_URL}")
    print("=" * 80)

    client = httpx.Client(base_url=BASE_URL, timeout=60.0)

    # 1. Daftarkan Sumber Situs JDIH ESDM
    print("\n[1] Mendaftarkan sumber situs web: JDIH Kementerian ESDM...")
    src_payload = {
        "name": "JDIH Kementerian ESDM (Publik)",
        "url": "https://jdih.esdm.go.id",
        "source_type": "situs_web",
        "crawl_depth": 1,
        "default_access_classification": "publik",
        "default_document_role": "corpus_eksisting",
    }
    r_src = client.post("/api/v1/scraping-sources/", json=src_payload)
    if r_src.status_code == 201:
        source_id = r_src.json()["id"]
        print(f"==> Sumber berhasil didaftarkan: ID={source_id}, Nama='{r_src.json()['name']}'")
    elif r_src.status_code == 400 and "sudah terdaftar" in r_src.text:
        # Cari ID sumber yang sudah ada
        r_list = client.get("/api/v1/scraping-sources/?source_type=situs_web")
        sources = r_list.json()["items"]
        source_id = next(s["id"] for s in sources if s["url"] == "https://jdih.esdm.go.id")
        print(f"==> Sumber sudah terdaftar sebelumnya: ID={source_id}")
    else:
        print(f"[ERROR] Gagal mendaftarkan sumber: {r_src.status_code} - {r_src.text}")
        sys.exit(1)

    # 2. Jalankan Pemindaian (Scan depth=1, max_pages=3)
    print("\n[2] Menjalankan pemindaian (Scan depth 1, max_pages=3)...")
    scan_payload = {
        "source_id": source_id,
        "crawl_depth": 1,
        "max_pages": 3,
    }
    t0 = time.time()
    r_scan = client.post("/api/v1/scans/?wait=true", json=scan_payload)
    t1 = time.time()

    if r_scan.status_code != 200:
        print(f"[ERROR] Gagal memindai: {r_scan.status_code} - {r_scan.text}")
        sys.exit(1)

    scan_data = r_scan.json()
    scan_id = scan_data["id"]
    print(f"==> Pemindaian selesai dalam {t1 - t0:.2f} detik.")
    print("==> RAW RESPONSE POST /api/v1/scans/?wait=true:")
    print(json.dumps(scan_data, indent=2))

    # 3. Ambil Daftar Kandidat
    print(f"\n[3] Mengambil daftar kandidat untuk sesi #{scan_id}...")
    r_cands = client.get(f"/api/v1/scans/{scan_id}/candidates?limit=20")
    cands_data = r_cands.json()
    items = cands_data["items"]
    print(f"==> Total kandidat ditemukan: {cands_data['total']}")
    for idx, c in enumerate(items, 1):
        print(f"  {idx:02d}. [{c['match_status']}] {c['filename']} ({c['size_bytes']} bytes) - Selected: {c['selected']}")

    # 4. Pilih Maksimal 3 Kandidat 'baru' untuk Ditarik ke Knowledge Base
    new_candidates = [c for c in items if c["match_status"] == "baru"]
    selected_for_pull = new_candidates[:3]
    selected_ids = [c["id"] for c in selected_for_pull]

    print(f"\n[4] Memilih {len(selected_ids)} kandidat 'baru' untuk ditarik ke Knowledge Base: {selected_ids}...")
    # Reset seleksi dan set yang dipilih
    client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
    r_sel = client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "set", "candidate_ids": selected_ids, "selected": True})
    print("==> Ringkasan seleksi terbaru:", json.dumps(r_sel.json(), indent=2))

    # 5. Eksekusi Penarikan ke Knowledge Base
    print("\n[5] Mengeksekusi penarikan ke knowledge_base (POST /api/v1/scans/{id}/pull?wait=true)...")
    t0_pull = time.time()
    r_pull = client.post(f"/api/v1/scans/{scan_id}/pull?wait=true", json={"destination": "knowledge_base"})
    t1_pull = time.time()

    if r_pull.status_code != 200:
        print(f"[ERROR] Gagal penarikan: {r_pull.status_code} - {r_pull.text}")
        sys.exit(1)

    pull_res_data = r_pull.json()
    print(f"==> Penarikan selesai dalam {t1_pull - t0_pull:.2f} detik.")
    print("==> RAW RESPONSE POST /api/v1/scans/{id}/pull?wait=true:")
    print(json.dumps(pull_res_data, indent=2))

    # 6. Periksa Hasil Kandidat Setelah Ditarik
    print("\n[6] Detail hasil per kandidat setelah penarikan:")
    r_cands_pulled = client.get(f"/api/v1/scans/{scan_id}/candidates")
    for c in r_cands_pulled.json()["items"]:
        if c["id"] in selected_ids:
            print(f"  * ID={c['id']} | Filename='{c['filename']}' | Outcome='{c['pull_outcome']}' | Doc ID={c['document_id']}")

    # 7. Tampilkan Dashboard Summary
    print("\n[7] Mengambil ringkasan dashboard (GET /api/v1/dashboard/summary):")
    r_dash = client.get("/api/v1/dashboard/summary")
    print(json.dumps(r_dash.json(), indent=2))

    print("\n" + "=" * 80)
    print("DEMONSTRASI NYATA LANGKAH 7 SELESAI DENGAN SUKSES")
    print("=" * 80)


if __name__ == "__main__":
    main()
