"""Penyiapan set uji UAT Fase 2 — skenario 1.480 + 20 (MoM Weekly #7, 27 Okt 2026).

Skenario Pak Faris, apa adanya: dari korpus yang ada, masukkan semuanya ke
Knowledge Base **kecuali** 20 dokumen yang disisihkan. Setelah KB terisi:

1. **Fase A — keterbacaan.** Masukkan 20 dokumen yang disisihkan itu.
   Pertanyaannya "terbaca atau tidak?", jadi tiap dokumen perlu nilai harapan
   (jenis, nomor, tahun, jumlah pasal) supaya hasilnya bisa dinilai lulus/gagal
   dan bukan dikira-kira saat demo.
2. **Fase B — deteksi duplikat.** Masukkan lagi 20 dokumen yang SUDAH ada di KB.
   Harapannya dikenali sebagai duplikat, dibandingkan lewat hash + ukuran
   (KEP-06/ADR-05) — karena itu sha256 dan ukuran ikut dicatat.

Dua hal yang membuat set ini bukan sekadar 20 baris pertama:

* **Deterministik.** Urutan ditentukan hash stabil dari ``seed|doc_id``, bukan
  ``ORDER BY rowid`` atau acak tanpa benih. Perintah yang sama atas katalog yang
  sama selalu memilih 20 dokumen yang sama, sehingga UAT bisa diulang dan
  pilihannya bisa dipertanggungjawabkan (tidak di-*cherry-pick*).
* **Berlapis per jenis + kasus sulit.** Sampel acak 20 dari korpus yang 70%
  POJK berpeluang besar berisi POJK semua dan PDF yang lapisan teksnya bersih.
  MoM #7 justru menyebut PDF hasil pindai dan PDF terproteksi sebagai skenario
  yang harus diuji, jadi dokumen hasil pindai didahulukan lalu sisanya diisi
  merata antar jenis.

Deterministik dan tanpa jaringan (URD 3.1): modul ini hanya membaca katalog.
"""
from __future__ import annotations

import hashlib
import sqlite3
from typing import Any

SEED_BAWAAN = "uat-fase2"


def _peringkat(doc_id: str, seed: str) -> str:
    return hashlib.sha256(f"{seed}|{doc_id}".encode()).hexdigest()


def _baris(conn: sqlite3.Connection) -> list[sqlite3.Row]:
    conn.row_factory = sqlite3.Row
    return list(conn.execute(
        "SELECT doc_id, sha256, doc_type, number, year, title, stored_path, "
        "       page_count, ocr_pages, is_scanned, size_bytes, access_class, status "
        "FROM documents WHERE status = 'ingested'"))


def pilih_disisihkan(rows: list[sqlite3.Row], *, sisihkan: int,
                     seed: str = SEED_BAWAAN) -> list[sqlite3.Row]:
    """Pilih dokumen yang disisihkan: hasil pindai dulu, lalu merata antar jenis."""
    urut = sorted(rows, key=lambda r: _peringkat(r["doc_id"], seed))
    dipilih: list[sqlite3.Row] = []
    sudah: set[str] = set()

    # Kasus sulit lebih dulu — ini yang diminta MoM #7, dan jumlahnya sedikit.
    for r in urut:
        if len(dipilih) >= sisihkan:
            break
        if r["is_scanned"] or (r["ocr_pages"] or 0) > 0:
            dipilih.append(r)
            sudah.add(r["doc_id"])

    # Lalu putaran per jenis (round-robin) supaya satu jenis tidak mendominasi.
    per_jenis: dict[str, list[sqlite3.Row]] = {}
    for r in urut:
        if r["doc_id"] in sudah:
            continue
        per_jenis.setdefault((r["doc_type"] or "?").upper(), []).append(r)
    while len(dipilih) < sisihkan and any(per_jenis.values()):
        for jenis in sorted(per_jenis):
            if len(dipilih) >= sisihkan:
                break
            if per_jenis[jenis]:
                r = per_jenis[jenis].pop(0)
                dipilih.append(r)
                sudah.add(r["doc_id"])
    return dipilih[:sisihkan]


def _kasus_keterbacaan(r: sqlite3.Row) -> dict[str, Any]:
    # Dokumen yang identitasnya sendiri belum terbaca tidak bisa dipakai sebagai
    # kriteria lulus "terbaca atau tidak" — harapannya akan berbunyi "None None".
    # Ditandai, bukan dibuang: justru inilah antrian koreksi manual (US-20).
    lengkap = bool(r["doc_type"] and r["number"] and r["year"])
    return {
        "doc_id": r["doc_id"],
        "sha256": r["sha256"],
        "berkas": r["stored_path"],
        "akses": r["access_class"],
        "sulit": bool(r["is_scanned"] or (r["ocr_pages"] or 0) > 0),
        "harapan_lengkap": lengkap,
        "harapan": {
            "jenis": r["doc_type"],
            "nomor": r["number"],
            "tahun": r["year"],
            "judul": r["title"],
            "jumlah_halaman": r["page_count"],
        },
    }


def _kasus_duplikat(r: sqlite3.Row) -> dict[str, Any]:
    return {
        "doc_id": r["doc_id"],
        "berkas": r["stored_path"],
        # Duplikat dinilai dari hash DAN ukuran bersama-sama (KEP-06/ADR-05).
        "sha256": r["sha256"],
        "ukuran_bytes": r["size_bytes"],
        "harapan": "dikenali_duplikat",
    }


def siapkan(conn: sqlite3.Connection, *, sisihkan: int = 20,
            seed: str = SEED_BAWAAN) -> dict[str, Any]:
    """Susun manifes UAT: apa yang masuk KB, apa yang diuji, dan harapannya."""
    rows = _baris(conn)
    total = len(rows)
    if total <= sisihkan:
        return {"cukup": False, "total_dokumen": total, "sisihkan_diminta": sisihkan,
                "alasan": f"korpus hanya {total} dokumen — perlu lebih dari {sisihkan} "
                          "agar ada yang bisa dimuat ke KB lebih dulu"}

    disisihkan = pilih_disisihkan(rows, sisihkan=sisihkan, seed=seed)
    ids = {r["doc_id"] for r in disisihkan}
    ke_kb = [r for r in rows if r["doc_id"] not in ids]

    # Fase B memakai dokumen yang SUDAH di KB — diambil dari ujung urutan yang
    # berlawanan supaya tidak bertabrakan dengan pilihan fase A.
    urut_kb = sorted(ke_kb, key=lambda r: _peringkat(r["doc_id"], seed), reverse=True)
    dup = urut_kb[:min(sisihkan, len(urut_kb))]

    sulit = sum(1 for r in disisihkan if r["is_scanned"] or (r["ocr_pages"] or 0) > 0)
    fase_a = [_kasus_keterbacaan(r) for r in disisihkan]
    return {
        "cukup": True,
        "seed": seed,
        "total_dokumen": total,
        "muat_ke_kb": len(ke_kb),
        "disisihkan": len(disisihkan),
        "sebaran_jenis_disisihkan": _hitung(disisihkan),
        "kasus_sulit_disisihkan": sulit,
        "harapan_tidak_lengkap": sum(1 for k in fase_a if not k["harapan_lengkap"]),
        "fase_a_keterbacaan": fase_a,
        "fase_b_duplikat": [_kasus_duplikat(r) for r in dup],
    }


def _hitung(rows: list[sqlite3.Row]) -> dict[str, int]:
    out: dict[str, int] = {}
    for r in rows:
        k = (r["doc_type"] or "?").upper()
        out[k] = out.get(k, 0) + 1
    return dict(sorted(out.items(), key=lambda kv: (-kv[1], kv[0])))
