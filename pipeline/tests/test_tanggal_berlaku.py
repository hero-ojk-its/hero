"""Tanggal mulai berlaku (QA #89: "1 Januari 2027 tidak terambil, status tertulis berlaku").

Backend sudah menghitung status dari effective_date (aturan 5a); sisi data tak pernah mengisinya,
sehingga 1.057 dokumen berstatus tidak diketahui."""
from __future__ import annotations

from datetime import date, datetime

import pytest

from hero.analysis.structured import compose_summary, _tanggal_id
from hero.bridge import mapping, sync
from hero.extract.metadata import _detect_status, _extract_effective_date, extract_metadata
from hero.models import RegulationMetadata

TERBIT = date(2026, 8, 12)
PASAL_8_9 = """Pasal 8
Peraturan ini mulai berlaku pada tanggal yang ditetapkan dalam Peraturan ini.
Pasal 9
Agar setiap orang mengetahuinya, memerintahkan pengundangan Peraturan ini.
Peraturan ini mulai berlaku pada tanggal 1 Januari 2027.
Ditetapkan di Jakarta pada tanggal 12 Agustus 2026"""


@pytest.mark.parametrize("teks, harapan", [
    (PASAL_8_9, date(2027, 1, 1)),                                              # kalimat terakhir yang berisi tanggal
    ("Peraturan ini mulai berlaku pada tanggal 3 Mei 2025.", date(2025, 5, 3)),
    ("Peraturan ini berlaku sejak tanggal 3 Mei 2025.", date(2025, 5, 3)),
    ("Keputusan ini mulai berlaku pada tanggal ditetapkan.", TERBIT),
    ("Peraturan ini mulai berlaku pada tanggal diundangkan.\nDiundangkan di Jakarta pada tanggal 20 Agustus 2026",
     date(2026, 8, 20)),
    ("Peraturan ini mulai berlaku pada tanggal diundangkan.", None),             # tanggal pengundangan tak ada: tak ditebak
    ("Peraturan ini mulai berlaku 6 (enam) bulan sejak tanggal diundangkan.", None),   # durasi relatif tak dihitung
    ("Pada saat Peraturan ini mulai berlaku, Peraturan lama dicabut.", None),    # pencabutan, bukan masa berlaku
    ("Pasal 5 mulai berlaku pada tanggal 1 Januari 2030.", None),                # pasal tertentu, bukan dokumennya
    ("Peraturan ini mulai berlaku pada tanggal yang ditetapkan dalam Peraturan ini.", None),
    ("", None),
])
def test_tanggal_berlaku_hanya_bila_tertulis(teks, harapan):
    assert _extract_effective_date(teks, TERBIT) == harapan


def test_status_diturunkan_dari_tanggal_bukan_ditebak():
    hari = date(2026, 11, 10)
    assert _detect_status("", None, date(2027, 1, 1), today=hari) == "belum_berlaku"
    assert _detect_status("", None, date(2026, 11, 10), today=hari) == "berlaku"
    assert _detect_status("", None, date(2020, 1, 1), today=hari) == "berlaku"
    assert _detect_status("teks apa saja", None) == "unknown"                    # dulu "berlaku"
    assert _detect_status("Peraturan ini dinyatakan tidak berlaku", None, date(2020, 1, 1)) == "dicabut"
    assert _detect_status("", "PERUBAHAN ATAS PERATURAN X", date(2027, 1, 1), today=hari) == "diubah"


def test_ekstraksi_penuh_membaca_tanggal_dan_status_89():
    teks = ("PERATURAN OTORITAS JASA KEUANGAN\nNOMOR 91 TAHUN 2026\nTENTANG\nPENERAPAN TATA KELOLA\n\n"
            "Mengingat : 1. Undang-Undang Nomor 21 Tahun 2011;\nMEMUTUSKAN:\n" + PASAL_8_9)
    md = extract_metadata(teks)
    assert md.effective_date == date(2027, 1, 1)
    assert md.status in ("belum_berlaku", "berlaku")                             # bergantung hari ini; 2027 → belum
    assert md.to_dict()["effective_date"] == "2027-01-01"


def test_payload_ke_backend_membawa_tanggal_berlaku():
    md = RegulationMetadata(number="91/2026", effective_date=date(2027, 1, 1), issued_date=TERBIT)
    ekstraksi = type("E", (), {"text": "isi", "ocr_pages": 0})()
    p = mapping.extraction_payload(md, ekstraksi, send_full_text=False)
    assert p["effective_date"] == "2027-01-01" and p["release_date"] == "2026-08-12"
    md.effective_date = None
    assert mapping.extraction_payload(md, ekstraksi, send_full_text=False)["effective_date"] is None


def _baris(**kw):
    return {"id": 1, "file_hash": "h" * 64, "title": "X", "regulation_type": "POJK", "regulation_number": "1",
            "regulation_year": 2026, "document_role": "corpus_eksisting", "status_keberlakuan": "tidak_diketahui",
            "processing_status": "terindeks", **kw}


def test_cermin_tidak_lagi_memakai_tebakan_berlaku_untuk_status_tak_diketahui():
    assert sync._record(_baris(), "be-1", {"status": "unknown"}).metadata.status == "unknown"
    assert sync._record(_baris(), "be-1", {"status": "belum_berlaku"}).metadata.status == "belum_berlaku"
    assert sync._record(_baris(status_keberlakuan="belum_berlaku"), "be-1").metadata.status == "belum_berlaku"
    rec = sync._record(_baris(effective_date=date(2027, 1, 1)), "be-1", {"effective_date": "2020-01-01"})
    assert rec.metadata.effective_date == date(2027, 1, 1)                       # nilai backend menang


def test_ringkasan_menyebut_tanggal_bila_belum_berlaku():
    ident = {"jenis": "POJK", "nomor": "91", "tentang": "Tata Kelola", "status": "belum_berlaku",
             "tanggal_berlaku": "2027-01-01"}
    kalimat = compose_summary(ident, [], [], [], [], {})[0]["kalimat"]
    assert "belum berlaku, mulai berlaku 1 Januari 2027" in kalimat
    assert _tanggal_id("2027-01-01") == "1 Januari 2027" and _tanggal_id("rusak") == "rusak"


class _Kursor:
    def __init__(self, log):
        self.log = log

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def execute(self, sql, params):
        self.log.append((sql, params))

    def fetchall(self):
        return [(7,), (9,)]


class _Koneksi:
    def __init__(self, log):
        self.log = log

    def cursor(self):
        return _Kursor(self.log)

    def close(self):
        pass


def test_pemilihan_ulang_ekstraksi_dibatasi_waktu_dan_jumlah(monkeypatch):
    log: list = []
    monkeypatch.setattr(sync.pg, "connect", lambda dsn=None: _Koneksi(log))
    sebelum = datetime(2026, 11, 10, 12, 0)
    ids = sync.id_dokumen_untuk_ulang(sebelum=sebelum, tanpa_tanggal=True, jenis=["kepdk"], maks=50)
    assert ids == [7, 9]
    sql, params = log[0]
    assert "effective_date IS NULL" in sql and "extracted_at < %s" in sql and "ORDER BY id LIMIT" in sql
    assert params == [list(sync.SYNCABLE), sebelum, ["KEPDK"], 50]
    sync.id_dokumen_untuk_ulang(sebelum=sebelum)
    assert "effective_date IS NULL" not in log[1][0] and "regulation_type" not in log[1][0]
