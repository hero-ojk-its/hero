"""
app/services/catatan_dinas_export_service.py
Layanan untuk mengekspor laporan harmonisasi regulasi ke format "Catatan Dinas" (DOCX dan PDF).
Format Catatan Dinas mengikuti tata naskah dinas resmi DPEA / OJK.
"""
from dataclasses import dataclass
from datetime import date, datetime, timedelta, timezone
import html
import io
import logging
import re
from typing import Any, Dict, List, Optional, Set, Tuple
import unicodedata
import urllib.parse

import docx
from docx.enum.table import WD_TABLE_ALIGNMENT
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement, parse_xml
from docx.oxml.ns import nsdecls, qn
from docx.shared import Mm, Pt, RGBColor
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY, TA_LEFT, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.platypus import HRFlowable, KeepTogether, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle
from sqlalchemy.orm import Session

from app.models.analysis_result import AnalysisResult
from app.models.article import Article
from app.models.document import Document
from app.models.enums import JenisAnalisa, ModeAnalisa
from app.schemas.catatan_dinas import CatatanDinasExportIn
from app.services.harmonisasi_export_service import (
    FOOTER_URD,
    _format_keyakinan,
    muat_data_harmonisasi_tersimpan,
)

logger = logging.getLogger("hero")

BULAN_INDONESIA = {
    1: "Januari",
    2: "Februari",
    3: "Maret",
    4: "April",
    5: "Mei",
    6: "Juni",
    7: "Juli",
    8: "Agustus",
    9: "September",
    10: "Oktober",
    11: "November",
    12: "Desember",
}

JENIS_LABEL_MAP = {
    "pasal_baru": "Baru",
    "baru": "Baru",
    "sama": "Sama",
    "menggantikan": "Menggantikan",
    "melengkapi": "Melengkapi",
    "konflik": "Konflik",
}


def format_tanggal_indonesia(d: date) -> str:
    """Format tanggal ke bahasa Indonesia, misal: 13 November 2026."""
    return f"{d.day} {BULAN_INDONESIA.get(d.month, str(d.month))} {d.year}"


def potong_teks_di_batas_kata(teks: Optional[str], batas: int = 300) -> str:
    """Memotong teks maksimal `batas` karakter pada batas kata dengan akhiran '…'."""
    if not teks:
        return ""
    teks = teks.strip()
    if len(teks) <= batas:
        return teks
    potongan = teks[:batas]
    last_space = potongan.rfind(" ")
    if last_space > 0:
        potongan = potongan[:last_space]
    return potongan.rstrip(".,;:- ") + "…"


def parse_pasal_sort_key(pasal_str: Optional[str]) -> Tuple[int, str]:
    """Sort key alami untuk penomoran pasal: Pasal 1, Pasal 2, ..., Pasal 10."""
    if not pasal_str:
        return (999999, "")
    m = re.search(r"\b(?:pasal\s*)?(\d+)", str(pasal_str), re.IGNORECASE)
    num = int(m.group(1)) if m else 999999
    return (num, str(pasal_str).lower())


def get_letter_label(idx: int) -> str:
    """Mengubah index 0..n menjadi huruf a., b., ..., z., aa., dst."""
    res = ""
    curr = idx
    while curr >= 0:
        res = chr(ord("a") + (curr % 26)) + res
        curr = (curr // 26) - 1
    return f"{res}."


def int_to_roman_lower(n: int) -> str:
    """Konversi bilangan bulat ke angka romawi kecil: 1 -> i, 2 -> ii, dst."""
    val = [1000, 900, 500, 400, 100, 90, 50, 40, 10, 9, 5, 4, 1]
    syb = ["m", "cm", "d", "cd", "c", "xc", "l", "xl", "x", "ix", "v", "iv", "i"]
    roman_num = ""
    i = 0
    while n > 0:
        for _ in range(n // val[i]):
            roman_num += syb[i]
            n -= val[i]
        i += 1
    return roman_num or "i"


@dataclass
class TemuanItem:
    label_jenis: str
    pembanding_str: Optional[str]
    alasan: str
    keyakinan_str: str
    penilaian_analis: str
    catatan_analis: Optional[str]


@dataclass
class PasalGroupItem:
    pasal_label: str  # misal: "a. Pasal 1"
    kutipan_paragraf: str  # misal: "Pasal 1 mengatur bahwa ..."
    temuan_items: List[TemuanItem]


@dataclass
class ButirItem:
    nomor: int
    judul_butir: str
    paragraf_utama: str
    pasal_groups: Optional[List[PasalGroupItem]] = None
    paragraf_penutup: Optional[str] = None


@dataclass
class CatatanDinasData:
    nomor_cd: str
    is_konsep: bool
    identitas_rows: List[Tuple[str, str]]
    kalimat_pembuka: str
    butir_items: List[ButirItem]
    kalimat_penutup: str
    penandatangan_jabatan: str
    penandatangan_nama: str
    penandatangan_nip: str
    footer_urd: str
    ai_footnote: Optional[str] = None


def generate_catatan_dinas_filename(doc: Document, ext: str) -> Tuple[str, str]:
    """
    Format nama berkas: catatan_dinas_<slug judul>_<id>.<ext>
    Mengembalikan (filename_ascii, filename_utf8).
    """
    title_part = doc.title or f"dokumen_{doc.id}"
    slug = re.sub(r'[\s/\\:*?"<>|]+', "_", title_part).strip("_")
    slug = slug[:50].rstrip("_")
    raw_name = f"catatan_dinas_{slug}_{doc.id}.{ext}"

    cleaned_utf8 = re.sub(r'[\s/\\:*?"<>|]+', "_", raw_name)
    cleaned_utf8 = re.sub(r"_+", "_", cleaned_utf8)

    norm_ascii = unicodedata.normalize("NFKD", raw_name).encode("ascii", "ignore").decode("ascii")
    cleaned_ascii = re.sub(r'[\s/\\:*?"<>|]+', "_", norm_ascii)
    cleaned_ascii = re.sub(r"_+", "_", cleaned_ascii)
    if not cleaned_ascii or cleaned_ascii == f".{ext}":
        cleaned_ascii = f"catatan_dinas_dokumen_{doc.id}.{ext}"

    return cleaned_ascii, cleaned_utf8


def _normalkan_narasi_ai(val: Any) -> Optional[str]:
    """
    Menormalkan nilai narasi AI menjadi teks string.
    Menerima str, list of str, atau list of dict (mengambil field 'kalimat').
    Abaikan item kosong atau bentuk lain. Bila data tidak dikenali atau kosong, kembalikan None.
    """
    if val is None:
        return None
    if isinstance(val, str):
        cleaned = val.strip()
        return cleaned if cleaned else None
    if isinstance(val, list):
        sentences: List[str] = []
        for item in val:
            if isinstance(item, str) and item.strip():
                sentences.append(item.strip())
            elif isinstance(item, dict):
                kalimat = item.get("kalimat")
                if isinstance(kalimat, str) and kalimat.strip():
                    sentences.append(kalimat.strip())
        if sentences:
            joined = " ".join(sentences).strip()
            return joined if joined else None
    return None


def _format_nama_pembanding(
    pembanding_obj: Optional[Dict[str, Any]],
    pasal_fallback: Optional[str] = None,
    allowed_ids: Optional[Set[int]] = None,
) -> Optional[str]:
    """
    Menyusun nama peraturan pembanding:
    - akses dibatasi: 'peraturan pembanding (akses dibatasi)'
    - ada judul dan nomor: '<judul> (Nomor <nomor>), <pasal>'
    - hanya judul: '<judul>, <pasal>'
    - hanya nomor: 'peraturan Nomor <nomor>, <pasal>'
    - tidak ada keduanya: 'peraturan pembanding' (+ ', <pasal>' bila ada)
    Jangan menampilkan pembanding.key (pengenal internal). Judul dipotong maks 200 karakter.
    """
    if pembanding_obj and isinstance(pembanding_obj, dict):
        p_doc_id = pembanding_obj.get("document_id")
        if allowed_ids is not None and isinstance(p_doc_id, int) and p_doc_id not in allowed_ids:
            return "peraturan pembanding (akses dibatasi)"
        if pembanding_obj.get("restricted") or pembanding_obj.get("akses_dibatasi"):
            return "peraturan pembanding (akses dibatasi)"

        judul_raw = pembanding_obj.get("judul")
        judul = potong_teks_di_batas_kata(str(judul_raw).strip(), 200) if judul_raw and str(judul_raw).strip() else None

        nomor_raw = pembanding_obj.get("nomor")
        nomor = str(nomor_raw).strip() if nomor_raw and str(nomor_raw).strip() else None

        pasal_raw = pembanding_obj.get("pasal") or pasal_fallback
        pasal = str(pasal_raw).strip() if pasal_raw and str(pasal_raw).strip() else None

        if judul and nomor:
            base = f"{judul} (Nomor {nomor})"
        elif judul:
            base = judul
        elif nomor:
            base = f"peraturan Nomor {nomor}"
        else:
            base = "peraturan pembanding"

        if pasal:
            return f"{base}, {pasal}"
        return base

    if pasal_fallback and str(pasal_fallback).strip():
        return f"peraturan pembanding, {str(pasal_fallback).strip()}"

    return None


def _get_butir_1_content(
    db: Session,
    doc: Document,
    pakai_ai: bool = False,
) -> Tuple[str, Optional[str], Optional[str]]:
    """
    Menyusun isi Butir 1 (Latar Belakang Regulasi).
    Mengembalikan: (teks_butir_1, ai_status, ai_footnote)
    ai_status bernilai "dipakai", "tidak_tersedia", atau None (bila pakai_ai=False).
    """
    jenis = doc.regulation_type or "Regulasi"
    judul = doc.title or f"Dokumen #{doc.id}"

    # 1. Cari data analisa tersimpan (kind=analisa) untuk identitas & kerangka
    analisa_cached = (
        db.query(AnalysisResult)
        .filter(
            AnalysisResult.document_id == doc.id,
            AnalysisResult.kind == JenisAnalisa.analisa,
        )
        .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
        .first()
    )

    jumlah_pasal: Optional[int] = None
    jumlah_bab: Optional[int] = None
    bab_titles: List[str] = []

    if analisa_cached and isinstance(analisa_cached.result, dict):
        res = analisa_cached.result
        identitas = res.get("identitas") if isinstance(res.get("identitas"), dict) else {}
        if identitas.get("jumlah_pasal") is not None:
            try:
                jumlah_pasal = int(identitas["jumlah_pasal"])
            except (ValueError, TypeError):
                pass

        kerangka = res.get("kerangka")
        if isinstance(kerangka, list) and kerangka:
            jumlah_bab = len(kerangka)
            # bab ke-2 s.d. ke-5 (index 1 to 4)
            bab_titles = [
                str(b.get("judul")).strip()
                for b in kerangka[1:5]
                if isinstance(b, dict) and b.get("judul") and str(b.get("judul")).strip()
            ]
            if not bab_titles:
                bab_titles = [
                    str(b.get("judul")).strip()
                    for b in kerangka[:4]
                    if isinstance(b, dict) and b.get("judul") and str(b.get("judul")).strip()
                ]

    # Fallback ke tabel articles bila belum didapat (urutkan mengikuti urutan pasal pertama tiap bab)
    if jumlah_pasal is None:
        count_art = db.query(Article).filter(Article.document_id == doc.id).count()
        if count_art > 0:
            jumlah_pasal = count_art

    if jumlah_bab is None:
        articles = (
            db.query(Article.chapter_title)
            .filter(Article.document_id == doc.id, Article.chapter_title.isnot(None))
            .order_by(Article.order_index.asc().nullslast(), Article.id.asc())
            .all()
        )
        ordered_chapters: List[str] = []
        seen_chapters = set()
        for (ch,) in articles:
            if ch and str(ch).strip():
                ch_clean = str(ch).strip()
                if ch_clean not in seen_chapters:
                    seen_chapters.add(ch_clean)
                    ordered_chapters.append(ch_clean)

        if ordered_chapters:
            jumlah_bab = len(ordered_chapters)
            if not bab_titles:
                bab_titles = ordered_chapters[1:5] if len(ordered_chapters) > 1 else ordered_chapters[:4]

    # Susun template bawaan
    if jumlah_bab and jumlah_pasal:
        if bab_titles:
            bab_str = ", ".join(bab_titles)
            template_text = (
                f"{jenis} tentang {judul} terdiri atas {jumlah_bab} bab dan {jumlah_pasal} pasal, "
                f"yang antara lain mengatur {bab_str}."
            )
        else:
            template_text = (
                f"{jenis} tentang {judul} terdiri atas {jumlah_bab} bab dan {jumlah_pasal} pasal."
            )
    elif jumlah_pasal:
        template_text = f"{jenis} tentang {judul} terdiri atas {jumlah_pasal} pasal."
    else:
        template_text = f"{jenis} tentang {judul} mengatur pokok-pokok ketentuan regulasi terkait."

    # 2. Bila pakai_ai=True: cari narasi AI yang tersimpan dan segar
    if pakai_ai:
        ai_cached = (
            db.query(AnalysisResult)
            .filter(
                AnalysisResult.document_id == doc.id,
                AnalysisResult.kind == JenisAnalisa.analisa,
                AnalysisResult.mode == ModeAnalisa.ai,
                AnalysisResult.usang_sejak.is_(None),
            )
            .order_by(AnalysisResult.created_at.desc(), AnalysisResult.id.desc())
            .first()
        )

        narasi_ai: Optional[str] = None
        if ai_cached and isinstance(ai_cached.result, dict):
            res_ai = ai_cached.result
            mode_dipakai = res_ai.get("mode_dipakai")
            ai_dict = res_ai.get("ai") if isinstance(res_ai.get("ai"), dict) else {}
            ai_status_field = ai_dict.get("status")

            # Narasi AI hanya dipakai jika AI benar-benar dipakai (bukan fallback deterministik)
            if mode_dipakai == "ai" or ai_status_field == "ai":
                if res_ai.get("ringkasan_ai") is not None:
                    narasi_ai = _normalkan_narasi_ai(res_ai["ringkasan_ai"])
                if not narasi_ai and ai_dict.get("ringkasan") is not None:
                    narasi_ai = _normalkan_narasi_ai(ai_dict["ringkasan"])

        if narasi_ai:
            footnote = "Butir 1 disusun dengan bantuan AI dari hasil analisa terverifikasi."
            return narasi_ai, "dipakai", footnote
        else:
            return template_text, "tidak_tersedia", None

    return template_text, None, None


def build_catatan_dinas_data(
    db: Session,
    doc: Document,
    payload: CatatanDinasExportIn,
    filtered_data: Dict[str, Any],
    allowed_ids: Optional[Set[int]] = None,
) -> Tuple[CatatanDinasData, Optional[str]]:
    """
    Membangun struktur antara (IR) Catatan Dinas dari model dokumen, isian form, dan temuan harmonisasi.
    Mengembalikan (catatan_dinas_data, ai_status).
    """
    judul_draf = doc.title or f"Dokumen #{doc.id}"

    # 1. Isian identitas dengan default
    nomor_cd = payload.nomor_cd or "CD-xx/…/xxxx"
    yth = payload.yth or "…"
    dari = payload.dari or "…"
    sifat = payload.sifat or "Biasa"
    lampiran = payload.lampiran or "-"
    hal = payload.hal or f"Tanggapan atas {judul_draf}"

    if payload.tanggal:
        tanggal_str = format_tanggal_indonesia(payload.tanggal)
    else:
        now_wib = datetime.now(timezone(timedelta(hours=7))).date()
        tanggal_str = format_tanggal_indonesia(now_wib)

    identitas_rows = [
        ("Yth.", yth),
        ("Dari", dari),
        ("Sifat", sifat),
        ("Lampiran", lampiran),
        ("Hal", hal),
        ("Tanggal", tanggal_str),
    ]

    unit_peminta = payload.unit_peminta or "…"
    nomor_nd = payload.nomor_nd or "ND-xx/…/xxxx"
    tanggal_nd_str = format_tanggal_indonesia(payload.tanggal_nd) if payload.tanggal_nd else "…"
    hal_nd = payload.hal_nd or "…"

    kalimat_pembuka = (
        f"Sehubungan dengan nota dinas {unit_peminta} nomor {nomor_nd} tanggal {tanggal_nd_str} "
        f"hal {hal_nd}, dapat kami sampaikan hal-hal sebagai berikut:"
    )

    # 2. Butir 1 (Latar belakang)
    butir_1_text, ai_status, ai_footnote = _get_butir_1_content(
        db=db,
        doc=doc,
        pakai_ai=bool(payload.pakai_ai),
    )

    # 3. Butir 2 (Riwayat permintaan)
    butir_2_text = (
        f"{unit_peminta} melalui nota dinas nomor {nomor_nd} tanggal {tanggal_nd_str} "
        f"meminta tanggapan atas {judul_draf}."
    )

    # 4. Butir 3 (Tanggapan: SEMUA temuan, dikelompokkan per pasal draf)
    raw_temuan = filtered_data.get("temuan") if isinstance(filtered_data.get("temuan"), list) else []

    # Sort temuan secara alami berdasarkan nomor pasal draf
    sorted_temuan = sorted(raw_temuan, key=lambda t: parse_pasal_sort_key(t.get("pasal_draft")))

    # Kelompokkan per pasal draf
    grouped_pasal: Dict[str, List[Dict[str, Any]]] = {}
    for t in sorted_temuan:
        p_key = str(t.get("pasal_draft") or "Ketentuan Umum").strip()
        grouped_pasal.setdefault(p_key, []).append(t)

    pasal_group_items: List[PasalGroupItem] = []
    pasal_idx = 0
    for p_key, t_list in grouped_pasal.items():
        letter_label = get_letter_label(pasal_idx)
        pasal_idx += 1

        # Ambil kutipan draft dari salah satu temuan
        kutipan_draft = ""
        for item in t_list:
            candidate = (
                item.get("kutipan_draft")
                or item.get("teks_draft")
                or item.get("draft_teks")
                or item.get("kutipan")
                or item.get("isi_pasal")
            )
            if candidate and str(candidate).strip():
                kutipan_draft = str(candidate).strip()
                break

        if kutipan_draft:
            kutipan_potong = potong_teks_di_batas_kata(kutipan_draft, 300)
            kutipan_paragraf = f"{letter_label} {p_key} mengatur bahwa {kutipan_potong}"
        else:
            kutipan_paragraf = f"{letter_label} {p_key} mengatur ketentuan terkait regulasi ini."

        # Rincian temuan per pasal
        temuan_sub_items: List[TemuanItem] = []
        for t in t_list:
            jenis_raw = str(t.get("jenis") or "temuan").lower().strip()
            label_jenis = JENIS_LABEL_MAP.get(jenis_raw, jenis_raw.capitalize())

            # Peraturan pembanding
            pembanding_obj = t.get("pembanding")
            pembanding_str = _format_nama_pembanding(
                pembanding_obj=pembanding_obj,
                pasal_fallback=t.get("pasal_pembanding"),
                allowed_ids=allowed_ids,
            )

            # Alasan
            alasan_raw = t.get("alasan") or t.get("deskripsi") or t.get("judul") or "-"
            alasan_potong = potong_teks_di_batas_kata(str(alasan_raw), 300)

            # Keyakinan
            keyakinan_str = _format_keyakinan(t.get("tingkat"), t.get("keyakinan"))

            # Penilaian analis
            tanggapan = t.get("tanggapan") if isinstance(t.get("tanggapan"), dict) else None
            catatan_analis: Optional[str] = None
            if tanggapan:
                pen_raw = str(tanggapan.get("penilaian") or "").lower().strip()
                if pen_raw == "valid":
                    penilaian_analis = "Valid"
                elif pen_raw in ("tidak_relevan", "tidak relevan"):
                    penilaian_analis = "Tidak Relevan"
                else:
                    penilaian_analis = "Belum dinilai"
                cat_val = tanggapan.get("catatan")
                if cat_val and str(cat_val).strip() and str(cat_val).strip() != "-":
                    catatan_analis = str(cat_val).strip()
            else:
                penilaian_analis = "Belum dinilai"

            temuan_sub_items.append(
                TemuanItem(
                    label_jenis=label_jenis,
                    pembanding_str=pembanding_str,
                    alasan=alasan_potong,
                    keyakinan_str=keyakinan_str,
                    penilaian_analis=penilaian_analis,
                    catatan_analis=catatan_analis,
                )
            )

        pasal_group_items.append(
            PasalGroupItem(
                pasal_label=f"{letter_label} {p_key}",
                kutipan_paragraf=kutipan_paragraf,
                temuan_items=temuan_sub_items,
            )
        )

    if pasal_group_items:
        butir_3_intro = "Tanggapan terhadap substansi draf regulasi hasil penelaahan adalah sebagai berikut:"
    else:
        butir_3_intro = "Berdasarkan hasil harmonisasi, tidak ditemukan adanya temuan disharmonisasi pada draf regulasi ini."

    # Cek apakah ada temuan yang disembunyikan karena pembatasan akses
    butir_3_penutup: Optional[str] = None
    disaring_count: Optional[int] = None
    rincian = filtered_data.get("disaring_rincian")
    if isinstance(rincian, dict) and isinstance(rincian.get("temuan"), int) and rincian["temuan"] > 0:
        disaring_count = rincian["temuan"]
    elif isinstance(filtered_data.get("ringkasan"), dict):
        ringkasan = filtered_data["ringkasan"]
        for k in ("temuan_disaring", "disaring_temuan", "temuan_tersembunyi", "jumlah_disaring"):
            if isinstance(ringkasan.get(k), int) and ringkasan[k] > 0:
                disaring_count = ringkasan[k]
                break
    if disaring_count is None and isinstance(filtered_data.get("disaring_backend"), int) and filtered_data["disaring_backend"] > 0:
        if not (isinstance(rincian, dict) and rincian.get("temuan") == 0):
            disaring_count = filtered_data["disaring_backend"]

    if disaring_count is not None and disaring_count > 0:
        butir_3_penutup = f"{disaring_count} temuan tidak ditampilkan karena pembandingnya tidak dapat diakses."

    # 5. Susun daftar ButirItem
    butir_list: List[ButirItem] = []
    # Butir 1
    butir_list.append(
        ButirItem(
            nomor=1,
            judul_butir="Latar Belakang Regulasi",
            paragraf_utama=butir_1_text,
        )
    )
    # Butir 2
    butir_list.append(
        ButirItem(
            nomor=2,
            judul_butir="Riwayat Permintaan Tanggapan",
            paragraf_utama=butir_2_text,
        )
    )
    # Butir 3
    butir_list.append(
        ButirItem(
            nomor=3,
            judul_butir="Tanggapan",
            paragraf_utama=butir_3_intro,
            pasal_groups=pasal_group_items,
            paragraf_penutup=butir_3_penutup,
        )
    )

    current_num = 4
    # Butir 4 (opsional: Catatan Tambahan)
    catatan_tambahan = payload.catatan_tambahan
    if catatan_tambahan and catatan_tambahan.strip():
        butir_list.append(
            ButirItem(
                nomor=current_num,
                judul_butir="Catatan Tambahan",
                paragraf_utama=catatan_tambahan.strip(),
            )
        )
        current_num += 1

    # Butir Penutup
    penutup_butir_text = "Apabila Bapak/Ibu sependapat, terlampir konsep nota dinas tanggapan untuk ditindaklanjuti."
    butir_list.append(
        ButirItem(
            nomor=current_num,
            judul_butir="Tindak Lanjut",
            paragraf_utama=penutup_butir_text,
        )
    )

    kalimat_penutup = "Demikian kami sampaikan, atas perhatian Bapak/Ibu kami ucapkan terima kasih."

    penandatangan_jabatan = payload.penandatangan_jabatan or "…"
    penandatangan_nama = payload.penandatangan_nama or "…"
    penandatangan_nip = payload.penandatangan_nip or "…"

    catatan_dinas = CatatanDinasData(
        nomor_cd=nomor_cd,
        is_konsep=True,
        identitas_rows=identitas_rows,
        kalimat_pembuka=kalimat_pembuka,
        butir_items=butir_list,
        kalimat_penutup=kalimat_penutup,
        penandatangan_jabatan=penandatangan_jabatan,
        penandatangan_nama=penandatangan_nama,
        penandatangan_nip=penandatangan_nip,
        footer_urd=FOOTER_URD,
        ai_footnote=ai_footnote,
    )

    return catatan_dinas, ai_status


# ==============================================================================
# PERENDER DOCX
# ==============================================================================


def _set_cell_border(cell: Any, **kwargs) -> None:
    """Helper untuk mengatur border sel tabel di python-docx."""
    tcPr = cell._tc.get_or_add_tcPr()
    tcBorders = OxmlElement("w:tcBorders")
    for border_name, border_props in kwargs.items():
        border = OxmlElement(f"w:{border_name}")
        for key, val in border_props.items():
            border.set(qn(f"w:{key}"), str(val))
        tcBorders.append(border)
    tcPr.append(tcBorders)


def render_catatan_dinas_docx(data: CatatanDinasData) -> bytes:
    """Membangun berkas DOCX Catatan Dinas menggunakan python-docx."""
    doc = docx.Document()

    # Pengaturan Halaman A4 dan Margin
    section = doc.sections[0]
    section.page_width = Mm(210)
    section.page_height = Mm(297)
    section.top_margin = Mm(25)
    section.bottom_margin = Mm(25)
    section.left_margin = Mm(25)
    section.right_margin = Mm(25)

    # Set font default ke Times New Roman
    style_normal = doc.styles["Normal"]
    style_normal.font.name = "Times New Roman"
    style_normal.font.size = Pt(11)
    style_normal.paragraph_format.line_spacing = 1.15
    style_normal.paragraph_format.space_after = Pt(4)

    # 1. Judul Tengah: CATATAN DINAS & NOMOR
    p_title = doc.add_paragraph()
    p_title.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_title.paragraph_format.space_after = Pt(2)
    run_title = p_title.add_run("CATATAN DINAS")
    run_title.bold = True
    run_title.font.size = Pt(14)

    p_nomor = doc.add_paragraph()
    p_nomor.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_nomor.paragraph_format.space_after = Pt(4)
    run_nomor = p_nomor.add_run(f"NOMOR {data.nomor_cd}")
    run_nomor.bold = True
    run_nomor.font.size = Pt(11)

    # Satu baris di bawah judul: label KONSEP
    p_konsep = doc.add_paragraph()
    p_konsep.alignment = WD_ALIGN_PARAGRAPH.CENTER
    p_konsep.paragraph_format.space_after = Pt(8)
    run_konsep = p_konsep.add_run(
        "KONSEP — dihasilkan sistem HERO sebagai Draft / Rekomendasi; belum ditandatangani."
    )
    run_konsep.italic = True
    run_konsep.font.size = Pt(8.5)
    run_konsep.font.color.rgb = RGBColor(100, 100, 100)

    # Garis pemisah horizontal (border bawah tipis via XML)
    p_hr = doc.add_paragraph()
    p_hr.paragraph_format.space_after = Pt(8)
    pPr = p_hr._p.get_or_add_pPr()
    pBdr = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                     r'<w:bottom w:val="single" w:sz="8" w:space="1" w:color="000000"/>'
                     r'</w:pBdr>')
    pPr.append(pBdr)

    # 2. Blok Identitas (Yth., Dari, Sifat, Lampiran, Hal, Tanggal)
    tbl_id = doc.add_table(rows=len(data.identitas_rows), cols=3)
    tbl_id.alignment = WD_TABLE_ALIGNMENT.CENTER
    tbl_id.autofit = False

    col_widths = [Mm(25), Mm(5), Mm(130)]
    for row_idx, (label, val) in enumerate(data.identitas_rows):
        row = tbl_id.rows[row_idx]
        # Kolom Label
        c0 = row.cells[0]
        c0.width = col_widths[0]
        p0 = c0.paragraphs[0]
        p0.paragraph_format.space_after = Pt(2)
        r0 = p0.add_run(label)
        r0.bold = True

        # Kolom Pemisah ":"
        c1 = row.cells[1]
        c1.width = col_widths[1]
        p1 = c1.paragraphs[0]
        p1.paragraph_format.space_after = Pt(2)
        p1.add_run(":")

        # Kolom Nilai
        c2 = row.cells[2]
        c2.width = col_widths[2]
        p2 = c2.paragraphs[0]
        p2.paragraph_format.space_after = Pt(2)
        p2.add_run(val)

    # Garis pemisah horizontal kedua di bawah identitas
    p_hr2 = doc.add_paragraph()
    p_hr2.paragraph_format.space_before = Pt(4)
    p_hr2.paragraph_format.space_after = Pt(10)
    pPr2 = p_hr2._p.get_or_add_pPr()
    pBdr2 = parse_xml(r'<w:pBdr xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
                      r'<w:bottom w:val="single" w:sz="6" w:space="1" w:color="000000"/>'
                      r'</w:pBdr>')
    pPr2.append(pBdr2)

    # 3. Kalimat Pembuka
    p_buka = doc.add_paragraph(data.kalimat_pembuka)
    p_buka.paragraph_format.space_after = Pt(8)
    p_buka.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 4. Butir Bernomor
    for butir in data.butir_items:
        p_butir = doc.add_paragraph()
        p_butir.paragraph_format.left_indent = Mm(7)
        p_butir.paragraph_format.first_line_indent = Mm(-7)
        p_butir.paragraph_format.space_after = Pt(6)
        p_butir.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

        run_num = p_butir.add_run(f"{butir.nomor}. ")
        run_num.bold = True
        p_butir.add_run(butir.paragraf_utama)

        # Jika ada kelompok pasal (Butir 3: Tanggapan)
        if butir.pasal_groups:
            for pg in butir.pasal_groups:
                p_pasal = doc.add_paragraph()
                p_pasal.paragraph_format.left_indent = Mm(14)
                p_pasal.paragraph_format.space_after = Pt(4)
                p_pasal.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
                p_pasal.add_run(pg.kutipan_paragraf)

                for t_idx, t in enumerate(pg.temuan_items, start=1):
                    p_temuan = doc.add_paragraph()
                    p_temuan.paragraph_format.left_indent = Mm(21)
                    p_temuan.paragraph_format.space_after = Pt(4)
                    p_temuan.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

                    roman_num = int_to_roman_lower(t_idx)
                    p_temuan.add_run(f"{roman_num}. ").bold = True

                    # Header temuan
                    if t.pembanding_str:
                        p_temuan.add_run(f"Temuan {t.label_jenis}").bold = True
                        p_temuan.add_run(f" terhadap {t.pembanding_str}.\n")
                    else:
                        p_temuan.add_run(f"Temuan {t.label_jenis}.\n").bold = True

                    # Uraian & Keyakinan
                    p_temuan.add_run(f"Uraian: {t.alasan} ")
                    p_temuan.add_run(f"(Keyakinan: {t.keyakinan_str}).\n")

                    # Penilaian analis
                    p_temuan.add_run("Penilaian analis: ").bold = True
                    p_temuan.add_run(t.penilaian_analis)
                    if t.catatan_analis:
                        p_temuan.add_run(f". Catatan analis: {t.catatan_analis}")

        if butir.paragraf_penutup:
            p_penutup = doc.add_paragraph()
            p_penutup.paragraph_format.left_indent = Mm(7)
            p_penutup.paragraph_format.space_before = Pt(4)
            p_penutup.paragraph_format.space_after = Pt(6)
            p_penutup.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY
            p_penutup.add_run(butir.paragraf_penutup)

    # 5. Kalimat Penutup
    p_tutup = doc.add_paragraph(data.kalimat_penutup)
    p_tutup.paragraph_format.space_before = Pt(8)
    p_tutup.paragraph_format.space_after = Pt(16)
    p_tutup.paragraph_format.alignment = WD_ALIGN_PARAGRAPH.JUSTIFY

    # 6. Blok Penandatangan (rata kanan)
    p_sign = doc.add_paragraph()
    p_sign.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    p_sign.paragraph_format.left_indent = Mm(90)
    p_sign.paragraph_format.space_after = Pt(2)
    p_sign.add_run(f"{data.penandatangan_jabatan}\n\n\n\n")

    run_nama = p_sign.add_run(f"{data.penandatangan_nama}\n")
    run_nama.bold = True
    if data.penandatangan_nip and data.penandatangan_nip != "-":
        p_sign.add_run(f"NIP {data.penandatangan_nip}")

    # 7. Catatan Kaki / Disclaimer (URD & AI Footnote)
    doc.add_paragraph()
    p_foot = doc.add_paragraph()
    p_foot.paragraph_format.space_before = Pt(12)
    p_foot.paragraph_format.space_after = Pt(2)
    run_foot = p_foot.add_run(data.footer_urd)
    run_foot.italic = True
    run_foot.font.size = Pt(8.5)
    run_foot.font.color.rgb = RGBColor(120, 120, 120)

    if data.ai_footnote:
        p_ai_foot = doc.add_paragraph()
        p_ai_foot.paragraph_format.space_after = Pt(2)
        run_ai = p_ai_foot.add_run(f"*{data.ai_footnote}")
        run_ai.italic = True
        run_ai.font.size = Pt(8.5)
        run_ai.font.color.rgb = RGBColor(100, 100, 100)

    buf = io.BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# PERENDER PDF (REPORTLAB)
# ==============================================================================


def render_catatan_dinas_pdf(data: CatatanDinasData) -> bytes:
    """Membangun berkas PDF Catatan Dinas menggunakan reportlab."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        leftMargin=25 * mm,
        rightMargin=25 * mm,
        topMargin=25 * mm,
        bottomMargin=25 * mm,
    )

    styles = getSampleStyleSheet()

    # Style standar serif Times-Roman
    style_title = ParagraphStyle(
        "CDTitle",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=14,
        leading=18,
        alignment=TA_CENTER,
        spaceAfter=2,
    )
    style_nomor = ParagraphStyle(
        "CDNomor",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=11,
        leading=15,
        alignment=TA_CENTER,
        spaceAfter=4,
    )
    style_konsep = ParagraphStyle(
        "CDKonsep",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=8.5,
        leading=11,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#555555"),
        spaceAfter=6,
    )
    style_body = ParagraphStyle(
        "CDBody",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    style_butir = ParagraphStyle(
        "CDButir",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        leftIndent=18,
        firstLineIndent=-18,
        alignment=TA_JUSTIFY,
        spaceAfter=6,
    )
    style_pasal = ParagraphStyle(
        "CDPasal",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        leftIndent=24,
        alignment=TA_JUSTIFY,
        spaceAfter=4,
    )
    style_temuan = ParagraphStyle(
        "CDTemuan",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10,
        leading=13.5,
        leftIndent=40,
        alignment=TA_JUSTIFY,
        spaceAfter=5,
    )
    style_sign = ParagraphStyle(
        "CDSign",
        parent=styles["Normal"],
        fontName="Times-Roman",
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
    )
    style_sign_bold = ParagraphStyle(
        "CDSignBold",
        parent=styles["Normal"],
        fontName="Times-Bold",
        fontSize=10.5,
        leading=14,
        alignment=TA_LEFT,
    )
    style_foot = ParagraphStyle(
        "CDFoot",
        parent=styles["Normal"],
        fontName="Times-Italic",
        fontSize=8.5,
        leading=11,
        textColor=colors.HexColor("#777777"),
        spaceAfter=2,
    )

    story: List[Any] = []

    # 1. Judul Tengah & Nomor & Konsep
    story.append(Paragraph("CATATAN DINAS", style_title))
    story.append(Paragraph(f"NOMOR {html.escape(data.nomor_cd)}", style_nomor))
    story.append(
        Paragraph(
            "KONSEP — dihasilkan sistem HERO sebagai Draft / Rekomendasi; belum ditandatangani.",
            style_konsep,
        )
    )
    story.append(HRFlowable(width="100%", thickness=1, color=colors.black, spaceAfter=8))

    # 2. Blok Identitas (Tabel 3 kolom)
    table_data = []
    style_id_lbl = ParagraphStyle("IdLbl", fontName="Times-Bold", fontSize=10.5, leading=13)
    style_id_sep = ParagraphStyle("IdSep", fontName="Times-Roman", fontSize=10.5, leading=13)
    style_id_val = ParagraphStyle("IdVal", fontName="Times-Roman", fontSize=10.5, leading=13)

    for label, val in data.identitas_rows:
        table_data.append(
            [
                Paragraph(html.escape(label), style_id_lbl),
                Paragraph(":", style_id_sep),
                Paragraph(html.escape(val), style_id_val),
            ]
        )

    tbl_id = Table(table_data, colWidths=[25 * mm, 4 * mm, 131 * mm])
    tbl_id.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("TOPPADDING", (0, 0), (-1, -1), 1),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 1),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(tbl_id)
    story.append(HRFlowable(width="100%", thickness=0.8, color=colors.black, spaceBefore=6, spaceAfter=8))

    # 3. Kalimat Pembuka
    story.append(Paragraph(html.escape(data.kalimat_pembuka), style_body))

    # 4. Butir Bernomor
    for butir in data.butir_items:
        escaped_utama = html.escape(butir.paragraf_utama).replace("\r\n", "<br/>").replace("\n", "<br/>")
        text_b = f"<b>{butir.nomor}.</b> {escaped_utama}"
        story.append(Paragraph(text_b, style_butir))

        if butir.pasal_groups:
            for pg in butir.pasal_groups:
                story.append(Paragraph(html.escape(pg.kutipan_paragraf), style_pasal))

                for t_idx, t in enumerate(pg.temuan_items, start=1):
                    roman_num = int_to_roman_lower(t_idx)

                    # Susun teks temuan
                    parts_t = []
                    if t.pembanding_str:
                        parts_t.append(
                            f"<b>{roman_num}. Temuan {html.escape(t.label_jenis)}</b> "
                            f"terhadap {html.escape(t.pembanding_str)}.<br/>"
                        )
                    else:
                        parts_t.append(
                            f"<b>{roman_num}. Temuan {html.escape(t.label_jenis)}.</b><br/>"
                        )

                    parts_t.append(
                        f"Uraian: {html.escape(t.alasan)} "
                        f"(Keyakinan: {html.escape(t.keyakinan_str)}).<br/>"
                    )

                    pen_str = f"<b>Penilaian analis:</b> {html.escape(t.penilaian_analis)}"
                    if t.catatan_analis:
                        pen_str += f". Catatan analis: {html.escape(t.catatan_analis)}"
                    parts_t.append(pen_str)

                    story.append(Paragraph("".join(parts_t), style_temuan))

        if butir.paragraf_penutup:
            escaped_penutup = html.escape(butir.paragraf_penutup).replace("\r\n", "<br/>").replace("\n", "<br/>")
            story.append(Paragraph(escaped_penutup, style_butir))

    # 5. Kalimat Penutup
    story.append(Spacer(1, 4))
    story.append(Paragraph(html.escape(data.kalimat_penutup), style_body))
    story.append(Spacer(1, 12))

    # 6. Blok Penandatangan (Tabel 2 kolom, rata kanan)
    sign_cells = [
        Paragraph(html.escape(data.penandatangan_jabatan), style_sign),
        Spacer(1, 35),
        Paragraph(html.escape(data.penandatangan_nama), style_sign_bold),
    ]
    if data.penandatangan_nip and data.penandatangan_nip != "-":
        sign_cells.append(Paragraph(f"NIP {html.escape(data.penandatangan_nip)}", style_sign))

    sign_flowables = [
        Paragraph(html.escape(data.penandatangan_jabatan), style_sign),
        Spacer(1, 30),
        Paragraph(html.escape(data.penandatangan_nama), style_sign_bold),
    ]
    if data.penandatangan_nip and data.penandatangan_nip != "-":
        sign_flowables.append(Paragraph(f"NIP {html.escape(data.penandatangan_nip)}", style_sign))

    tbl_sign = Table(
        [
            ["", sign_flowables],
        ],
        colWidths=[80 * mm, 80 * mm],
    )
    tbl_sign.setStyle(
        TableStyle(
            [
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 0),
                ("RIGHTPADDING", (0, 0), (-1, -1), 0),
                ("TOPPADDING", (0, 0), (-1, -1), 0),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 0),
            ]
        )
    )
    story.append(KeepTogether(tbl_sign))

    # 7. Disclaimer & Catatan Kaki
    story.append(Spacer(1, 20))
    story.append(Paragraph(html.escape(data.footer_urd), style_foot))
    if data.ai_footnote:
        story.append(Paragraph(f"*{html.escape(data.ai_footnote)}", style_foot))

    doc.build(story)
    buf.seek(0)
    return buf.getvalue()


# ==============================================================================
# ENTRY POINT LAYANAN EKSPOR CATATAN DINAS
# ==============================================================================


def export_catatan_dinas(
    db: Session,
    doc: Document,
    payload: CatatanDinasExportIn,
    current_user: Optional[Any] = None,
    allowed_ids: Optional[Set[int]] = None,
    saring_rujukan_lengkap_fn: Optional[Any] = None,
    sesuaikan_ringkasan_harmonisasi_fn: Optional[Any] = None,
) -> Tuple[bytes, str, Dict[str, str], int, Optional[str]]:
    """
    Mengambil data harmonisasi tersimpan, menyaring rujukan, menyusun struktur antara Catatan Dinas,
    dan merender berkas keluaran sesuai format (DOCX atau PDF).

    Returns:
        (content_bytes, media_type, headers, temuan_count, ai_status)
    """
    # 1. Ambil data harmonisasi tersimpan lewat fungsi pembantu bersama
    filtered_data, actual_mode, dibuat_at, resolved_run_id = muat_data_harmonisasi_tersimpan(
        db=db,
        doc=doc,
        run_id=payload.run_id,
        allowed_ids=allowed_ids,
        saring_rujukan_lengkap_fn=saring_rujukan_lengkap_fn,
        sesuaikan_ringkasan_harmonisasi_fn=sesuaikan_ringkasan_harmonisasi_fn,
    )

    temuan_count = len(filtered_data.get("temuan", [])) if isinstance(filtered_data.get("temuan"), list) else 0

    # 2. Bangun struktur antara Catatan Dinas
    catatan_dinas_data, ai_status = build_catatan_dinas_data(
        db=db,
        doc=doc,
        payload=payload,
        filtered_data=filtered_data,
        allowed_ids=allowed_ids,
    )

    # 3. Generate nama berkas sesuai konvensi RFC 5987
    fmt = (payload.format or "docx").lower().strip()
    ascii_name, utf8_name = generate_catatan_dinas_filename(doc, fmt)
    encoded_utf8 = urllib.parse.quote(utf8_name)
    content_disp = f'attachment; filename="{ascii_name}"; filename*=UTF-8\'\'{encoded_utf8}'

    # 4. Render berkas sesuai format
    if fmt == "docx":
        content_bytes = render_catatan_dinas_docx(catatan_dinas_data)
        media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    elif fmt == "pdf":
        content_bytes = render_catatan_dinas_pdf(catatan_dinas_data)
        media_type = "application/pdf"
    else:
        raise ValueError(f"Format '{fmt}' tidak didukung. Pilihan format: docx, pdf.")

    headers = {
        "Content-Disposition": content_disp,
        "Content-Type": media_type,
    }

    # Header status AI jika pakai_ai diminta
    if payload.pakai_ai:
        headers["X-Catatan-Dinas-AI"] = ai_status or "tidak_tersedia"

    return content_bytes, media_type, headers, temuan_count, ai_status

