"""
app/services/kemiripan_service.py
Layanan Kemiripan Draft Berulang dan Perbandingan Per Pasal (Langkah 30).
"""
import re
import zlib
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import func
from sqlalchemy.orm import Session

from app.config import settings
from app.core.permissions import boleh_baca_nonpublik
from app.models.article import Article
from app.models.document import Document
from app.models.enums import KlasifikasiAkses, PeranDokumen

# Pola baris nomor halaman yang berdiri sendiri (misal: "1", "- 1 -", "Halaman 12", "Halaman 1 dari 25", "hal. 3", "Page 4")
PAGE_NUM_PATTERN = re.compile(
    r"^\s*(?:[-—_~*\[\]()]+\s*)?(?:halaman|hal\.?|hlm\.?|page)?\s*\d+(?:\s*(?:dari|of)\s*\d+)?\s*(?:[-—_~*\[\]()]+\s*)?$",
    re.IGNORECASE,
)


def normalisasi(teks: Optional[str]) -> str:
    """
    Normalisasi teks untuk perbandingan kemiripan:
    - Lowercase
    - Buang nomor halaman yang berdiri sendiri
    - Hapus tanda baca (ganti dengan spasi)
    - Rapikan spasi berlebih
    """
    if not teks:
        return ""

    # 1. Buang baris nomor halaman berdiri sendiri
    baris_bersih = []
    for line in teks.splitlines():
        if PAGE_NUM_PATTERN.match(line.strip()):
            continue
        baris_bersih.append(line)
    teks_gabung = " ".join(baris_bersih)

    # 2. Lowercase
    teks_lower = teks_gabung.lower()

    # 3. Hapus tanda baca (ganti karakter non-alfanumerik/non-spasi dan underscore dengan spasi)
    teks_nopunct = re.sub(r"[^\w\s]|_", " ", teks_lower)

    # 4. Rapikan spasi
    return re.sub(r"\s+", " ", teks_nopunct).strip()


def shingle(teks: str, k: int = 5) -> set[int]:
    """
    Membentuk himpunan hash int (zlib.crc32) dari k-gram kata (default 5-gram).
    Hemat memori dibanding menyimpan string gram mentah.
    Bila teks sangat pendek (kurang dari k kata), bandingkan sebagai himpunan kata.
    """
    norm = normalisasi(teks)
    if not norm:
        return set()

    words = norm.split()
    if not words:
        return set()

    if len(words) < k:
        # Teks sangat pendek -> himpunan kata
        return {zlib.crc32(w.encode("utf-8")) for w in words}

    shingles: set[int] = set()
    for i in range(len(words) - k + 1):
        gram = " ".join(words[i : i + k])
        shingles.add(zlib.crc32(gram.encode("utf-8")))
    return shingles


def persen_kemiripan(a: str, b: str, k: int = 5) -> float:
    """
    Menghitung persentase kemiripan Jaccard antara teks A dan B:
    |A ∩ B| / |A ∪ B| * 100, dibulatkan 1 desimal.
    Dua teks kosong -> 0.0.
    """
    if not a or not b:
        return 0.0

    shingle_a = shingle(a, k=k)
    shingle_b = shingle(b, k=k)

    if not shingle_a or not shingle_b:
        return 0.0

    irisan = len(shingle_a & shingle_b)
    gabungan = len(shingle_a | shingle_b)
    if gabungan == 0:
        return 0.0

    return round((irisan / gabungan) * 100.0, 1)


def batas_atas_cepat(len_a: int, len_b: int) -> float:
    """
    Menghitung batas atas teoritis kemiripan:
    min(|A|, |B|) / max(|A|, |B|) * 100.
    Bila batas ini kurang dari ambang, lewati perhitungan penuh Jaccard.
    """
    if len_a <= 0 or len_b <= 0:
        return 0.0
    return (min(len_a, len_b) / max(len_a, len_b)) * 100.0


# Margin batas atas cepat (10 poin persentase) untuk mengantisipasi perbedaan
# panjang karakter mentah akibat elemen non-substantif (seperti nomor halaman,
# header/footer berulang, dan spasi OCR) yang dibersihkan saat normalisasi teks.
MARGIN_BATAS_ATAS: float = 10.0


def banding_pasal(
    db: Session, draft_baru_id: int, draft_lama_id: int
) -> tuple[Optional[dict], Optional[str]]:
    """
    Membandingkan pasal antara dua draft kajian menggunakan tabel articles:
    - Hanya pasal tingkat atas (parent_id IS NULL)
    - Status: sama, berubah (dengan persen), baru, dihapus
    - Diurutkan menurut urutan pasal (order_index dan nomor pasal)
    - Bila salah satu draft belum punya articles, kembalikan (None, catatan).
    """
    arts_baru = (
        db.query(Article)
        .filter(Article.document_id == draft_baru_id, Article.parent_id.is_(None))
        .order_by(Article.order_index.asc().nulls_last(), Article.id.asc())
        .all()
    )
    arts_lama = (
        db.query(Article)
        .filter(Article.document_id == draft_lama_id, Article.parent_id.is_(None))
        .order_by(Article.order_index.asc().nulls_last(), Article.id.asc())
        .all()
    )

    if not arts_baru or not arts_lama:
        return None, "perbandingan per pasal belum tersedia (pasal belum dipecah)"

    map_baru: dict[str, Article] = {a.article_number.strip(): a for a in arts_baru}
    map_lama: dict[str, Article] = {a.article_number.strip(): a for a in arts_lama}

    semua_nomor = list(
        dict.fromkeys(
            [a.article_number.strip() for a in arts_baru]
            + [a.article_number.strip() for a in arts_lama]
        )
    )

    def sort_key(nomor: str):
        art_b = map_baru.get(nomor)
        art_l = map_lama.get(nomor)
        idx = (
            art_b.order_index
            if (art_b and art_b.order_index is not None)
            else (art_l.order_index if (art_l and art_l.order_index is not None) else None)
        )
        match = re.search(r"\d+", nomor)
        num = int(match.group()) if match else (idx if idx is not None else 999999)
        suffix = ""
        if match:
            rest = nomor[match.end() :].strip()
            m_suf = re.match(r"^[A-Za-z]+", rest)
            if m_suf:
                suffix = m_suf.group().upper()
        return (num, suffix, idx if idx is not None else 999999, nomor)

    semua_nomor.sort(key=sort_key)

    daftar_pasal = []
    for nomor in semua_nomor:
        art_b = map_baru.get(nomor)
        art_l = map_lama.get(nomor)
        if art_b and not art_l:
            daftar_pasal.append({
                "pasal": nomor,
                "status": "baru",
            })
        elif art_l and not art_b:
            daftar_pasal.append({
                "pasal": nomor,
                "status": "dihapus",
            })
        else:
            # Keduanya ada
            assert art_b is not None and art_l is not None
            norm_b = normalisasi(art_b.content_text)
            norm_l = normalisasi(art_l.content_text)
            if norm_b == norm_l:
                daftar_pasal.append({
                    "pasal": nomor,
                    "status": "sama",
                })
            else:
                persen = persen_kemiripan(art_b.content_text, art_l.content_text)
                daftar_pasal.append({
                    "pasal": nomor,
                    "status": "berubah",
                    "persen": persen,
                })

    ringkas = {
        "sama": sum(1 for p in daftar_pasal if p["status"] == "sama"),
        "berubah": sum(1 for p in daftar_pasal if p["status"] == "berubah"),
        "baru": sum(1 for p in daftar_pasal if p["status"] == "baru"),
        "dihapus": sum(1 for p in daftar_pasal if p["status"] == "dihapus"),
    }

    hasil = {
        "dibanding_dengan": draft_lama_id,
        "ringkas": ringkas,
        "pasal": daftar_pasal,
    }
    return hasil, None


def cari_kemiripan_draft(
    db: Session,
    doc: Document,
    user: Optional[Any] = None,
    ambang: Optional[float] = None,
    limit: int = 5,
) -> dict:
    """
    Menemukan draft-draft kajian lain yang mirip dengan dokumen draft target.
    Memfilter kandidat berdasarkan akses pengguna dan efisiensi query ringan.
    """
    if ambang is None:
        ambang = float(settings.draft_kemiripan_ambang)

    # 1. Query ringan metadata kandidat (tanpa full_text)
    query = (
        db.query(
            Document.id,
            Document.title,
            Document.created_at,
            func.length(Document.full_text).label("teks_len"),
        )
        .filter(
            Document.id != doc.id,
            Document.is_active == True,  # noqa: E712
            Document.document_role == PeranDokumen.draft_kajian,
            Document.full_text.isnot(None),
            Document.full_text != "",
        )
    )

    if not boleh_baca_nonpublik(user):
        query = query.filter(Document.access_classification == KlasifikasiAkses.publik)

    # Maksimal 200 terbaru menurut created_at
    candidates = query.order_by(Document.created_at.desc(), Document.id.desc()).limit(200).all()

    dibandingkan = len(candidates)
    doc_text = doc.full_text or ""
    doc_len = len(doc_text)

    draft_mirip_list: list[dict] = []
    terdekat_cand: Optional[int] = None
    terdekat_persen: float = -1.0
    dihitung_penuh_count: int = 0
    kandidat_tertinggi_batas: Optional[tuple[float, int, Any]] = None

    for cand in candidates:
        cand_id = cand.id
        cand_len = cand.teks_len or 0

        # Evaluasi batas atas cepat sebelum mengambil teks.
        # Lewati perhitungan penuh hanya bila batas < ambang - MARGIN_BATAS_ATAS.
        batas = batas_atas_cepat(doc_len, cand_len)
        if batas < ambang - MARGIN_BATAS_ATAS:
            if kandidat_tertinggi_batas is None or batas > kandidat_tertinggi_batas[0]:
                kandidat_tertinggi_batas = (batas, cand_id, cand)
            continue

        # Ambil full_text kandidat dari DB untuk perhitungan penuh
        cand_row = db.query(Document.full_text).filter(Document.id == cand_id).first()
        if not cand_row or not cand_row[0]:
            continue
        cand_text = cand_row[0]

        persen = persen_kemiripan(doc_text, cand_text)
        dihitung_penuh_count += 1

        if persen > terdekat_persen:
            terdekat_persen = persen
            terdekat_cand = cand_id

        if persen >= ambang:
            status_str = "identik" if persen >= 99.5 else "sangat_mirip"
            created_val = cand.created_at
            if isinstance(created_val, datetime):
                diunggah_str = created_val.isoformat()
            else:
                diunggah_str = str(created_val) if created_val else None

            draft_mirip_list.append({
                "document_id": cand_id,
                "judul": cand.title or "",
                "diunggah": diunggah_str,
                "persen": persen,
                "status": status_str,
            })

    # Bila tidak ada satu pun kandidat yang dihitung penuh (semuanya dilewati),
    # hitung penuh untuk satu kandidat dengan batas atas tertinggi sebagai 'terdekat'.
    if dihitung_penuh_count == 0 and kandidat_tertinggi_batas is not None:
        batas, best_cand_id, best_cand = kandidat_tertinggi_batas
        cand_row = db.query(Document.full_text).filter(Document.id == best_cand_id).first()
        if cand_row and cand_row[0]:
            cand_text = cand_row[0]
            persen = persen_kemiripan(doc_text, cand_text)
            terdekat_persen = persen
            terdekat_cand = best_cand_id
            if persen >= ambang:
                status_str = "identik" if persen >= 99.5 else "sangat_mirip"
                created_val = best_cand.created_at
                if isinstance(created_val, datetime):
                    diunggah_str = created_val.isoformat()
                else:
                    diunggah_str = str(created_val) if created_val else None

                draft_mirip_list.append({
                    "document_id": best_cand_id,
                    "judul": best_cand.title or "",
                    "diunggah": diunggah_str,
                    "persen": persen,
                    "status": status_str,
                })

    # Urutkan draft mirip menurun berdasarkan persen
    draft_mirip_list.sort(key=lambda x: x["persen"], reverse=True)
    draft_mirip_terpilih = draft_mirip_list[:limit]

    terdekat = None
    if terdekat_cand is not None and terdekat_persen >= 0:
        terdekat = {
            "document_id": terdekat_cand,
            "persen": terdekat_persen,
        }

    per_pasal = None
    catatan = None

    if terdekat and terdekat["persen"] >= ambang:
        per_pasal_hasil, per_pasal_catatan = banding_pasal(db, doc.id, terdekat["document_id"])
        per_pasal = per_pasal_hasil
        catatan = per_pasal_catatan

    return {
        "document_id": doc.id,
        "ambang": ambang,
        "dibandingkan": dibandingkan,
        "draft_mirip": draft_mirip_terpilih,
        "terdekat": terdekat,
        "per_pasal": per_pasal,
        "catatan": catatan,
    }

