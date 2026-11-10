"""
app/services/metadata_extraction_service.py
Layanan ekstraksi metadata otomatis dari naskah PDF regulasi (Judul, Nomor, Jenis, Bidang, Tanggal).
Mendukung regulasi OJK (POJK, SEOJK, PDK, SEDK) dan peraturan perundang-undangan Indonesia (UU, PP, Perpres, PBI, dll).
"""
import io
import re
from datetime import date
from typing import Any, Dict, Optional, Tuple
from pypdf import PdfReader

# Kamus nama bulan Indonesia ke angka
MONTHS_ID = {
    "januari": 1, "februari": 2, "pebruari": 2, "maret": 3, "april": 4,
    "mei": 5, "juni": 6, "juli": 7, "agustus": 8, "september": 9,
    "oktober": 10, "november": 11, "nopember": 11, "desember": 12,
    "january": 1, "february": 2, "march": 3, "april": 4, "may": 5,
    "june": 6, "july": 7, "august": 8, "september": 9, "october": 10,
    "december": 12,
}

# Pola regex jenis regulasi (prioritas dari terpanjang)
REGULATION_TYPE_PATTERNS = [
    (r"SURAT\s+EDARAN\s+(?:OTORITAS\s+JASA\s+KEUANGAN|OJK)", "SEOJK"),
    (r"PERATURAN\s+ANGGOTA\s+DEWAN\s+KOMISIONER", "PADK"),
    (r"PERATURAN\s+DEWAN\s+KOMISIONER", "PDK"),
    (r"SURAT\s+EDARAN\s+DEWAN\s+KOMISIONER", "SEDK"),
    (r"KEPUTUSAN\s+(?:ANGGOTA\s+)?DEWAN\s+KOMISIONER", "KEPDK"),
    (r"PERATURAN\s+(?:OTORITAS\s+JASA\s+KEUANGAN|OJK)", "POJK"),
    (r"PERATURAN\s+BANK\s+INDONESIA", "PBI"),
    (r"SURAT\s+EDARAN\s+BANK\s+INDONESIA", "SEBI"),
    (r"PERATURAN\s+PEMERINTAH\s+PENGGANTI\s+UNDANG[-\s]?UNDANG", "PERPPU"),
    (r"PERATURAN\s+PEMERINTAH", "PP"),
    (r"PERATURAN\s+PRESIDEN", "PERPRES"),
    (r"UNDANG[-\s]?UNDANG\s+REPUBLIK\s+INDONESIA", "UU"),
    (r"\bUNDANG[-\s]?UNDANG\b", "UU"),
    (r"PERATURAN\s+MENTERI\s+KEUANGAN", "PMK"),
    (r"PERATURAN\s+MENTERI", "PERMEN"),
    (r"PERATURAN\s+DAERAH", "PERDA"),
]

# Pola nomor regulasi
RE_NUMBER_SLASH = re.compile(
    r"(?:NOMOR|NO\.?)\s*[:.]?\s*([0-9]{1,4}(?:\s*/\s*[A-Za-z0-9.\-]{1,25}){1,4})",
    re.IGNORECASE,
)
RE_NUMBER_TAHUN = re.compile(
    r"(?:NOMOR|NO\.?)\s*[:.]?\s*([0-9]{1,4})\s+(?:TAHUN|YEAR)\s+((?:19|20)\d{2})",
    re.IGNORECASE,
)
RE_BARE_SLASH = re.compile(
    r"\b([0-9]{1,4}\s*/\s*(?:POJK|SEOJK|PBI|PADK|PADG|SEBI|PMK|PDK|SEDK)[A-Za-z0-9.\-]*\s*/\s*(?:19|20)\d{2})\b",
    re.IGNORECASE,
)

# Pola klausul TENTANG
RE_TENTANG = re.compile(r"\b(?:TENTANG|CONCERNING)\b\s*[:\-]?\s*", re.IGNORECASE)

# Pola penanda tanggal penetapan/pengundangan
RE_TANGGAL_DITETAPKAN = re.compile(
    r"(?:ditetapkan|diundangkan|ditandatangani)[\s\S]{0,100}?pada\s+tanggal\s+(\d{1,2})\s+([a-zA-Z]+)\s+((?:19|20)\d{2})",
    re.IGNORECASE,
)


def _extract_pdf_text_sample(content: bytes, max_pages: int = 5) -> Tuple[str, str, int]:
    """
    Membaca teks dari naskah PDF secara cepat dalam memori:
    - Halaman 1 sampai maksimal 5 (untuk judul, jenis, nomor, sektor)
    - Halaman terakhir reader.pages[-1] jika total_pages > max_pages (untuk klausul tanggal penetapan)
    Mengembalikan tuple: (head_text, full_sample_text, total_pages).
    """
    try:
        reader = PdfReader(io.BytesIO(content))
        total_pages = len(reader.pages)
        if total_pages == 0:
            return "", "", 0

        pages_to_read = min(total_pages, max_pages)
        text_chunks = []
        for i in range(pages_to_read):
            page_text = reader.pages[i].extract_text() or ""
            text_chunks.append(page_text)

        head_text = "\n".join(text_chunks)

        # Bila dokumen memiliki lebih dari max_pages, sertakan halaman terakhir untuk tanggal penetapan
        if total_pages > max_pages:
            last_page_text = reader.pages[-1].extract_text() or ""
            full_sample_text = head_text + "\n" + last_page_text
        else:
            full_sample_text = head_text

        return head_text, full_sample_text, total_pages
    except Exception:
        return "", "", 0


def _extract_header_text(text: str) -> str:
    """
    Mengambil teks kepala dokumen (sebelum klausul TENTANG atau pembukaan formal)
    agar pencarian jenis dan nomor regulasi tidak salah mengambil kutipan dalam konsiderans Mengingat.
    """
    m_tentang = RE_TENTANG.search(text[:3500])
    if m_tentang:
        return text[:m_tentang.start()]

    m_pembuka = re.search(
        r"\b(?:DENGAN\s+RAHMAT|MENIMBANG|MENGINGAT|MEMUTUSKAN)\b",
        text[:3500],
        re.IGNORECASE,
    )
    if m_pembuka:
        return text[:m_pembuka.start()]

    return text[:1000]


def _detect_type(text: str, filename: Optional[str] = None) -> Optional[str]:
    """
    Mendeteksi jenis regulasi.
    Prioritas:
    1. Teks kepala regulasi (sebelum klausul TENTANG / Mengingat)
    2. Teks pembuka (1000 karakter pertama)
    3. Nama berkas
    """
    header = _extract_header_text(text)
    if header.strip():
        for pattern, code in REGULATION_TYPE_PATTERNS:
            if re.search(pattern, header, re.IGNORECASE):
                return code

    # Fallback jika kepala dokumen tidak eksplisit
    for pattern, code in REGULATION_TYPE_PATTERNS:
        if re.search(pattern, text[:1000], re.IGNORECASE):
            return code

    if filename:
        fn = filename.upper().replace("_", " ").replace("-", " ")
        for pattern, code in REGULATION_TYPE_PATTERNS:
            if re.search(pattern, fn, re.IGNORECASE):
                return code
        # Singkatan umum di nama berkas
        if re.search(r"\bPOJK\b", fn):
            return "POJK"
        if re.search(r"\bSEOJK\b", fn):
            return "SEOJK"
        if re.search(r"\bPDK\b", fn):
            return "PDK"
        if re.search(r"\bUU\b", fn):
            return "UU"
        if re.search(r"\bPP\b", fn):
            return "PP"
        if re.search(r"\bPBI\b", fn):
            return "PBI"
    return None


def _detect_number(text: str, filename: Optional[str] = None) -> Optional[str]:
    """
    Mengekstrak nomor regulasi.
    Prioritas pencarian berada pada teks kepala dokumen (sebelum TENTANG)
    untuk mencegah salah tangkap nomor regulasi lain yang dikutip dalam konsiderans Mengingat.
    Mengambil kemunculan pertama (m[0]) pada bagian kepala.
    """
    header = _extract_header_text(text)
    search_targets = [header] if header.strip() else []
    search_targets.append(text[:2500])

    for target in search_targets:
        # 1. Pola slash (e.g. 12/POJK.03/2024)
        m_slash = list(RE_NUMBER_SLASH.finditer(target))
        if m_slash:
            raw = m_slash[0].group(1)
            return re.sub(r"\s+", "", raw).strip(" ./-")

        # 2. Pola tahun (e.g. Nomor 12 Tahun 2024)
        m_tahun = list(RE_NUMBER_TAHUN.finditer(target))
        if m_tahun:
            n, y = m_tahun[0].groups()
            return f"{n} Tahun {y}"

        # 3. Pola bare slash
        m_bare = RE_BARE_SLASH.search(target)
        if m_bare:
            raw = m_bare.group(1)
            return re.sub(r"\s+", "", raw).strip(" ./-")

    # 4. Fallback dari nama berkas jika teks awal tidak memuat nomor
    if filename:
        fn_slash = RE_NUMBER_SLASH.search(filename.replace("_", "/"))
        if fn_slash:
            return re.sub(r"\s+", "", fn_slash.group(1)).strip(" ./-")
        fn_bare = RE_BARE_SLASH.search(filename.replace("_", "/"))
        if fn_bare:
            return re.sub(r"\s+", "", fn_bare.group(1)).strip(" ./-")

    return None


def _detect_title(text: str, filename: Optional[str] = None) -> Optional[str]:
    """Mengekstrak judul regulasi (klausa setelah kata TENTANG)."""
    m = RE_TENTANG.search(text[:3500])
    if m:
        tail = text[m.end() : m.end() + 700]
        lines = []
        for raw in tail.split("\n"):
            line = raw.strip()
            if not line:
                if lines:
                    break
                continue
            # Penanda batas akhir perihal judul regulasi
            if re.match(
                r"^(?:DENGAN\s+RAHMAT|MENIMBANG|MENGINGAT|MEMUTUSKAN|BAB\s+[IVXLCDM0-9]+|PASAL\s+\d+|DEWAN\s+KOMISIONER|PRESIDEN\b)",
                line,
                re.IGNORECASE,
            ):
                break
            lines.append(line)
            if len(" ".join(lines)) > 250:
                break

        if lines:
            subject = re.sub(r"\s+", " ", " ".join(lines)).strip(" ,.;:-")
            if len(subject) >= 5:
                # Format Title Case yang rapi untuk antarmuka
                return subject.title()

    # Fallback dari nama berkas jika TENTANG tidak terdeteksi
    if filename:
        clean = filename.replace(".pdf", "").replace(".PDF", "")
        # Buang prefix nomor umum jika ada
        clean = re.sub(r"^(?:POJK|SEOJK|PDK|UU|PP)[-_0-9A-Za-z.]+[-_]", "", clean)
        clean = clean.replace("_", " ").replace("-", " ").strip()
        if len(clean) >= 5:
            return clean.title()

    return None


def _detect_date(text: str) -> Optional[str]:
    """Mengekstrak tanggal penetapan regulasi."""
    # Cari di bagian penutup atau 4000 karakter terakhir
    tail = text[-4000:] if len(text) > 4000 else text
    m = RE_TANGGAL_DITETAPKAN.search(tail)
    if not m:
        m = RE_TANGGAL_DITETAPKAN.search(text[:4000])

    if m:
        day_str, month_str, year_str = m.groups()
        month_num = MONTHS_ID.get(month_str.lower())
        if month_num:
            try:
                d = date(int(year_str), month_num, int(day_str))
                return d.isoformat()
            except ValueError:
                pass
    return None


def _detect_sector(text: str, title: Optional[str] = None) -> Optional[str]:
    """Mendeteksi sektor atau bidang regulasi dari kata kunci isi atau judul."""
    corpus = f"{title or ''} {text[:3000]}".lower()

    if re.search(r"\b(?:bank\s+umum|perbankan|bpr|bprs|likuiditas\s+bank|kredit\s+bank|simpanan)\b", corpus):
        return "Perbankan"
    if re.search(r"\b(?:pasar\s+modal|bursa\s+efek|emiten|reksadana|efek|kustodian|waran|ipo)\b", corpus):
        return "Pasar Modal"
    if re.search(r"\b(?:asuransi|perasuransian|dana\s+pensiun|reasuransi|polis|aktuaria|penjaminan)\b", corpus):
        return "Asuransi"
    if re.search(r"\b(?:fintech|pinjaman\s+daring|p2p\s+lending|layanan\s+pendanaan|inovasi\s+keuangan\s+digital)\b", corpus):
        return "Fintech"
    if re.search(r"\b(?:teknologi\s+informasi|keamanan\s+siber|siber|kecerdasan\s+artifisial|\bai\b|sistem\s+elektronik)\b", corpus):
        return "Tata Kelola IT & AI"

    return None


def extract_metadata_from_pdf_content(
    content: bytes,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Fungsi utama untuk mengekstrak metadata dari aliran byte PDF.
    Mengembalikan dict dengan kunci:
    - title: Optional[str]
    - regulation_number: Optional[str]
    - regulation_type: Optional[str]
    - bidang: Optional[str]
    - release_date: Optional[str] (YYYY-MM-DD)
    - page_count: int
    - raw_preview: Optional[str]
    """
    head_text, full_sample_text, total_pages = _extract_pdf_text_sample(content, max_pages=5)

    reg_type = _detect_type(head_text, filename)
    reg_number = _detect_number(head_text, filename)
    title = _detect_title(head_text, filename)
    release_date = _detect_date(full_sample_text)
    bidang = _detect_sector(head_text, title)

    return {
        "title": title,
        "regulation_number": reg_number,
        "regulation_type": reg_type,
        "bidang": bidang,
        "release_date": release_date,
        "page_count": total_pages,
        "raw_preview": head_text[:500] if head_text else None,
    }

