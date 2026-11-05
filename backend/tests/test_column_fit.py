"""Pemangkasan teks ke panjang kolom String(n) (tanpa database)."""
from sqlalchemy import Column, Integer, String, Text
from sqlalchemy.orm import declarative_base

from app.services.column_fit import ELLIPSIS, clip_to_columns, fit_text

Base = declarative_base()


class Contoh(Base):
    __tablename__ = "contoh_fit"
    id = Column(Integer, primary_key=True)
    sub_bidang = Column(String(100))
    judul = Column(String(20))
    bebas = Column(Text)
    angka = Column(Integer)


def test_fit_text_muat_tidak_berubah_dan_terpotong_bertanda():
    assert fit_text("abc", 5) == "abc"
    out = fit_text("x" * 50, 10)
    assert len(out) == 10 and out.endswith(ELLIPSIS)


def test_kasus_nyata_sub_bidang_ojk_118_karakter():
    """Daftar Sub Sektor asli dari ojk.go.id (aslinya 118 karakter) membuat INSERT gagal."""
    asli = ("Lembaga Pembiayaan; Lembaga Keuangan Mikro; Lembaga Jasa Keuangan Lainnya; "
            "Perusahaan Modal Ventura; Peraturan")
    assert len(asli) > 100          # kolom sub_bidang hanya String(100)
    obj = Contoh(sub_bidang=asli, judul="pendek", bebas="y" * 5000, angka=7)
    assert clip_to_columns(obj) == 1
    assert len(obj.sub_bidang) <= 100 and obj.sub_bidang.endswith(ELLIPSIS)
    assert obj.sub_bidang.startswith("Lembaga Pembiayaan; Lembaga Keuangan Mikro")
    assert obj.judul == "pendek" and len(obj.bebas) == 5000 and obj.angka == 7


def test_nilai_none_dan_pas_batas_dibiarkan():
    obj = Contoh(sub_bidang=None, judul="x" * 20)
    assert clip_to_columns(obj) == 0
    assert obj.judul == "x" * 20
