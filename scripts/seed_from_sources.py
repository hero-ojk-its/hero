#!/usr/bin/env python3
"""
scripts/seed_from_sources.py
Skrip otomatisasi untuk mengisi basis pengetahuan (Knowledge Base) HERO Backend
dengan data regulasi nyata dan bervariasi dari 3 sumber data resmi:
1. Regulasi OJK (SharePoint ASP.NET)
2. JDIH OJK (DataTables JSON API)
3. OneDrive Public DPEA (SharePoint Shared Folder)

Seluruh interaksi dilakukan murni melalui REST API resmi HERO Backend
(bukan melalui manipulasi langsung ke database).

Penggunaan:
    python scripts/seed_from_sources.py --per-source 15 --sources ojk,jdih,onedrive --naming-format nama,jenis,tahun --reset
"""
import argparse
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

REPO_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_ROOT))

try:
    sys.stdout.reconfigure(line_buffering=True)
    sys.stderr.reconfigure(line_buffering=True)
except Exception:
    pass

# Konfigurasi sumber default
DEFAULT_SOURCES_SPEC = {
    "ojk": {
        "name": "Regulasi OJK (Situs Resmi)",
        "source_type": "situs_web",
        "url": "https://ojk.go.id/id/regulasi/default.aspx",
        "crawl_depth": 1,
        "max_pages": 3,
        "is_jdih": False,
    },
    "jdih": {
        "name": "JDIH OJK (Situs Resmi)",
        "source_type": "situs_web",
        "url": "https://jdih.ojk.go.id/",
        "crawl_depth": 1,
        "max_pages": 2,
        "is_jdih": True,
    },
    "onedrive": {
        "name": "OneDrive Public DPEA",
        "source_type": "onedrive_public",
        "url": os.getenv(
            "SCAN_ONEDRIVE_URL",
            "https://oneojk-my.sharepoint.com/:f:/g/personal/faris_budi_ojk_go_id/IgC2eHe7uRwqT5X1zPBi_d1AAfA8Ec-W6i3BTN66ZgJI1rA?e=0yRyoP",
        ),
        "crawl_depth": 2,
        "max_pages": 3,
        "is_jdih": False,
    },
}


def http_request(
    base_url: str,
    method: str,
    path: str,
    data: Optional[Dict[str, Any]] = None,
    headers: Optional[Dict[str, str]] = None,
    timeout: int = 180,
) -> Tuple[int, Any]:
    """Helper untuk memanggil REST API menggunakan urllib bawaan."""
    url = f"{base_url.rstrip('/')}/{path.lstrip('/')}"
    req_headers = headers or {}
    req_headers.setdefault("Content-Type", "application/json")
    req_headers.setdefault("Accept", "application/json")

    encoded_data = None
    if data is not None and method in ("POST", "PUT", "PATCH"):
        encoded_data = json.dumps(data).encode("utf-8")

    req = urllib.request.Request(url, data=encoded_data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8")
            content_type = resp.headers.get("Content-Type", "")
            if "application/json" in content_type:
                return resp.status, json.loads(body)
            return resp.status, body
    except urllib.error.HTTPError as he:
        if he.code in (301, 302, 307, 308) and "Location" in he.headers:
            redir_url = he.headers["Location"]
            try:
                req_redir = urllib.request.Request(redir_url, data=encoded_data, headers=req_headers, method=method)
                with urllib.request.urlopen(req_redir, timeout=timeout) as resp2:
                    body2 = resp2.read().decode("utf-8")
                    content_type2 = resp2.headers.get("Content-Type", "")
                    if "application/json" in content_type2:
                        return resp2.status, json.loads(body2)
                    return resp2.status, body2
            except urllib.error.HTTPError as he2:
                err_body2 = he2.read().decode("utf-8")
                try:
                    return he2.code, json.loads(err_body2)
                except Exception:
                    return he2.code, {"detail": err_body2}
            except Exception as e2:
                return 0, {"detail": str(e2)}

        err_body = he.read().decode("utf-8")
        try:
            parsed_err = json.loads(err_body)
        except Exception:
            parsed_err = {"detail": err_body}
        return he.code, parsed_err
    except Exception as exc:
        return 0, {"detail": str(exc)}


def run_reset(repo_root: Path) -> None:
    """Mengeksekusi scripts/demo_reset.py --yes untuk mengosongkan database operasional."""
    print("\n[RESET] Memulai pengosongan data operasional via scripts/demo_reset.py...")
    reset_script = repo_root / "scripts" / "demo_reset.py"
    if not reset_script.exists():
        print(f"[RESET ERROR] Skrip reset '{reset_script}' tidak ditemukan!")
        sys.exit(1)

    cmd = [sys.executable, str(reset_script), "--yes"]
    res = subprocess.run(cmd, capture_output=True, text=True)
    if res.returncode != 0:
        print(f"[RESET ERROR] Gagal mereset database:\n{res.stderr}\n{res.stdout}")
        sys.exit(1)

    print(res.stdout.strip())
    print("[RESET KONFIRMASI] Operasional database dan berkas staging fisik telah dikosongkan secara bersih.\n")


def select_diverse_candidates(candidates: List[dict], n: int, is_jdih: bool = False) -> List[dict]:
    """
    Memilih n kandidat beragam berdasarkan doc_kind == 'utama', bidang, jenis regulasi,
    tahun penetapan, dan status keberlakuan (khusus JDIH).
    """
    cands = [c for c in candidates if c.get("doc_kind") == "utama"]
    baru_cands = [c for c in cands if c.get("match_status") == "baru"]
    pool = baru_cands if baru_cands else cands

    if not pool:
        return []
    if len(pool) <= n:
        return pool

    selected: List[dict] = []
    seen_ids = set()

    # Khusus JDIH: jamin perwakilan status non-berlaku (dicabut, diubah)
    if is_jdih:
        by_status: Dict[str, List[dict]] = {}
        for c in pool:
            st = c.get("status_keberlakuan") or "tidak_diketahui"
            by_status.setdefault(st, []).append(c)

        for st in ("dicabut", "diubah"):
            if st in by_status and by_status[st]:
                for c in by_status[st][:2]:
                    if c["id"] not in seen_ids and len(selected) < n:
                        selected.append(c)
                        seen_ids.add(c["id"])

    # Kelompokkan kandidat berdasarkan kombinasi metadata (bidang, jenis, tahun)
    buckets: Dict[Tuple[str, str, str], List[dict]] = {}
    for c in pool:
        if c["id"] in seen_ids:
            continue
        key = (
            str(c.get("bidang") or "Umum"),
            str(c.get("regulation_type") or "Lainnya"),
            str(c.get("release_year") or "N/A"),
        )
        buckets.setdefault(key, []).append(c)

    bucket_keys = list(buckets.keys())
    while len(selected) < n and bucket_keys:
        empty_keys = []
        for k in bucket_keys:
            if buckets[k]:
                cand = buckets[k].pop(0)
                if cand["id"] not in seen_ids:
                    selected.append(cand)
                    seen_ids.add(cand["id"])
                    if len(selected) >= n:
                        break
            if not buckets[k]:
                empty_keys.append(k)
        for ek in empty_keys:
            bucket_keys.remove(ek)

    # Jika kuota n belum terpenuhi, ambil dari sisa pool
    if len(selected) < n:
        for c in pool:
            if c["id"] not in seen_ids:
                selected.append(c)
                seen_ids.add(c["id"])
                if len(selected) >= n:
                    break

    return selected


def main():
    parser = argparse.ArgumentParser(description="Seed data uji nyata HERO Backend dari portal asli via REST API.")
    parser.add_argument("--per-source", type=int, default=15, help="Jumlah dokumen utama yang ditarik per sumber (default: 15).")
    parser.add_argument("--sources", type=str, default="ojk,jdih,onedrive", help="Daftar sumber dipisah koma (default: ojk,jdih,onedrive).")
    parser.add_argument("--naming-format", type=str, default="nama,jenis,tahun", help="Format penamaan baku KB (default: nama,jenis,tahun).")
    parser.add_argument("--reset", action="store_true", help="Jalankan demo_reset.py sebelum seeding.")
    parser.add_argument("--base-url", type=str, default="http://127.0.0.1:8000", help="Base URL REST API server (default: http://127.0.0.1:8000).")
    args = parser.parse_args()

    active_sources = [s.strip().lower() for s in args.sources.split(",") if s.strip()]
    naming_components = [p.strip() for p in args.naming_format.split(",") if p.strip()]

    print("=================================================================")
    print("HERO BACKEND - SEEDING DATA UJI NYATA DARI SUMBER ASLI")
    print(f"Base API URL   : {args.base_url}")
    print(f"Target Sumber  : {', '.join(active_sources)}")
    print(f"Per Sumber     : {args.per_source} dokumen")
    print(f"Format Penamaan: {naming_components}")
    print(f"Reset Database : {'Ya' if args.reset else 'Tidak'}")
    print("=================================================================")

    # 1. Eksekusi Reset jika diminta
    if args.reset:
        run_reset(REPO_ROOT)

    # 2. Cek Kesehatan API Server
    print("--> Memeriksa konektivitas dan kesehatan REST API server...")
    code, health = http_request(args.base_url, "GET", "/health")
    if code != 200 or not isinstance(health, dict) or health.get("database") != "ok":
        print(f"[FATAL] Server API tidak sehat atau database belum siap (Code: {code}): {health}")
        sys.exit(1)
    print(f"    Server online (Versi: {health.get('version', 'N/A')}, Status: {health.get('status')})\n")

    # 3. Ambil Sumber Scraping Eksisting
    code, existing_sources_resp = http_request(args.base_url, "GET", "/api/v1/scraping-sources/")
    existing_items = existing_sources_resp.get("items", []) if isinstance(existing_sources_resp, dict) else (existing_sources_resp if isinstance(existing_sources_resp, list) else [])
    existing_by_url = {s.get("url"): s for s in existing_items}

    seeding_stats = []

    # 4. Iterasi Pemrosesan per Sumber
    for s_key in active_sources:
        if s_key not in DEFAULT_SOURCES_SPEC:
            print(f"[SKIP] Sumber '{s_key}' tidak dikenali. Pilih dari: {list(DEFAULT_SOURCES_SPEC.keys())}")
            continue

        spec = DEFAULT_SOURCES_SPEC[s_key]
        src_name = spec["name"]
        src_type = spec["source_type"]
        src_url = spec["url"]
        crawl_depth = spec["crawl_depth"]
        max_pages = spec["max_pages"]
        is_jdih = spec["is_jdih"]

        print(f"-----------------------------------------------------------------")
        print(f"PROSES SUMBER: [{s_key.upper()}] {src_name}")
        print(f"URL: {src_url} | Tipe: {src_type} | Batas Paging: {max_pages}")
        print(f"-----------------------------------------------------------------")

        # 4.1 Registrasi atau Ambil Sumber
        source_id = None
        if src_url in existing_by_url:
            source_id = existing_by_url[src_url]["id"]
            print(f"  [1/4] Sumber sudah terdaftar (Source ID: {source_id}).")
        else:
            payload_src = {
                "name": src_name,
                "source_type": src_type,
                "url": src_url,
                "crawl_depth": crawl_depth,
                "max_pages": max_pages,
                "default_access_classification": "publik",
                "default_document_role": "corpus_eksisting",
            }
            code, create_res = http_request(args.base_url, "POST", "/api/v1/scraping-sources/", payload_src)
            if code not in (200, 201) or not isinstance(create_res, dict) or "id" not in create_res:
                print(f"  [GAGAL] Gagal mendaftarkan sumber (HTTP {code}): {create_res}")
                continue
            source_id = create_res["id"]
            print(f"  [1/4] Sumber berhasil didaftarkan (Source ID: {source_id}).")

        # 4.2 Mulai Pemindaian (Scan)
        print(f"  [2/4] Menjadwalkan pemindaian (POST /api/v1/scans/, depth={crawl_depth}, max_pages={max_pages})...")
        scan_payload = {
            "source_id": source_id,
            "crawl_depth": crawl_depth,
            "max_pages": max_pages,
        }
        code, scan_res = http_request(args.base_url, "POST", "/api/v1/scans/", scan_payload, timeout=60)
        if code not in (200, 201, 202) or not isinstance(scan_res, dict):
            print(f"  [GAGAL] Pemindaian gagal dimulai (HTTP {code}): {scan_res}")
            continue

        scan_id = scan_res.get("id") or scan_res.get("scan_id")
        scan_status = scan_res.get("status")

        # Safeguard jika masih memindai (polling)
        poll_count = 0
        while scan_status in ("antrian", "memindai"):
            time.sleep(2)
            poll_count += 1
            code, poll_res = http_request(args.base_url, "GET", f"/api/v1/scans/{scan_id}")
            if code == 200 and isinstance(poll_res, dict):
                scan_status = poll_res.get("status")
                scan_res = poll_res
                pages = poll_res.get("pages_visited", 0)
                c_cnt = poll_res.get("candidates_summary", {}).get("total", 0)
                if poll_count % 5 == 0:
                    print(f"        [Memindai...] Halaman: {pages}, Kandidat: {c_cnt}")
            if poll_count > 300:  # batas maksimal 10 menit
                print(f"        [TIMEOUT] Waktu tunggu pemindaian melebihi batas 10 menit.")
                break

        total_cands = scan_res.get("candidates_summary", {}).get("total", 0) if isinstance(scan_res.get("candidates_summary"), dict) else 0
        print(f"        Pemindaian selesai (Scan #{scan_id}, Status: {scan_status}). Total kandidat PDF ditemukan: {total_cands}")

        # 4.3 Ambil Daftar Kandidat
        code, cands_resp = http_request(args.base_url, "GET", f"/api/v1/scans/{scan_id}/candidates?limit=200")
        candidate_items = cands_resp.get("items", []) if isinstance(cands_resp, dict) else []
        print(f"  [3/4] Menganalisis {len(candidate_items)} kandidat berkas...")

        # 4.4 Pilih N Kandidat Bervariasi (hanya doc_kind == 'utama')
        diverse_cands = select_diverse_candidates(candidate_items, args.per_source, is_jdih=is_jdih)
        if not diverse_cands:
            print(f"        [PERINGATAN] Tidak ada kandidat 'utama' yang dapat ditarik untuk {s_key}.")
            continue

        selected_ids = [c["id"] for c in diverse_cands]
        print(f"        Terpilih {len(selected_ids)} kandidat 'utama' bervariasi:")
        for idx, dc in enumerate(diverse_cands, 1):
            bidang_str = dc.get("bidang") or "-"
            status_str = dc.get("status_keberlakuan") or "-"
            jenis_str = dc.get("regulation_type") or "-"
            tahun_str = str(dc.get("release_year") or "-")
            nomor_str = dc.get("regulation_number") or "-"
            print(f"          {idx:02d}. [ID:{dc['id']}] {nomor_str} ({jenis_str}, {tahun_str}) | Bidang: {bidang_str} | Status: {status_str}")

        # 4.5 Reset Centang dan Tetapkan Centang Pilihan
        http_request(args.base_url, "PATCH", f"/api/v1/scans/{scan_id}/selection", {"action": "select_none"})
        sel_payload = {
            "action": "set",
            "candidate_ids": selected_ids,
            "selected": True,
        }
        code, sel_res = http_request(args.base_url, "PATCH", f"/api/v1/scans/{scan_id}/selection", sel_payload)
        if code != 200:
            print(f"        [PERINGATAN] Gagal menetapkan seleksi (HTTP {code}): {sel_res}")

        # 4.6 Eksekusi Penarikan (Pull) ke Knowledge Base
        print(f"  [4/4] Menjadwalkan penarikan {len(selected_ids)} dokumen ke Knowledge Base (format={naming_components})...")
        pull_payload = {
            "destination": "knowledge_base",
            "naming_format": naming_components,
            "naming_separator": "_",
        }
        code, pull_res = http_request(args.base_url, "POST", f"/api/v1/scans/{scan_id}/pull", pull_payload, timeout=60)
        
        # Polling status pull jika belum selesai
        pull_status = pull_res.get("status") if isinstance(pull_res, dict) else "unknown"
        p_count = 0
        while pull_status in ("antrian", "menarik"):
            time.sleep(2)
            p_count += 1
            code, poll_pull = http_request(args.base_url, "GET", f"/api/v1/scans/{scan_id}")
            if code == 200 and isinstance(poll_pull, dict):
                pull_status = poll_pull.get("status")
                pull_res = poll_pull
                prog = poll_pull.get("pull_progress", {}) or {}
                if p_count % 5 == 0:
                    print(f"        [Menarik berkas...] Selesai: {prog.get('processed_count', 0)}/{prog.get('total_found', len(selected_ids))}")
            if p_count > 300:
                print(f"        [TIMEOUT] Waktu tunggu penarikan melebihi batas 10 menit.")
                break

        # Ambil statistik penarikan dari kandidat
        code, updated_cands_resp = http_request(args.base_url, "GET", f"/api/v1/scans/{scan_id}/candidates?limit=200")
        up_cands = updated_cands_resp.get("items", []) if isinstance(updated_cands_resp, dict) else []
        pulled_success = sum(1 for c in up_cands if c.get("id") in selected_ids and c.get("pull_outcome") in ("berhasil", "success", "diunduh"))
        print(f"        Penarikan selesai. Berhasil di-ingest ke Knowledge Base: {pulled_success}/{len(selected_ids)} dokumen.\n")

        seeding_stats.append({
            "key": s_key,
            "name": src_name,
            "type": src_type,
            "selected": len(selected_ids),
            "pulled": pulled_success,
        })

    # 5. Ambil Seluruh Dokumen Knowledge Base untuk Evaluasi Distribusi Nyata
    print("=================================================================")
    print("EVALUASI DISTRIBUSI DOKUMEN KNOWLEDGE BASE SETELAH SEEDING")
    print("=================================================================")
    code, docs_resp = http_request(args.base_url, "GET", "/api/v1/documents/?limit=100")
    docs = docs_resp.get("items", []) if isinstance(docs_resp, dict) else []
    total_docs = docs_resp.get("total", len(docs)) if isinstance(docs_resp, dict) else len(docs)

    bidang_counter = Counter()
    jenis_counter = Counter()
    tahun_counter = Counter()
    status_counter = Counter()

    for d in docs:
        b = d.get("bidang") or "(kosong)"
        bidang_counter[b] += 1
        j = d.get("regulation_type") or "(kosong)"
        jenis_counter[j] += 1
        y = str(d.get("release_year") or d.get("year") or (d.get("release_date")[:4] if d.get("release_date") else "(kosong)"))
        tahun_counter[y] += 1
        st = d.get("status_keberlakuan") or "tidak_diketahui"
        status_counter[st] += 1

    # Tabel 1: Dokumen Masuk per Sumber
    print("\n--- 1. Dokumen Masuk per Sumber ---")
    print(f"{'Kode Sumber':<12} | {'Nama Sumber':<32} | {'Target':<8} | {'Berhasil Masuk':<15}")
    print("-" * 75)
    for stat in seeding_stats:
        print(f"{stat['key']:<12} | {stat['name'][:32]:<32} | {stat['selected']:<8} | {stat['pulled']:<15}")
    print(f"{'TOTAL':<12} | {'Semua Sumber':<32} | {sum(s['selected'] for s in seeding_stats):<8} | {sum(s['pulled'] for s in seeding_stats):<15}")

    # Tabel 2: Distribusi Bidang
    print(f"\n--- 2. Distribusi Bidang ({len(bidang_counter)} kategori, Total: {total_docs}) ---")
    print(f"{'Bidang / Sektor':<45} | {'Jumlah Dokumen':<15}")
    print("-" * 65)
    for b_name, cnt in bidang_counter.most_common():
        print(f"{b_name[:45]:<45} | {cnt:<15}")

    # Tabel 3: Distribusi Jenis Regulasi
    print(f"\n--- 3. Distribusi Jenis Regulasi ({len(jenis_counter)} jenis) ---")
    print(f"{'Jenis Regulasi':<30} | {'Jumlah Dokumen':<15}")
    print("-" * 50)
    for j_name, cnt in jenis_counter.most_common():
        print(f"{j_name[:30]:<30} | {cnt:<15}")

    # Tabel 4: Distribusi Tahun
    print(f"\n--- 4. Distribusi Tahun Regulasi ({len(tahun_counter)} tahun) ---")
    print(f"{'Tahun':<20} | {'Jumlah Dokumen':<15}")
    print("-" * 40)
    for y_val, cnt in sorted(tahun_counter.items(), key=lambda x: str(x[0]), reverse=True):
        print(f"{y_val:<20} | {cnt:<15}")

    # Tabel 5: Distribusi Status Keberlakuan
    print(f"\n--- 5. Distribusi Status Keberlakuan ({len(status_counter)} nilai status) ---")
    print(f"{'Status Keberlakuan':<25} | {'Jumlah Dokumen':<15}")
    print("-" * 45)
    for st_val, cnt in status_counter.most_common():
        print(f"{st_val:<25} | {cnt:<15}")

    # 6. Cetak Ringkasan Dashboard (GET /dashboard/summary)
    print("\n=================================================================")
    print("OUTPUT MENTAH: GET /api/v1/dashboard/summary")
    print("=================================================================")
    code, dash = http_request(args.base_url, "GET", "/api/v1/dashboard/summary")
    if code == 200 and isinstance(dash, dict):
        print(json.dumps(dash, indent=2, ensure_ascii=False))
    else:
        print(f"[ERROR] Gagal mengambil dashboard summary (HTTP {code}): {dash}")

    print("\n[SELESAI] Seeding data uji integrasi frontend selesai dilakukan.")


if __name__ == "__main__":
    main()
