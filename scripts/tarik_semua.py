#!/usr/bin/env python3
"""
scripts/tarik_semua.py
Skrip penarikan otomatis hasil pemindaian (scan) ke Knowledge Base (KB) untuk persiapan UAT.
[Langkah 31, Weekly #7 Pak Faris]

Pemakaian:
    python scripts/tarik_semua.py --base-url https://<api> [--source-id N ...] [--apply] [--ulang-gagal] [--batas N] [--interval 15] [--timeout-menit 120]

Catatan Penting:
1. Mode Default adalah DRY-RUN (hanya-baca / metode GET).
   Tanpa argumen --apply, skrip hanya menginspeksi kandidat dan menampilkan ringkasan tanpa melakukan PATCH/POST.
2. Penarikan dokumen memicu unduhan berkas, validasi format PDF, penempatan ke direktori KB,
   serta pendaftaran antrean ekstraksi teks (worker lapisan data). Angka "terbaca" pada corong
   akan meningkat setelah worker background memproses berkas-berkas tersebut, bukan seketika saat tarikan selesai.
3. Disarankan untuk menguji penarikan bertahap terlebih dahulu menggunakan opsi --batas 20 per sumber.
4. Token otentikasi dapat disediakan melalui variabel lingkungan HERO_API_TOKEN.
   Skrip tidak menerima argumen token melalui CLI dan tidak akan pernah mencetak nilai token ke konsol.
"""

import argparse
from dataclasses import dataclass, field
import os
from pathlib import Path
import sys
import time
from typing import Any, Dict, List, Optional, Tuple

import httpx

# Pastikan direktori root masuk sys.path bila dijalankan langsung
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))


@dataclass
class OpsiTarik:
    source_ids: Optional[List[int]] = None
    apply: bool = False
    ulang_gagal: bool = False
    batas: Optional[int] = None
    interval: int = 15
    timeout_menit: int = 120


@dataclass
class HasilSumber:
    source_id: int
    nama: str
    session_id: Optional[int] = None
    status: str = "ok"  # "ok" | "dilewati" | "tidak_siap" | "gagal"
    catatan: str = ""
    perlu_ditarik: int = 0
    baru_count: int = 0
    ulang_gagal_count: int = 0
    sudah_ada_di_kb: int = 0
    ditarik: int = 0
    duplikat: int = 0
    gagal: int = 0


@dataclass
class RingkasanCorong:
    di_kb: int = 0
    belum_ditarik: int = 0


@dataclass
class Ringkasan:
    opsi: OpsiTarik
    sumber_list: List[HasilSumber] = field(default_factory=list)
    corong_sebelum: Optional[RingkasanCorong] = None
    corong_sesudah: Optional[RingkasanCorong] = None
    total_perlu_ditarik: int = 0
    total_ditarik: int = 0
    total_duplikat: int = 0
    total_gagal: int = 0
    exit_code: int = 0
    pesan_peringatan: Optional[str] = None


def ambil_corong(client: httpx.Client) -> Optional[RingkasanCorong]:
    """Mengambil metrik total corong dari endpoint dashboard/corong."""
    try:
        resp = client.get("/api/v1/dashboard/corong")
        if resp.status_code == 200:
            data = resp.json()
            total = data.get("total", {})
            di_kb = total.get("dokumen", {}).get("di_kb", 0)
            belum_ditarik = total.get("scan", {}).get("belum_ditarik", 0)
            return RingkasanCorong(di_kb=di_kb, belum_ditarik=belum_ditarik)
    except Exception:
        pass
    return None


def ambil_sumber(client: httpx.Client, source_ids: Optional[List[int]]) -> Tuple[List[Dict[str, Any]], Optional[str]]:
    """Mengambil daftar sumber aktif atau sumber berdasarkan filter ID."""
    try:
        resp = client.get("/api/v1/scraping-sources/")
        if resp.status_code != 200:
            return [], f"Gagal mengambil daftar sumber: HTTP {resp.status_code} {resp.text}"
        sources = resp.json()
        if not isinstance(sources, list):
            return [], "Format data sumber tidak valid (bukan list)."

        if source_ids:
            target_ids = set(source_ids)
            filtered = [s for s in sources if s.get("id") in target_ids]
        else:
            filtered = [s for s in sources if s.get("is_active")]

        filtered.sort(key=lambda s: s.get("id", 0))
        return filtered, None
    except Exception as exc:
        return [], f"Koneksi gagal saat mengambil sumber: {exc}"


def cari_sesi_terbaru(client: httpx.Client, source_id: int) -> Tuple[Optional[Dict[str, Any]], str, bool]:
    """
    Mencari sesi scan terbaru untuk suatu sumber.
    Mengembalikan (sesi, catatan, apakah_sedang_berjalan).
    """
    try:
        resp = client.get(f"/api/v1/scans/?source_id={source_id}&limit=100")
        if resp.status_code != 200:
            return None, f"HTTP {resp.status_code} saat cek sesi scan", False
        data = resp.json()
        items = data.get("items", [])
        if not items:
            return None, "tidak ada sesi scan siap — jalankan scan dulu", False

        # Cek apakah ada sesi yang sedang berjalan (memindai / menarik)
        active_sess = next((s for s in items if s.get("status") in ("memindai", "menarik")), None)
        if active_sess:
            return active_sess, "sesi sedang berjalan", True

        # Cari sesi terbaru yang siap_dipilih atau selesai
        ready_sess = next((s for s in items if s.get("status") in ("siap_dipilih", "selesai")), None)
        if ready_sess:
            return ready_sess, "siap", False

        return None, "tidak ada sesi scan siap — jalankan scan dulu", False
    except Exception as exc:
        return None, f"Kesalahan koneksi cek sesi: {exc}", False


def kumpulkan_kandidat(
    client: httpx.Client,
    scan_id: int,
    ulang_gagal: bool,
    batas: Optional[int],
) -> Tuple[List[int], int, int, int, Optional[str]]:
    """
    Mengumpulkan kandidat berkas yang perlu ditarik dengan paging hingga selesai.
    Mengembalikan (terpilih_ids, baru_count, ulang_gagal_count, sudah_ada_count, error).
    """
    semua_kandidat = []
    skip = 0
    limit = 200

    while True:
        try:
            resp = client.get(f"/api/v1/scans/{scan_id}/candidates?skip={skip}&limit={limit}")
            if resp.status_code != 200:
                return [], 0, 0, 0, f"HTTP {resp.status_code} saat membaca kandidat: {resp.text}"
            data = resp.json()
            items = data.get("items", [])
            total = data.get("total", 0)

            semua_kandidat.extend(items)
            skip += limit
            if skip >= total or not items:
                break
        except Exception as exc:
            return [], 0, 0, 0, f"Kesalahan koneksi paging kandidat: {exc}"

    sudah_ada_di_kb = 0
    baru_ids: List[int] = []
    ulang_gagal_ids: List[int] = []

    # Filter kandidat sesuai kriteria
    for c in semua_kandidat:
        cid = c.get("id")
        m_status = c.get("match_status")
        outcome = (c.get("pull_outcome") or "").strip().lower()

        if m_status == "sudah_ada":
            sudah_ada_di_kb += 1
            continue

        # Jangan pernah memilih yang sudah berhasil / duplikat / diunduh
        if outcome in ("success", "berhasil", "downloaded", "diunduh", "duplicate", "duplikat"):
            continue

        if not outcome:
            baru_ids.append(cid)
        elif outcome in ("failed", "gagal"):
            if ulang_gagal:
                ulang_gagal_ids.append(cid)

    # Gabungkan kandidat terurut berdasarkan id
    gabungan_kandidat: List[Tuple[int, bool]] = [(cid, True) for cid in baru_ids] + [
        (cid, False) for cid in ulang_gagal_ids
    ]
    gabungan_kandidat.sort(key=lambda x: x[0])

    if batas is not None and batas > 0:
        gabungan_kandidat = gabungan_kandidat[:batas]

    terpilih_ids = [item[0] for item in gabungan_kandidat]
    terpilih_baru = sum(1 for item in gabungan_kandidat if item[1])
    terpilih_ulang = sum(1 for item in gabungan_kandidat if not item[1])

    return terpilih_ids, terpilih_baru, terpilih_ulang, sudah_ada_di_kb, None


def hitung_hasil_penarikan(
    client: httpx.Client,
    scan_id: int,
    target_ids: Optional[List[int]] = None,
) -> Tuple[int, int, int]:
    """
    Menghitung jumlah berkas ditarik, duplikat, dan gagal dari kandidat sesi.
    Jika target_ids diberikan, hanya menghitung kandidat yang termasuk dalam daftar tersebut.
    """
    if not target_ids:
        try:
            resp_s = client.get(f"/api/v1/scans/{scan_id}/candidates?pull_outcome=success&limit=1")
            resp_d = client.get(f"/api/v1/scans/{scan_id}/candidates?pull_outcome=duplicate&limit=1")
            resp_f = client.get(f"/api/v1/scans/{scan_id}/candidates?pull_outcome=failed&limit=1")

            cnt_s = resp_s.json().get("total", 0) if resp_s.status_code == 200 else 0
            cnt_d = resp_d.json().get("total", 0) if resp_d.status_code == 200 else 0
            cnt_f = resp_f.json().get("total", 0) if resp_f.status_code == 200 else 0
            return cnt_s, cnt_d, cnt_f
        except Exception:
            return 0, 0, 0

    target_set = set(target_ids)
    cnt_s = 0
    cnt_d = 0
    cnt_f = 0
    skip = 0
    limit = 200

    while True:
        try:
            resp = client.get(f"/api/v1/scans/{scan_id}/candidates?selected=true&skip={skip}&limit={limit}")
            if resp.status_code != 200:
                break
            data = resp.json()
            items = data.get("items", [])
            for item in items:
                cid = item.get("id")
                if cid in target_set:
                    outcome = (item.get("pull_outcome") or "").strip().lower()
                    if outcome in ("success", "berhasil", "downloaded", "diunduh"):
                        cnt_s += 1
                    elif outcome in ("duplicate", "duplikat"):
                        cnt_d += 1
                    elif outcome in ("failed", "gagal"):
                        cnt_f += 1
            skip += limit
            if skip >= data.get("total", 0) or not items:
                break
        except Exception:
            break

    return cnt_s, cnt_d, cnt_f


def jalankan(client: httpx.Client, opsi: OpsiTarik) -> Ringkasan:
    """
    Fungsi inti eksekusi penarikan hasil scan ke Knowledge Base.
    Mendukung penyuntikan client (httpx.Client atau TestClient).
    """
    ringkasan = Ringkasan(opsi=opsi)

    # 1. Catat angka corong sebelum eksekusi
    ringkasan.corong_sebelum = ambil_corong(client)

    # 2. Ambil daftar sumber
    sumber_list, err_sumber = ambil_sumber(client, opsi.source_ids)
    if err_sumber:
        print(f"GALAT: {err_sumber}")
        ringkasan.exit_code = 1
        return ringkasan

    if not sumber_list:
        print("Tidak ada sumber dokumen yang sesuai untuk diproses.")
        ringkasan.corong_sesudah = ambil_corong(client)
        return ringkasan

    gagal_sumber_ids: List[int] = []

    # 3. Proses per sumber (sekuensial)
    for s in sumber_list:
        s_id = s.get("id")
        s_nama = s.get("name", f"Sumber #{s_id}")

        hasil_sumber = HasilSumber(source_id=s_id, nama=s_nama)

        sesi, catatan_sesi, is_running = cari_sesi_terbaru(client, s_id)
        if is_running:
            hasil_sumber.status = "dilewati"
            hasil_sumber.catatan = catatan_sesi
            ringkasan.sumber_list.append(hasil_sumber)
            print(f"[LEWATI] {s_nama} | {catatan_sesi}")
            continue

        if not sesi:
            hasil_sumber.status = "tidak_siap"
            hasil_sumber.catatan = catatan_sesi
            ringkasan.sumber_list.append(hasil_sumber)
            print(f"[LEWATI] {s_nama} | {catatan_sesi}")
            continue

        scan_id = sesi.get("id")
        hasil_sumber.session_id = scan_id

        # Kumpulkan kandidat
        ids, n_baru, n_ulang, n_sudah_ada, err_cand = kumpulkan_kandidat(
            client=client,
            scan_id=scan_id,
            ulang_gagal=opsi.ulang_gagal,
            batas=opsi.batas,
        )

        if err_cand:
            hasil_sumber.status = "gagal"
            hasil_sumber.catatan = err_cand
            ringkasan.sumber_list.append(hasil_sumber)
            ringkasan.exit_code = 1
            print(f"[GALAT] {s_nama} | sesi #{scan_id} | {err_cand}")
            continue

        hasil_sumber.perlu_ditarik = len(ids)
        hasil_sumber.baru_count = n_baru
        hasil_sumber.ulang_gagal_count = n_ulang
        hasil_sumber.sudah_ada_di_kb = n_sudah_ada
        ringkasan.total_perlu_ditarik += len(ids)

        # Mode DRY-RUN
        if not opsi.apply:
            hasil_sumber.catatan = "dry-run"
            ringkasan.sumber_list.append(hasil_sumber)
            print(
                f"{s_nama} | sesi #{scan_id} | perlu ditarik: {len(ids)} "
                f"(baru {n_baru}, ulang-gagal {n_ulang}) | sudah ada di KB: {n_sudah_ada}"
            )
            continue

        # Mode --apply
        if len(ids) == 0:
            hasil_sumber.catatan = "tidak ada kandidat yang perlu ditarik"
            ringkasan.sumber_list.append(hasil_sumber)
            print(f"{s_nama} | sesi #{scan_id} | tidak ada kandidat yang perlu ditarik")
            continue

        print(f"[APPLY] {s_nama} | sesi #{scan_id} | Menyiapkan centang untuk {len(ids)} berkas...")

        # Reset centang terlebih dahulu
        try:
            resp_none = client.patch(f"/api/v1/scans/{scan_id}/selection", json={"action": "select_none"})
            if resp_none.status_code != 200:
                hasil_sumber.status = "gagal"
                hasil_sumber.catatan = f"Gagal reset selection: HTTP {resp_none.status_code}"
                ringkasan.sumber_list.append(hasil_sumber)
                ringkasan.exit_code = 1
                continue
        except Exception as exc:
            hasil_sumber.status = "gagal"
            hasil_sumber.catatan = f"Koneksi gagal reset selection: {exc}"
            ringkasan.sumber_list.append(hasil_sumber)
            ringkasan.exit_code = 1
            continue

        # Kirim centang terpilih per batch 200 ID
        batch_err = None
        for i in range(0, len(ids), 200):
            batch = ids[i : i + 200]
            try:
                resp_set = client.patch(
                    f"/api/v1/scans/{scan_id}/selection",
                    json={"action": "set", "candidate_ids": batch, "selected": True},
                )
                if resp_set.status_code != 200:
                    batch_err = f"Gagal set batch selection: HTTP {resp_set.status_code}"
                    break
            except Exception as exc:
                batch_err = f"Koneksi gagal set batch: {exc}"
                break

        if batch_err:
            hasil_sumber.status = "gagal"
            hasil_sumber.catatan = batch_err
            ringkasan.sumber_list.append(hasil_sumber)
            ringkasan.exit_code = 1
            continue

        # Jalankan POST pull ke knowledge_base
        # PENTING: JANGAN mengirim category_id ke endpoint pull, karena bila category_id dikirim,
        # semua dokumen hasil tarikan akan ditandai dengan kategori_manual=True (Langkah 28)
        # sehingga mematikan relokasi otomatis oleh placement_service saat metadata dikoreksi.
        try:
            pull_payload = {"destination": "knowledge_base"}
            resp_pull = client.post(f"/api/v1/scans/{scan_id}/pull", json=pull_payload)
            if resp_pull.status_code not in (200, 202):
                hasil_sumber.status = "gagal"
                hasil_sumber.catatan = f"Gagal memulai pull: HTTP {resp_pull.status_code} {resp_pull.text}"
                ringkasan.sumber_list.append(hasil_sumber)
                ringkasan.exit_code = 1
                continue
        except Exception as exc:
            hasil_sumber.status = "gagal"
            hasil_sumber.catatan = f"Koneksi gagal memulai pull: {exc}"
            ringkasan.sumber_list.append(hasil_sumber)
            ringkasan.exit_code = 1
            continue

        # Polling status sesi sampai bukan 'menarik' atau timeout
        print(f"  Menunggu proses penarikan di server (interval: {opsi.interval}s)...")
        start_time = time.time()
        timeout_seconds = opsi.timeout_menit * 60
        is_timeout = False

        while True:
            try:
                resp_status = client.get(f"/api/v1/scans/{scan_id}")
                if resp_status.status_code == 200:
                    data_sess = resp_status.json()
                    st = data_sess.get("status")
                    if st != "menarik":
                        break
            except Exception as exc:
                print(f"  Peringatan koneksi saat polling sesi #{scan_id}: {exc}")

            if time.time() - start_time > timeout_seconds:
                is_timeout = True
                print(
                    f"PERINGATAN: Batas waktu {opsi.timeout_menit} menit terlampaui saat memproses "
                    f"sumber {s_nama} (sesi #{scan_id}). Tarikan tetap berlanjut di server."
                )
                hasil_sumber.catatan = f"timeout ({opsi.timeout_menit}m)"
                break

            if opsi.interval > 0:
                time.sleep(opsi.interval)

        # Hitung hasil akhir penarikan kandidat
        cnt_ditarik, cnt_duplikat, cnt_gagal = hitung_hasil_penarikan(client, scan_id, ids)
        hasil_sumber.ditarik = cnt_ditarik
        hasil_sumber.duplikat = cnt_duplikat
        hasil_sumber.gagal = cnt_gagal

        ringkasan.total_ditarik += cnt_ditarik
        ringkasan.total_duplikat += cnt_duplikat
        ringkasan.total_gagal += cnt_gagal

        if not is_timeout:
            hasil_sumber.catatan = "selesai ditarik"

        if cnt_gagal > 0:
            gagal_sumber_ids.append(s_id)

        ringkasan.sumber_list.append(hasil_sumber)

    # 4. Catat angka corong sesudah eksekusi
    ringkasan.corong_sesudah = ambil_corong(client)

    # 5. Siapkan pesan peringatan bila ada kegagalan
    if ringkasan.total_gagal > 0:
        sumber_filter_str = "&".join(f"source_id={sid}" for sid in gagal_sumber_ids) if gagal_sumber_ids else ""
        ringkasan.pesan_peringatan = (
            f"PERINGATAN: {ringkasan.total_gagal} kandidat gagal ditarik — lihat "
            f"GET /api/v1/ingest/failures?{sumber_filter_str} ; "
            f"jalankan ulang dengan --ulang-gagal setelah diperiksa."
        )

    return ringkasan


def cetak_laporan(ringkasan: Ringkasan):
    """Mencetak laporan ringkas ke stdout."""
    opsi = ringkasan.opsi

    print("\n" + "=" * 90)
    print("                    RINGKASAN PENARIKAN HASIL SCAN KE KB")
    print(f"                    Mode: {'APPLY (Tereksekusi)' if opsi.apply else 'DRY-RUN (Hanya Tinjauan)'}")
    print("=" * 90)

    # Tabel per sumber
    if opsi.apply:
        header = f"{'Sumber':<28} | {'Sesi':<6} | {'Perlu':<6} | {'Ditarik':<7} | {'Duplikat':<8} | {'Gagal':<6} | {'Catatan'}"
        print(header)
        print("-" * 90)
        for hs in ringkasan.sumber_list:
            sesi_str = f"#{hs.session_id}" if hs.session_id else "-"
            print(
                f"{hs.nama[:28]:<28} | {sesi_str:<6} | {hs.perlu_ditarik:<6} | {hs.ditarik:<7} | "
                f"{hs.duplikat:<8} | {hs.gagal:<6} | {hs.catatan}"
            )
    else:
        header = f"{'Sumber':<28} | {'Sesi':<6} | {'Perlu Ditarik (Baru / Ulang)':<30} | {'Di KB':<6} | {'Catatan'}"
        print(header)
        print("-" * 90)
        for hs in ringkasan.sumber_list:
            sesi_str = f"#{hs.session_id}" if hs.session_id else "-"
            rincian = f"{hs.perlu_ditarik} (baru {hs.baru_count}, ulang {hs.ulang_gagal_count})"
            print(f"{hs.nama[:28]:<28} | {sesi_str:<6} | {rincian:<30} | {hs.sudah_ada_di_kb:<6} | {hs.catatan}")

    # Tabel corong sebelum vs sesudah
    if ringkasan.corong_sebelum and ringkasan.corong_sesudah:
        sb = ringkasan.corong_sebelum
        sd = ringkasan.corong_sesudah
        d_kb = sd.di_kb - sb.di_kb
        d_blm = sd.belum_ditarik - sb.belum_ditarik

        print("\n" + "-" * 90)
        print(f"{'Metrik Corong':<36} | {'Sebelum':<12} | {'Sesudah':<12} | {'Perubahan'}")
        print("-" * 90)
        print(f"{'Total Dokumen di KB':<36} | {sb.di_kb:<12} | {sd.di_kb:<12} | {d_kb:+d}")
        print(f"{'Total Scan Belum Ditarik':<36} | {sb.belum_ditarik:<12} | {sd.belum_ditarik:<12} | {d_blm:+d}")

    print("=" * 90)

    # Baris RINGKASAN
    if opsi.apply:
        print(
            f"RINGKASAN: {len(ringkasan.sumber_list)} sumber diproses | Perlu Ditarik: {ringkasan.total_perlu_ditarik} "
            f"| Berhasil Ditarik: {ringkasan.total_ditarik} | Duplikat: {ringkasan.total_duplikat} | Gagal: {ringkasan.total_gagal}"
        )
    else:
        print(
            f"RINGKASAN: {len(ringkasan.sumber_list)} sumber diproses | Perlu Ditarik: {ringkasan.total_perlu_ditarik} "
            f"| Mode: DRY-RUN (tidak ada berkas ditarik)"
        )

    # Pesan peringatan bila ada kegagalan
    if ringkasan.pesan_peringatan:
        print(ringkasan.pesan_peringatan)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Skrip penarikan semua hasil pemindaian ke Knowledge Base (default: DRY-RUN)",
    )
    parser.add_argument(
        "--base-url",
        required=True,
        help="Alamat dasar API backend (misal: http://localhost:8000 atau https://hero.lan)",
    )
    parser.add_argument(
        "--source-id",
        nargs="+",
        type=int,
        default=None,
        help="ID sumber dokumen spesifik yang ingin diproses (opsional, default: seluruh sumber aktif)",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        default=False,
        help="Jalankan penarikan berkas sesungguhnya (default: False / DRY-RUN)",
    )
    parser.add_argument(
        "--ulang-gagal",
        action="store_true",
        default=False,
        help="Sertakan juga kandidat yang sebelumnya berstatus gagal (failed)",
    )
    parser.add_argument(
        "--batas",
        type=int,
        default=None,
        help="Membatasi jumlah kandidat yang ditarik per sumber (misal: 20)",
    )
    parser.add_argument(
        "--interval",
        type=int,
        default=15,
        help="Interval polling status sesi penarikan dalam detik (default: 15)",
    )
    parser.add_argument(
        "--timeout-menit",
        type=int,
        default=120,
        help="Batas waktu maksimum polling sesi penarikan per sumber dalam menit (default: 120)",
    )

    args = parser.parse_args()

    # Pastikan output konsol mendukung karakter UTF-8 di Windows
    if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
        try:
            sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    base_url = args.base_url.rstrip("/")
    headers = {}
    token = os.getenv("HERO_API_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
        print("Autentikasi: Menggunakan HERO_API_TOKEN (terpasang)")
    else:
        print("Autentikasi: Tidak ada HERO_API_TOKEN (mode anonim/dev)")

    opsi = OpsiTarik(
        source_ids=args.source_id,
        apply=args.apply,
        ulang_gagal=args.ulang_gagal,
        batas=args.batas,
        interval=args.interval,
        timeout_menit=args.timeout_menit,
    )

    try:
        with httpx.Client(base_url=base_url, headers=headers, timeout=60.0) as client:
            ringkasan = jalankan(client, opsi)
            cetak_laporan(ringkasan)
            return ringkasan.exit_code
    except Exception as exc:
        print(f"FATAL: Gagal menghubungi server pada {base_url}: {exc}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
