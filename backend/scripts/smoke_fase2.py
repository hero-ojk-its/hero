#!/usr/bin/env python3
"""
scripts/smoke_fase2.py
Smoke test untuk memvalidasi ketersediaan dan fungsionalitas fitur Fase 2 HERO Backend
(pengujian milestone M2, Langkah 26–28, dan migrasi ke VPS baru).

Pemakaian:
    python scripts/smoke_fase2.py --base-url https://<domain-api> [--doc-id N] [--draft-id N] [--expect-revision REV] [--tanpa-harmonisasi] [--nama-tanpa-tahun STR]

Catatan efek samping dan metode HTTP:
S06 dan S07 menambah baris di analysis_results, analysis_runs, dan audit logs (RUN_ANALYSIS).
S22 (POST /api/v1/ml/harmonisasi/{id}) adalah satu-satunya permintaan non-GET.
Permintaan ini hanya menghitung harmonisasi per pasal draft terhadap korpus dokumen regulasi,
dengan efek samping cache/riwayat/audit (RUN_HARMONIZATION) yang serupa seperti S06.
Pengecualian ini dapat dinonaktifkan dengan opsi --tanpa-harmonisasi (S22 akan LEWATI "dinonaktifkan").
Selain S22, seluruh permintaan dalam skrip ini sepenuhnya berstatus hanya membaca (read-only)
dan menggunakan metode HTTP GET.
"""
import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import sys
from typing import Any, List, Optional
import httpx

# Pastikan direktori root masuk sys.path bila dijalankan langsung
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class Hasil:
    nama: str
    status: str  # "OK" | "GAGAL" | "LEWATI"
    keterangan: str = ""
    extra: Optional[Any] = None


CHECK_DESCRIPTIONS = {
    "S01": "GET /health",
    "S02": "GET /api/v1/auth/me",
    "S03": "GET /api/v1/ml/health",
    "S04": "Pilih dokumen uji",
    "S05": "GET /documents/{id}/versi",
    "S06": "GET /ml/analisa/{id} (panggilan 1)",
    "S07": "GET /ml/analisa/{id} (panggilan 2)",
    "S08": "GET /documents/{id}/analisa/banding",
    "S09": "GET /documents/{id}/analisa/riwayat",
    "S10": "GET .../riwayat/{run_id}",
    "S11": "Ekspor format=json",
    "S12": "Ekspor format=csv",
    "S13": "Ekspor format=docx",
    "S14": "GET /api/v1/audit-logs",
    "S15": "Penjaga non-publik",
    "S16": "GET /api/v1/dashboard/summary",
    "S17": "GET /api/v1/dashboard/corong",
    "S18": "GET /api/v1/dashboard/corong?format=csv",
    "S19": "GET /ingest/failures filter kode",
    "S20": "GET /api/v1/categories/tree",
    "S21": "Dokumen di kategori 'Tanpa Tahun'",
    "S22": "Harmonisasi per pasal",
}


def get_local_alembic_head(alembic_dir: Optional[str] = None) -> str:
    """Mendapatkan revisi head lokal dari direktori alembic."""
    try:
        from alembic.script import ScriptDirectory
        if alembic_dir is None:
            alembic_dir = str(Path(__file__).resolve().parent.parent / "alembic")
        script = ScriptDirectory(alembic_dir)
        heads = script.get_heads()
        return heads[0] if heads else ""
    except Exception:
        return ""


def run_checks(
    client: Any,
    expect_revision: Optional[str] = None,
    doc_id: Optional[int] = None,
    draft_id: Optional[int] = None,
    tanpa_harmonisasi: bool = False,
    nama_tanpa_tahun: str = "Tanpa Tahun",
) -> List[Hasil]:
    """
    Menjalankan rangkaian pengujian smoke test Fase 2 secara berurutan (S01 - S22).
    Seluruh permintaan jaringan menggunakan HTTP GET, kecuali S22 yang menggunakan POST /ml/harmonisasi/{id}.
    """
    if expect_revision is None:
        expect_revision = get_local_alembic_head()

    # Periksa token dari variabel lingkungan jika ada dan pasang ke header
    token = os.getenv("HERO_SMOKE_TOKEN")
    if token and hasattr(client, "headers"):
        existing_keys = {k.lower() for k in client.headers.keys()}
        if "authorization" not in existing_keys:
            client.headers["Authorization"] = f"Bearer {token}"

    hasil_list: List[Hasil] = []

    # S01: GET /health
    try:
        resp = client.get("/health")
        if resp.status_code == 200:
            data = resp.json()
            status_ok = data.get("status") == "ok"
            migrations_ok = data.get("migrations_up_to_date") is True
            vps_rev = data.get("alembic_revision")

            if expect_revision and vps_rev != expect_revision:
                hasil_list.append(Hasil(
                    "S01",
                    "GAGAL",
                    f"VPS belum di-deploy versi terbaru: {vps_rev} ≠ {expect_revision}",
                ))
            elif status_ok and migrations_ok:
                hasil_list.append(Hasil("S01", "OK", f"rev={vps_rev}"))
            else:
                hasil_list.append(Hasil(
                    "S01",
                    "GAGAL",
                    f"status={data.get('status')}, migrations_up_to_date={migrations_ok}",
                ))
        else:
            hasil_list.append(Hasil("S01", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S01", "GAGAL", f"Koneksi gagal: {exc}"))

    # S02: GET /api/v1/auth/me
    auth_enabled = False
    try:
        resp = client.get("/api/v1/auth/me")
        if resp.status_code == 200:
            data = resp.json()
            auth_enabled = bool(data.get("auth_enabled", False))
            hasil_list.append(Hasil("S02", "OK", f"auth_enabled={auth_enabled}"))
        else:
            hasil_list.append(Hasil("S02", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S02", "GAGAL", f"Koneksi gagal: {exc}"))

    # S03: GET /api/v1/ml/health
    ml_siap = False
    try:
        resp = client.get("/api/v1/ml/health")
        if resp.status_code == 200:
            data = resp.json()
            if data.get("status") == "siap":
                ml_siap = True
                hasil_list.append(Hasil("S03", "OK", "status=siap"))
            else:
                status_val = data.get("status", "belum siap")
                hasil_list.append(Hasil("S03", "LEWATI", f"ML tidak siap: {status_val}"))
        else:
            err_code = str(resp.status_code)
            try:
                err_data = resp.json().get("detail", {})
                if isinstance(err_data, dict) and "code" in err_data:
                    err_code = err_data["code"]
                elif isinstance(err_data, str):
                    err_code = err_data
            except Exception:
                pass
            hasil_list.append(Hasil("S03", "LEWATI", f"ML tidak siap: {err_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S03", "LEWATI", f"ML tidak siap: {exc}"))

    # S04: Pilih dokumen uji
    if doc_id is None:
        try:
            resp = client.get("/api/v1/documents/?access_classification=publik&processing_status=terindeks&limit=5")
            items = []
            if resp.status_code == 200:
                items = resp.json().get("items", [])

            if not items:
                resp = client.get("/api/v1/documents/?access_classification=publik&processing_status=perlu_koreksi&limit=5")
                if resp.status_code == 200:
                    items = resp.json().get("items", [])

            for item in items:
                p_status = item.get("processing_status")
                acc_class = item.get("access_classification")
                is_act = item.get("is_active", True)
                if (
                    p_status in ("terindeks", "perlu_koreksi")
                    and acc_class == "publik"
                    and is_act is not False
                ):
                    doc_id = item.get("id")
                    break
        except Exception:
            pass

    if doc_id is not None:
        hasil_list.append(Hasil("S04", "OK", f"doc_id={doc_id}"))
    else:
        hasil_list.append(Hasil("S04", "LEWATI", "Tidak ada dokumen publik aktif terindeks/perlu_koreksi"))

    # S05: GET /documents/{id}/versi
    if doc_id is None:
        hasil_list.append(Hasil("S05", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/versi")
            if resp.status_code == 200:
                data = resp.json()
                req_keys = ("induk", "diubah_oleh", "dicabut_oleh", "mencabut")
                if all(k in data for k in req_keys):
                    hasil_list.append(Hasil("S05", "OK", "kunci relasi versi lengkap"))
                else:
                    hasil_list.append(Hasil("S05", "GAGAL", "kunci versi tidak lengkap"))
            else:
                hasil_list.append(Hasil("S05", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S05", "GAGAL", f"Koneksi gagal: {exc}"))

    # S06: GET /ml/analisa/{id} (panggilan 1)
    s06_sukses = False
    run_id_s06 = None
    if doc_id is None:
        hasil_list.append(Hasil("S06", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/ml/analisa/{doc_id}")
            if ml_siap:
                if resp.status_code == 200:
                    data = resp.json()
                    run_id_s06 = data.get("cache", {}).get("run_id")
                    if run_id_s06 is not None:
                        s06_sukses = True
                        hasil_list.append(Hasil("S06", "OK", f"run_id={run_id_s06}"))
                    else:
                        hasil_list.append(Hasil("S06", "GAGAL", "cache.run_id tidak ditemukan"))
                else:
                    hasil_list.append(Hasil("S06", "GAGAL", f"HTTP {resp.status_code}"))
            else:
                if resp.status_code == 200:
                    data = resp.json()
                    cache_info = data.get("cache", {})
                    run_id_s06 = cache_info.get("run_id")
                    s06_sukses = True
                    hasil_list.append(Hasil("S06", "OK", "jalur ML mati"))
                elif resp.status_code in (503, 504):
                    hasil_list.append(Hasil("S06", "OK", "jalur ML mati"))
                else:
                    hasil_list.append(Hasil("S06", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S06", "GAGAL", f"Koneksi gagal: {exc}"))

    # S07: GET /ml/analisa/{id} (panggilan 2)
    if doc_id is None:
        hasil_list.append(Hasil("S07", "LEWATI", "Tidak ada dokumen uji"))
    elif not ml_siap:
        hasil_list.append(Hasil("S07", "LEWATI", "ML tidak siap"))
    else:
        try:
            resp = client.get(f"/api/v1/ml/analisa/{doc_id}")
            if resp.status_code == 200:
                data = resp.json()
                cache_info = data.get("cache", {})
                if cache_info.get("hit") is True:
                    hasil_list.append(Hasil("S07", "OK", "cache.hit=true"))
                else:
                    hasil_list.append(Hasil("S07", "GAGAL", f"cache.hit={cache_info.get('hit')}"))
            else:
                hasil_list.append(Hasil("S07", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S07", "GAGAL", f"Koneksi gagal: {exc}"))

    # S08: GET /documents/{id}/analisa/banding
    if doc_id is None:
        hasil_list.append(Hasil("S08", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/banding")
            if resp.status_code == 200:
                data = resp.json()
                det = data.get("deterministik")
                if s06_sukses and det is None:
                    hasil_list.append(Hasil("S08", "GAGAL", "deterministik null padahal analisa sukses"))
                else:
                    status_det = "ada" if det is not None else "null"
                    hasil_list.append(Hasil("S08", "OK", f"deterministik={status_det}"))
            else:
                hasil_list.append(Hasil("S08", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S08", "GAGAL", f"Koneksi gagal: {exc}"))

    # S09: GET /documents/{id}/analisa/riwayat
    if doc_id is None:
        hasil_list.append(Hasil("S09", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/riwayat")
            if resp.status_code == 200:
                data = resp.json()
                total = data.get("total", 0)
                if s06_sukses and total < 1:
                    hasil_list.append(Hasil("S09", "GAGAL", f"total={total} (< 1 padahal analisa sukses)"))
                else:
                    hasil_list.append(Hasil("S09", "OK", f"total={total}"))
            else:
                hasil_list.append(Hasil("S09", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S09", "GAGAL", f"Koneksi gagal: {exc}"))

    # S10: GET .../riwayat/{run_id} (dari S06)
    if doc_id is None or run_id_s06 is None:
        hasil_list.append(Hasil("S10", "LEWATI", "Tidak ada run_id dari analisa"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/riwayat/{run_id_s06}")
            if resp.status_code == 200:
                data = resp.json()
                hasil_ada = data.get("hasil") is not None
                cara_ulang_ada = bool(data.get("cara_ulang"))
                if hasil_ada and cara_ulang_ada:
                    hasil_list.append(Hasil("S10", "OK", f"run_id={run_id_s06}, cara_ulang terisi"))
                else:
                    hasil_list.append(Hasil("S10", "GAGAL", f"hasil={hasil_ada}, cara_ulang={cara_ulang_ada}"))
            else:
                hasil_list.append(Hasil("S10", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S10", "GAGAL", f"Koneksi gagal: {exc}"))

    # S11: Ekspor format=json
    if doc_id is None:
        hasil_list.append(Hasil("S11", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/ekspor?format=json")
            if resp.status_code == 200:
                data = resp.json()
                if "label" in data:
                    hasil_list.append(Hasil("S11", "OK", f"label={data.get('label')}"))
                else:
                    hasil_list.append(Hasil("S11", "GAGAL", "kunci 'label' tidak ada"))
            elif resp.status_code == 404 and not s06_sukses:
                hasil_list.append(Hasil("S11", "LEWATI", "Belum ada data analisa untuk diekspor"))
            else:
                hasil_list.append(Hasil("S11", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S11", "GAGAL", f"Koneksi gagal: {exc}"))

    # S12: Ekspor format=csv
    if doc_id is None:
        hasil_list.append(Hasil("S12", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/ekspor?format=csv")
            if resp.status_code == 200:
                content_bytes = resp.content
                has_bom = content_bytes.startswith(b"\xef\xbb\xbf")
                has_poin = b"poin_utama" in content_bytes
                if has_bom and has_poin:
                    hasil_list.append(Hasil("S12", "OK", f"BOM=ada, poin_utama=ada, bytes={len(content_bytes)}"))
                else:
                    hasil_list.append(Hasil("S12", "GAGAL", f"BOM={has_bom}, poin_utama={has_poin}"))
            elif resp.status_code == 404 and not s06_sukses:
                hasil_list.append(Hasil("S12", "LEWATI", "Belum ada data analisa untuk diekspor"))
            else:
                hasil_list.append(Hasil("S12", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S12", "GAGAL", f"Koneksi gagal: {exc}"))

    # S13: Ekspor format=docx
    if doc_id is None:
        hasil_list.append(Hasil("S13", "LEWATI", "Tidak ada dokumen uji"))
    else:
        try:
            resp = client.get(f"/api/v1/documents/{doc_id}/analisa/ekspor?format=docx")
            if resp.status_code == 200:
                content_bytes = resp.content
                cd_header = resp.headers.get("content-disposition", "")
                has_pk = content_bytes.startswith(b"PK")
                has_filename = "filename*=" in cd_header
                if has_pk and has_filename:
                    hasil_list.append(Hasil("S13", "OK", f"PK=ada, filename*=ada, bytes={len(content_bytes)}"))
                else:
                    hasil_list.append(Hasil("S13", "GAGAL", f"PK={has_pk}, filename*={has_filename}"))
            elif resp.status_code == 404 and not s06_sukses:
                hasil_list.append(Hasil("S13", "LEWATI", "Belum ada data analisa untuk diekspor"))
            else:
                hasil_list.append(Hasil("S13", "GAGAL", f"HTTP {resp.status_code}"))
        except Exception as exc:
            hasil_list.append(Hasil("S13", "GAGAL", f"Koneksi gagal: {exc}"))

    # S14: GET /api/v1/audit-logs/?action=RUN_ANALYSIS&limit=1
    try:
        resp = client.get("/api/v1/audit-logs/?action=RUN_ANALYSIS&limit=1")
        if resp.status_code in (401, 403):
            hasil_list.append(Hasil("S14", "LEWATI", f"token tanpa AUDIT_BACA ({resp.status_code})"))
        elif resp.status_code == 200:
            data = resp.json()
            if isinstance(data, list):
                total = len(data)
            elif isinstance(data, dict):
                total = data.get("total", len(data.get("items", [])))
            else:
                total = 0

            if total >= 1:
                hasil_list.append(Hasil("S14", "OK", f"total={total}"))
            elif doc_id is None or not s06_sukses:
                hasil_list.append(Hasil("S14", "LEWATI", "Belum ada entri audit RUN_ANALYSIS"))
            else:
                hasil_list.append(Hasil("S14", "GAGAL", "Entri audit RUN_ANALYSIS kosong"))
        else:
            hasil_list.append(Hasil("S14", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S14", "GAGAL", f"Koneksi gagal: {exc}"))

    # S15: Penjaga non-publik
    nonpub_id = None
    try:
        resp = client.get("/api/v1/documents/?access_classification=non_publik&limit=1")
        if resp.status_code == 200:
            items = resp.json().get("items", [])
            if items:
                nonpub_id = items[0].get("id")
    except Exception:
        pass

    if nonpub_id is None:
        hasil_list.append(Hasil("S15", "LEWATI", "Tidak ada dokumen non-publik"))
    else:
        if auth_enabled:
            hasil_list.append(Hasil("S15", "LEWATI", f"Auth aktif (doc_id={nonpub_id})"))
        else:
            try:
                resp_pdf = client.get(f"/api/v1/documents/{nonpub_id}/pdf")
                if resp_pdf.status_code == 403:
                    hasil_list.append(Hasil("S15", "OK", f"doc_id={nonpub_id} ditolak 403 saat auth mati"))
                else:
                    hasil_list.append(Hasil("S15", "GAGAL", f"doc_id={nonpub_id} status={resp_pdf.status_code} (bukan 403)"))
            except Exception as exc:
                hasil_list.append(Hasil("S15", "GAGAL", f"Koneksi gagal: {exc}"))

    # S16: GET /api/v1/dashboard/summary
    try:
        resp = client.get("/api/v1/dashboard/summary")
        if resp.status_code == 200:
            data = resp.json()
            by_status = data.get("by_status_keberlakuan") or data.get("kb", {}).get("by_status_keberlakuan")
            if isinstance(by_status, dict) and "belum_berlaku" in by_status:
                hasil_list.append(Hasil("S16", "OK", f"belum_berlaku={by_status.get('belum_berlaku')}"))
            else:
                hasil_list.append(Hasil("S16", "GAGAL", "server belum memuat Langkah 26"))
        else:
            hasil_list.append(Hasil("S16", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S16", "GAGAL", f"Koneksi gagal: {exc}"))

    # S17: GET /api/v1/dashboard/corong
    try:
        resp = client.get("/api/v1/dashboard/corong")
        if resp.status_code == 404:
            hasil_list.append(Hasil("S17", "GAGAL", "server belum memuat Langkah 27"))
        elif resp.status_code == 200:
            corong_data = resp.json()
            sumber_list = corong_data.get("sumber", [])
            total_info = corong_data.get("total", {})

            invarian_gagal = None
            for s in sumber_list:
                s_name = s.get("nama") or f"id={s.get('source_id')}"
                sc = s.get("scan", {})
                dk = s.get("dokumen", {})

                ditemukan = sc.get("ditemukan", 0)
                sum_5_scan = (
                    sc.get("sudah_ada_di_kb", 0)
                    + sc.get("ditarik", 0)
                    + sc.get("duplikat", 0)
                    + sc.get("gagal_unduh", 0)
                    + sc.get("belum_ditarik", 0)
                )
                if ditemukan != sum_5_scan:
                    invarian_gagal = f"invarian scan dilanggar pada sumber '{s_name}' ({ditemukan} ≠ {sum_5_scan})"
                    break

                di_kb = dk.get("di_kb", 0)
                sum_4_dok = (
                    dk.get("menunggu_ekstraksi", 0)
                    + dk.get("terbaca", 0)
                    + dk.get("gagal_baca", 0)
                    + dk.get("lainnya", 0)
                )
                if di_kb != sum_4_dok:
                    invarian_gagal = f"invarian dokumen dilanggar pada sumber '{s_name}' ({di_kb} ≠ {sum_4_dok})"
                    break

            if invarian_gagal:
                hasil_list.append(Hasil("S17", "GAGAL", invarian_gagal))
            else:
                tot_dok = total_info.get("dokumen", {})
                di_kb_tot = tot_dok.get("di_kb", 0)
                terbaca_tot = tot_dok.get("terbaca", 0)
                persen_tot = total_info.get("persen_terbaca", 0.0)
                n_sumber = len(sumber_list)
                ket = f"sumber={n_sumber}, di_kb={di_kb_tot}, terbaca={terbaca_tot} ({persen_tot}%)"

                scan_belum_ditarik = total_info.get("scan", {}).get("belum_ditarik", 0)
                pdf_belum_diperiksa = total_info.get("pdf", {}).get("belum_diperiksa", 0)
                hasil_list.append(Hasil(
                    "S17",
                    "OK",
                    ket,
                    extra={"belum_ditarik": scan_belum_ditarik, "belum_diperiksa": pdf_belum_diperiksa},
                ))
        else:
            hasil_list.append(Hasil("S17", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S17", "GAGAL", f"Koneksi gagal: {exc}"))

    # S18: GET /api/v1/dashboard/corong?format=csv
    try:
        resp = client.get("/api/v1/dashboard/corong?format=csv")
        if resp.status_code == 200:
            content_bytes = resp.content
            cd_header = resp.headers.get("content-disposition", "")
            has_bom = content_bytes.startswith(b"\xef\xbb\xbf")
            has_filename = "filename*=" in cd_header

            text_csv = content_bytes.decode("utf-8", errors="replace")
            lines = [line.strip() for line in text_csv.splitlines() if line.strip()]
            last_line = lines[-1] if lines else ""
            has_total = last_line.startswith(",TOTAL,") or (len(last_line.split(",")) > 1 and last_line.split(",")[1] == "TOTAL")

            if has_bom and has_filename and has_total:
                hasil_list.append(Hasil("S18", "OK", f"BOM=ada, TOTAL=ada, filename*=ada, bytes={len(content_bytes)}"))
            else:
                hasil_list.append(Hasil(
                    "S18",
                    "GAGAL",
                    f"BOM={has_bom}, TOTAL={has_total}, filename*={has_filename}",
                ))
        else:
            hasil_list.append(Hasil("S18", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S18", "GAGAL", f"Koneksi gagal: {exc}"))

    # S19: GET /api/v1/ingest/failures?reason_code=pdf_rusak&reason_code=pdf_terenkripsi&limit=5
    try:
        resp = client.get("/api/v1/ingest/failures?reason_code=pdf_rusak&reason_code=pdf_terenkripsi&limit=5")
        if resp.status_code in (401, 403):
            hasil_list.append(Hasil("S19", "LEWATI", "token tanpa izin kegagalan"))
        elif resp.status_code == 200:
            data = resp.json()
            items = data.get("items", []) if isinstance(data, dict) else (data if isinstance(data, list) else [])
            invalid_reasons = [
                it.get("reason_code") for it in items if it.get("reason_code") not in ("pdf_rusak", "pdf_terenkripsi")
            ]
            if invalid_reasons:
                hasil_list.append(Hasil("S19", "GAGAL", f"reason_code di luar filter: {invalid_reasons}"))
            else:
                hasil_list.append(Hasil("S19", "OK", f"items={len(items)}, filter bekerja"))
        else:
            hasil_list.append(Hasil("S19", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S19", "GAGAL", f"Koneksi gagal: {exc}"))

    # S20: GET /api/v1/categories/tree
    tree_data = None
    try:
        resp = client.get("/api/v1/categories/tree")
        if resp.status_code == 200:
            tree_data = resp.json()
            missing_keys = False
            node_count = 0

            def check_node(n):
                nonlocal missing_keys, node_count
                if not isinstance(n, dict):
                    return
                node_count += 1
                if "jumlah_dokumen" not in n or "classification_rule" not in n:
                    missing_keys = True
                for child in n.get("children", []):
                    check_node(child)

            if isinstance(tree_data, list):
                for node in tree_data:
                    check_node(node)
            elif isinstance(tree_data, dict):
                check_node(tree_data)

            if missing_keys:
                hasil_list.append(Hasil("S20", "GAGAL", "server belum memuat Langkah 28"))
            else:
                hasil_list.append(Hasil("S20", "OK", f"nodes={node_count}, kunci Langkah 28 lengkap"))
        else:
            hasil_list.append(Hasil("S20", "GAGAL", f"HTTP {resp.status_code}"))
    except Exception as exc:
        hasil_list.append(Hasil("S20", "GAGAL", f"Koneksi gagal: {exc}"))

    # S21: Dokumen di kategori "tanpa tahun"
    try:
        if tree_data is None:
            resp = client.get("/api/v1/categories/tree")
            if resp.status_code == 200:
                tree_data = resp.json()

        if tree_data is None:
            hasil_list.append(Hasil("S21", "GAGAL", "Gagal memuat pohon kategori"))
        else:
            tanpa_tahun_doc_count = 0

            def count_tanpa_tahun(n):
                nonlocal tanpa_tahun_doc_count
                if not isinstance(n, dict):
                    return
                if n.get("name") == nama_tanpa_tahun:
                    tanpa_tahun_doc_count += n.get("jumlah_dokumen", 0)
                for child in n.get("children", []):
                    count_tanpa_tahun(child)

            if isinstance(tree_data, list):
                for node in tree_data:
                    count_tanpa_tahun(node)
            elif isinstance(tree_data, dict):
                count_tanpa_tahun(tree_data)

            if tanpa_tahun_doc_count == 0:
                hasil_list.append(Hasil(
                    "S21",
                    "OK",
                    f"0 dokumen di '{nama_tanpa_tahun}'",
                    extra={"tanpa_tahun_count": 0, "nama_tanpa_tahun": nama_tanpa_tahun},
                ))
            else:
                ket = f"{tanpa_tahun_doc_count} dokumen di '{nama_tanpa_tahun}' — jalankan scripts/relokasi_kategori.py (dry-run dulu)"
                hasil_list.append(Hasil(
                    "S21",
                    "OK",
                    ket,
                    extra={"tanpa_tahun_count": tanpa_tahun_doc_count, "nama_tanpa_tahun": nama_tanpa_tahun},
                ))
    except Exception as exc:
        hasil_list.append(Hasil("S21", "GAGAL", f"Koneksi gagal: {exc}"))

    # S22: Harmonisasi per pasal
    if tanpa_harmonisasi:
        hasil_list.append(Hasil("S22", "LEWATI", "dinonaktifkan"))
    elif not ml_siap:
        hasil_list.append(Hasil("S22", "LEWATI", "ML tidak siap"))
    else:
        selected_draft_id = draft_id
        if selected_draft_id is None:
            try:
                resp_draft = client.get("/api/v1/documents/?document_role=draft_kajian&processing_status=terindeks&limit=1")
                items = resp_draft.json().get("items", []) if resp_draft.status_code == 200 else []
                if not items:
                    resp_draft = client.get("/api/v1/documents/?document_role=draft_kajian&processing_status=perlu_koreksi&limit=1")
                    items = resp_draft.json().get("items", []) if resp_draft.status_code == 200 else []
                if items:
                    selected_draft_id = items[0].get("id")
            except Exception:
                pass

        if selected_draft_id is None:
            hasil_list.append(Hasil("S22", "LEWATI", "Tidak ada draft kajian terindeks"))
        else:
            try:
                resp_h = client.post(f"/api/v1/ml/harmonisasi/{selected_draft_id}")
                if resp_h.status_code == 422:
                    hasil_list.append(Hasil("S22", "LEWATI", "KB pembanding kosong"))
                elif resp_h.status_code in (503, 504):
                    hasil_list.append(Hasil("S22", "LEWATI", "jalur ML mati"))
                elif resp_h.status_code == 200:
                    data_h = resp_h.json()
                    temuan = data_h.get("temuan")
                    per_jenis = data_h.get("ringkasan", {}).get("per_jenis")

                    if not isinstance(temuan, list) or not isinstance(per_jenis, dict):
                        hasil_list.append(Hasil("S22", "GAGAL", "Format respons tidak valid (temuan bukan list atau ringkasan.per_jenis bukan dict)"))
                    else:
                        hyperlink_valid = True
                        unknown_types = set()
                        standard_types = {"menggantikan", "memperjelas", "pasal_baru", "duplikasi", "konflik"}

                        for t in temuan:
                            if isinstance(t, dict):
                                j = t.get("jenis")
                                if j and j not in standard_types:
                                    unknown_types.add(str(j))

                                pmb = t.get("pembanding")
                                if isinstance(pmb, dict):
                                    pdf_url = pmb.get("pdf")
                                    pmb_doc_id = pmb.get("document_id")
                                    if pdf_url is not None:
                                        if not isinstance(pdf_url, str) or not pdf_url.startswith("/api/v1/documents/") or not isinstance(pmb_doc_id, int):
                                            hyperlink_valid = False
                                            break

                        if not hyperlink_valid:
                            hasil_list.append(Hasil("S22", "GAGAL", "hyperlink pembanding tidak valid"))
                        else:
                            ket = f"temuan={len(temuan)}, per_jenis={per_jenis}"
                            if unknown_types:
                                ket += f", jenis tak dikenal: {', '.join(sorted(unknown_types))}"
                            hasil_list.append(Hasil("S22", "OK", ket))
                else:
                    hasil_list.append(Hasil("S22", "GAGAL", f"HTTP {resp_h.status_code}"))
            except Exception as exc:
                if isinstance(exc, (httpx.ConnectError, httpx.TimeoutException, httpx.NetworkError)) or "connect" in type(exc).__name__.lower():
                    hasil_list.append(Hasil("S22", "LEWATI", "jalur ML mati"))
                else:
                    hasil_list.append(Hasil("S22", "GAGAL", f"Koneksi gagal: {exc}"))

    return hasil_list


def print_report(hasil_list: List[Hasil]) -> None:
    """Mencetak tabel hasil pemeriksaan ringkas dan rangkuman status akhir beserta peringatan."""
    print("=" * 84)
    print(f"{'Kode':<6} | {'Cek':<40} | {'Status':<8} | {'Keterangan'}")
    print("-" * 84)
    for h in hasil_list:
        desc = CHECK_DESCRIPTIONS.get(h.nama, h.nama)
        print(f"{h.nama:<6} | {desc:<40} | {h.status:<8} | {h.keterangan}")
    print("=" * 84)
    ok_cnt = sum(1 for h in hasil_list if h.status == "OK")
    gagal_cnt = sum(1 for h in hasil_list if h.status == "GAGAL")
    lewati_cnt = sum(1 for h in hasil_list if h.status == "LEWATI")
    print(f"RINGKASAN: {ok_cnt} OK, {gagal_cnt} GAGAL, {lewati_cnt} LEWATI")

    # 1. Peringatan lama: S05–S13 tidak dijalankan karena S04 LEWATI
    s04_item = next((h for h in hasil_list if h.nama == "S04"), None)
    if s04_item and s04_item.status == "LEWATI":
        print("PERINGATAN: cek analisa/riwayat/ekspor (S05–S13) tidak dijalankan karena tidak ada dokumen uji. Pakai --doc-id atau pastikan ada dokumen publik terindeks.")

    # 2. Peringatan baru: S21 > 0 dokumen di "Tanpa Tahun"
    s21_item = next((h for h in hasil_list if h.nama == "S21"), None)
    if s21_item and s21_item.extra and isinstance(s21_item.extra, dict):
        tt_cnt = s21_item.extra.get("tanpa_tahun_count", 0)
        tt_name = s21_item.extra.get("nama_tanpa_tahun", "Tanpa Tahun")
        if tt_cnt > 0:
            print(f"PERINGATAN: {tt_cnt} dokumen di '{tt_name}' — jalankan scripts/relokasi_kategori.py (dry-run dulu).")

    # 3. Peringatan baru: total.scan.belum_ditarik > 0
    s17_item = next((h for h in hasil_list if h.nama == "S17"), None)
    if s17_item and s17_item.extra and isinstance(s17_item.extra, dict):
        belum_ditarik = s17_item.extra.get("belum_ditarik", 0)
        if belum_ditarik > 0:
            print(f"PERINGATAN: {belum_ditarik} hasil scan belum ditarik ke KB — Pak Faris meminta semua hasil scan masuk KB (Weekly #7).")

        # 4. Peringatan baru: total.pdf.belum_diperiksa > 0
        belum_diperiksa = s17_item.extra.get("belum_diperiksa", 0)
        if belum_diperiksa > 0:
            print(f"PERINGATAN: {belum_diperiksa} dokumen belum diperiksa proteksi PDF — jalankan scripts/backfill_pdf_info.py --apply.")


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Smoke test Fase 2 untuk memvalidasi fitur HERO Backend (M2, Langkah 26–28 & migrasi VPS)."
    )
    parser.add_argument(
        "--base-url",
        default="http://localhost:8000",
        help="URL dasar API HERO Backend (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--doc-id",
        type=int,
        default=None,
        help="ID dokumen spesifik untuk diuji pada S05–S13 (opsional, default: auto-detect)",
    )
    parser.add_argument(
        "--draft-id",
        type=int,
        default=None,
        help="ID dokumen draft kajian untuk diuji pada S22 (opsional, default: auto-detect)",
    )
    parser.add_argument(
        "--expect-revision",
        default=None,
        help="Revisi Alembic yang diharapkan pada server (default: head lokal)",
    )
    parser.add_argument(
        "--tanpa-harmonisasi",
        action="store_true",
        default=False,
        help="Nonaktifkan pengujian harmonisasi per pasal (S22)",
    )
    parser.add_argument(
        "--nama-tanpa-tahun",
        default="Tanpa Tahun",
        help="Nama kategori 'tanpa tahun' yang diperiksa pada S21 (default: Tanpa Tahun)",
    )

    args = parser.parse_args()

    # Pastikan output konsol mendukung karakter UTF-8 di Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != 'utf-8':
        try:
            sys.stdout.reconfigure(encoding='utf-8', errors='replace')
        except Exception:
            pass

    base_url = args.base_url.rstrip("/")
    expect_rev = args.expect_revision or get_local_alembic_head()

    headers = {}
    token = os.getenv("HERO_SMOKE_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"

    print("=" * 84)
    print(f"       HERO BACKEND SMOKE TEST FASE 2 - {base_url}")
    print(f"       Revisi Alembic Diharapkan: {expect_rev or 'Auto'}")
    if token:
        print("       Autentikasi: Menggunakan HERO_SMOKE_TOKEN (terpasang)")
    else:
        print("       Autentikasi: Tidak ada HERO_SMOKE_TOKEN (mode anonim/dev)")
    print("=" * 84)

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=30.0) as client:
            hasil_list = run_checks(
                client=client,
                expect_revision=expect_rev,
                doc_id=args.doc_id,
                draft_id=args.draft_id,
                tanpa_harmonisasi=args.tanpa_harmonisasi,
                nama_tanpa_tahun=args.nama_tanpa_tahun,
            )
    except Exception as exc:
        print(f"FATAL: Gagal menghubungi server pada {base_url}: {exc}")
        return 1

    print_report(hasil_list)

    if any(h.status == "GAGAL" for h in hasil_list):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
