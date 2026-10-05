#!/usr/bin/env python3
"""
scripts/demo_seed.py
Skrip otomatis untuk mendaftarkan sumber, memindai, dan menarik data demo
melalui HTTP API resmi HERO Backend (bukan akses langsung ke database).

Penggunaan:
    python scripts/demo_seed.py --config deploy/demo_sources.example.json --base-url http://127.0.0.1:8000
"""
import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path


def http_request(base_url: str, method: str, path: str, data: dict = None, headers: dict = None) -> dict:
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    headers = headers or {}
    headers.setdefault("Content-Type", "application/json")
    headers.setdefault("Accept", "application/json")

    encoded_data = None
    if data is not None and method in ("POST", "PUT", "PATCH"):
        encoded_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=encoded_data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            content_type = resp.headers.get("Content-Type", "")
            resp_body = resp.read().decode("utf-8")
            if "application/json" in content_type:
                return json.loads(resp_body)
            return {"raw": resp_body, "status_code": resp.status}
    except urllib.error.HTTPError as he:
        body = he.read().decode("utf-8")
        try:
            err_json = json.loads(body)
            detail = err_json.get("detail", body)
        except Exception:
            detail = body
        print(f"  [HTTP {he.code}] Error pada {method} {url}: {detail}")
        return {"error": True, "status_code": he.code, "detail": detail}
    except Exception as exc:
        print(f"  [REQ ERROR] Gagal menghubungi {url}: {exc}")
        return {"error": True, "detail": str(exc)}


def main():
    parser = argparse.ArgumentParser(description="Seed data demo HERO Backend melalui REST API.")
    parser.add_argument(
        "--config",
        default="deploy/demo_sources.example.json",
        help="Path ke berkas JSON konfigurasi sumber demo.",
    )
    parser.add_argument(
        "--base-url",
        default="http://127.0.0.1:8000",
        help="Base URL API HERO Backend (misal: http://127.0.0.1:8000 atau https://api.hero.example.com).",
    )
    parser.add_argument(
        "--api-key",
        default="",
        help="Internal API Key jika diperlukan.",
    )
    args = parser.parse_args()

    config_path = Path(args.config)
    if not config_path.exists():
        print(f"[ERROR] Berkas konfigurasi '{config_path}' tidak ditemukan!")
        sys.exit(1)

    with open(config_path, "r", encoding="utf-8") as f:
        config_data = json.load(f)

    sources = config_data.get("sources", [])
    if not sources:
        print("[WARN] Tidak ada daftar sumber dalam konfigurasi.")
        sys.exit(0)

    print("=================================================================")
    print("HERO BACKEND - DEMO SEEDING UTILITY")
    print(f"Base API URL   : {args.base_url}")
    print(f"Sumber Config  : {args.config} ({len(sources)} sumber terdaftar)")
    print("=================================================================\n")

    # 1. Cek kesehatan API
    print("--> Memeriksa status kesehatan server...")
    health = http_request(args.base_url, "GET", "/health")
    if health.get("error") or health.get("database") != "ok":
        print(f"[ABORT] Server API tidak sehat atau database belum siap: {health}")
        sys.exit(1)
    print(f"    Server aktif (Versi: {health.get('version', 'N/A')}, Status: {health.get('status')})\n")

    # 2. Ambil daftar sumber eksisting untuk idempoten
    existing_resp = http_request(args.base_url, "GET", "/api/v1/scraping-sources/")
    existing_items = existing_resp.get("items", []) if isinstance(existing_resp, dict) else []
    existing_urls = {s.get("url"): s for s in existing_items}

    summary_results = []

    # 3. Proses pendaftaran dan eksekusi masing-masing sumber
    for idx, src_conf in enumerate(sources, 1):
        name = src_conf.get("name")
        stype = src_conf.get("source_type")
        url = src_conf.get("url")
        max_pull = src_conf.get("max_pull", 5)

        print(f"[{idx}/{len(sources)}] Memproses Sumber: '{name}' ({stype})")

        # Registrasi sumber jika belum ada (idempoten)
        source_id = None
        if url in existing_urls:
            source_id = existing_urls[url]["id"]
            print(f"    Sumber sudah terdaftar sebelumnya (ID: {source_id}).")
        else:
            payload = {
                "name": name,
                "source_type": stype,
                "url": url,
                "crawl_depth": src_conf.get("crawl_depth", 2),
                "max_pages": src_conf.get("max_pages", 20),
                "default_access_classification": src_conf.get("default_access_classification", "publik"),
                "default_document_role": src_conf.get("default_document_role", "corpus_eksisting"),
            }
            create_resp = http_request(args.base_url, "POST", "/api/v1/scraping-sources/", payload)
            if create_resp.get("error"):
                print(f"    [SKIP] Gagal mendaftarkan sumber: {create_resp.get('detail')}")
                summary_results.append({"name": name, "type": stype, "found": 0, "pulled": 0, "status": "gagal_daftar"})
                continue
            source_id = create_resp.get("id")
            print(f"    Sumber baru berhasil didaftarkan (ID: {source_id}).")

        # Eksekusi sumber
        if stype == "folder_lokal":
            print(f"    Menjalankan sinkronisasi folder lokal (wait=true)...")
            run_resp = http_request(args.base_url, "POST", f"/api/v1/scraping-sources/{source_id}/run?wait=true")
            if run_resp.get("error"):
                print(f"    [WARN] Eksekusi folder lokal gagal: {run_resp.get('detail')}")
                summary_results.append({"name": name, "type": stype, "found": 0, "pulled": 0, "status": "gagal"})
            else:
                processed = run_resp.get("processed_count", 0)
                success = run_resp.get("success_count", 0)
                print(f"    Sinkronisasi selesai. Diproses: {processed}, Sukses: {success}")
                summary_results.append({"name": name, "type": stype, "found": processed, "pulled": success, "status": "sukses"})

        elif stype == "situs_web":
            print(f"    Menjalankan pemindaian situs (POST /api/v1/scans?wait=true)...")
            scan_payload = {
                "source_id": source_id,
                "max_depth": src_conf.get("crawl_depth", 2),
                "max_pages": src_conf.get("max_pages", 15),
            }
            scan_resp = http_request(args.base_url, "POST", "/api/v1/scans?wait=true", scan_payload)
            if scan_resp.get("error"):
                print(f"    [WARN] Pemindaian gagal: {scan_resp.get('detail')}")
                summary_results.append({"name": name, "type": stype, "found": 0, "pulled": 0, "status": "gagal_scan"})
                continue

            scan_id = scan_resp.get("id")
            found_count = scan_resp.get("found_candidates_count", 0)
            new_count = scan_resp.get("new_candidates_count", 0)
            print(f"    Pemindaian selesai (Scan ID: {scan_id}). Ditemukan: {found_count}, Baru: {new_count}")

            # Ambil kandidat dengan status 'baru'
            candidates_resp = http_request(args.base_url, "GET", f"/api/v1/scans/{scan_id}/candidates?match_status=baru&limit={max_pull}")
            candidates = candidates_resp.get("items", [])
            candidate_ids = [c["id"] for c in candidates if "id" in c]

            if candidate_ids:
                print(f"    Menarik {len(candidate_ids)} kandidat ke Knowledge Base (wait=true)...")
                pull_payload = {
                    "candidate_ids": candidate_ids,
                    "destination": "knowledge_base",
                    "access_classification": src_conf.get("default_access_classification", "publik"),
                    "document_role": src_conf.get("default_document_role", "corpus_eksisting"),
                }
                pull_resp = http_request(args.base_url, "POST", f"/api/v1/scans/{scan_id}/pull?wait=true", pull_payload)
                pull_stat = pull_resp.get("pull_progress", {})
                pulled_cnt = pull_stat.get("success_count", 0)
                print(f"    Penarikan selesai. Berhasil ditarik: {pulled_cnt}")
                summary_results.append({"name": name, "type": stype, "found": found_count, "pulled": pulled_cnt, "status": "sukses"})
            else:
                print(f"    Tidak ada kandidat berstatus 'baru' untuk ditarik.")
                summary_results.append({"name": name, "type": stype, "found": found_count, "pulled": 0, "status": "tidak_ada_kandidat_baru"})

    # 4. Cetak Tabel Ringkasan
    print("\n=================================================================")
    print("RINGKASAN HASIL SEEDING DATA DEMO")
    print("=================================================================")
    print(f"{'Nama Sumber':<35} | {'Tipe':<12} | {'Ditemukan':<10} | {'Ditarik':<8} | {'Status':<10}")
    print("-" * 85)
    for r in summary_results:
        print(f"{r['name'][:35]:<35} | {r['type']:<12} | {r['found']:<10} | {r['pulled']:<8} | {r['status']:<10}")
    print("=" * 85)

    # 5. Tampilkan cuplikan dashboard summary
    print("\n--> Mengambil ringkasan Dashboard...")
    dash = http_request(args.base_url, "GET", "/api/v1/dashboard/summary")
    if not dash.get("error"):
        print(f"  - Total Dokumen Corpus  : {dash.get('corpus_documents', 0)}")
        print(f"  - Dokumen Perlu Koreksi : {dash.get('needs_review_count', 0)}")
        print(f"  - Total Kegagalan       : {dash.get('failed_ingest_count', 0)}")
        print(f"  - Target 20 Dokumen     : {'TERCAPAI (Hijau)' if dash.get('target_met') else 'BELUM TERCAPAI'}")
    print("\nSeeding demo selesai.")


if __name__ == "__main__":
    main()
