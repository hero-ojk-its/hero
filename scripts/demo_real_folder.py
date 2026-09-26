"""
scripts/demo_real_folder.py
Demonstrasi nyata pendaftaran dan sinkronisasi folder lokal dengan 5 PDF peraturan perbankan OJK pada hero_db.
"""
import json
import os
from pathlib import Path
import httpx

def make_pdf_bytes(title: str, reg_num: str, about: str, body_text: str) -> bytes:
    content = (
        f"OTORITAS JASA KEUANGAN REPUBLIK INDONESIA\n"
        f"SALINAN {reg_num}\n"
        f"TENTANG\n{about.upper()}\n\n"
        f"DENGAN RAHMAT TUHAN YANG MAHA ESA\n"
        f"DEWAN KOMISIONER OTORITAS JASA KEUANGAN,\n\n"
        f"Menimbang: a. bahwa untuk mewujudkan sistem perbankan yang sehat, berdaya saing, dan berintegritas;\n"
        f"Mengingat: Undang-Undang Nomor 21 Tahun 2011 tentang Otoritas Jasa Keuangan;\n\n"
        f"MEMUTUSKAN:\nMenetapkan: {title}.\n\n"
        f"BAB I KETENTUAN UMUM\nPasal 1\nDalam Peraturan Otoritas Jasa Keuangan ini yang dimaksud dengan:\n"
        f"{body_text}\n"
    )
    content_bytes = content.encode("utf-8")
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

def main():
    demo_dir = Path("./sources/demo_ojk_peraturan")
    demo_dir.mkdir(parents=True, exist_ok=True)

    regulations = [
        {
            "filename": "POJK_11_2022_Penyelenggaraan_Teknologi_Informasi.pdf",
            "title": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 11/POJK.03/2022 TENTANG PENYELENGGARAAN TEKNOLOGI INFORMASI OLEH BANK UMUM",
            "reg_num": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 11/POJK.03/2022",
            "about": "Penyelenggaraan Teknologi Informasi oleh Bank Umum",
            "body": "1. Bank Umum adalah Bank yang melaksanakan kegiatan usaha secara konvensional atau syariah. 2. Teknologi Informasi adalah teknologi pengelolaan sistem perbankan.",
        },
        {
            "filename": "POJK_12_2023_Penerapan_Tata_Kelola_Syariah.pdf",
            "title": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 12/POJK.03/2023 TENTANG PENERAPAN TATA KELOLA SYARIAH BAGI BANK UMUM SYARIAH",
            "reg_num": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 12/POJK.03/2023",
            "about": "Penerapan Tata Kelola Syariah bagi Bank Umum Syariah",
            "body": "1. Dewan Pengawas Syariah adalah dewan yang bertugas memberikan nasihat dan saran kepada Direksi serta mengawasi kegiatan Bank agar sesuai dengan Prinsip Syariah.",
        },
        {
            "filename": "POJK_17_2023_Penerapan_Tata_Kelola_Bank_Umum.pdf",
            "title": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 17/POJK.03/2023 TENTANG PENERAPAN TATA KELOLA BAGI BANK UMUM",
            "reg_num": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 17/POJK.03/2023",
            "about": "Penerapan Tata Kelola bagi Bank Umum",
            "body": "1. Tata Kelola Bank adalah struktur dan proses yang digunakan untuk mengarahkan dan mengelola usaha perbankan guna meningkatkan kinerja bisnis dan nilai bagi pemangku kepentingan.",
        },
        {
            "filename": "POJK_19_2023_Pengembangan_Kualitas_SDM_BPR.pdf",
            "title": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 19/POJK.03/2023 TENTANG PENGEMBANGAN KUALITAS SUMBER DAYA MANUSIA BPR DAN BPRS",
            "reg_num": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 19/POJK.03/2023",
            "about": "Pengembangan Kualitas Sumber Daya Manusia BPR dan BPRS",
            "body": "1. Sumber Daya Manusia BPR dan BPRS wajib ditingkatkan kompetensinya secara berkesinambungan melalui alokasi dana pendidikan dan pelatihan sekurang-kurangnya 5% dari anggaran SDM.",
        },
        {
            "filename": "POJK_21_2023_Layanan_Digital_Bank_Umum.pdf",
            "title": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 21/POJK.03/2023 TENTANG LAYANAN DIGITAL OLEH BANK UMUM",
            "reg_num": "PERATURAN OTORITAS JASA KEUANGAN NOMOR 21/POJK.03/2023",
            "about": "Layanan Digital oleh Bank Umum",
            "body": "1. Layanan Perbankan Digital adalah layanan perbankan elektronik yang dikembangkan dengan mengoptimalkan pemanfaatan data nasabah dalam rangka melayani nasabah secara lebih cepat dan aman.",
        },
    ]

    print("==> Menulis 5 berkas PDF regulasi OJK ke:", demo_dir.resolve())
    for r in regulations:
        target_f = demo_dir / r["filename"]
        target_f.write_bytes(make_pdf_bytes(r["title"], r["reg_num"], r["about"], r["body"]))
        print(f"    - Dibuat: {r['filename']} ({len(target_f.read_bytes())} bytes)")

    client = httpx.Client(base_url="http://127.0.0.1:8000", timeout=30.0)

    # 1. Daftarkan Folder Lokal
    folder_path = "/app/sources/demo_ojk_peraturan"  # path di dalam Docker
    payload = {
        "name": "Direktori Regulasi Perbankan OJK 2022-2023",
        "url": folder_path,
        "source_type": "folder_lokal",
        "recursive": True,
        "default_access_classification": "publik",
        "default_document_role": "corpus_eksisting",
    }
    print("\n==> Mendaftarkan sumber folder lokal ke API...")
    res_reg = client.post("/api/v1/scraping-sources/", json=payload)
    if res_reg.status_code != 201:
        # Coba path absolut host jika server running secara lokal
        payload["url"] = str(demo_dir.resolve())
        res_reg = client.post("/api/v1/scraping-sources/", json=payload)

    print(f"Status Pendaftaran: {res_reg.status_code}")
    print(json.dumps(res_reg.json(), indent=2, ensure_ascii=False))

    source_id = res_reg.json()["id"]

    # 2. Jalankan Sinkronisasi (Run)
    print(f"\n==> Menjalankan sinkronisasi sumber ID {source_id} (wait=true)...")
    res_run = client.post(f"/api/v1/scraping-sources/{source_id}/run?wait=true")
    print(f"Status Run: {res_run.status_code}")
    print("Respons Run (Raw JSON):")
    print(json.dumps(res_run.json(), indent=2, ensure_ascii=False))

    # 3. Ambil Hasil Files
    print(f"\n==> Mengambil daftar berkas terindeks (/scraping-sources/{source_id}/files)...")
    res_files = client.get(f"/api/v1/scraping-sources/{source_id}/files")
    print(f"Status Files: {res_files.status_code}")
    print("Respons Files (Raw JSON):")
    print(json.dumps(res_files.json(), indent=2, ensure_ascii=False))

    # 4. Ambil Dashboard Summary
    print("\n==> Mengambil ringkasan dashboard (/api/v1/dashboard/summary)...")
    res_dash = client.get("/api/v1/dashboard/summary")
    print(f"Status Dashboard: {res_dash.status_code}")
    print("Respons Dashboard (Raw JSON):")
    print(json.dumps(res_dash.json(), indent=2, ensure_ascii=False))

if __name__ == "__main__":
    main()
