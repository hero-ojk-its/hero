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
    "january": 1, "february": 2, "march": 3, "may": 5,
    "june": 6, "july": 7, "august": 8, "october": 10,
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
    Aturan:
    - Bila kepala dokumen (sebelum TENTANG pertama) berhasil ditemukan, nomor HANYA boleh
      diambil dari kepala itu. Jangan lanjut mencari ke text[:2500].
      Bila kepala memuat "NOMOR" yang isinya kosong atau placeholder ("...", "…", "___", "-", "xx"),
      kembalikan None.
    - Pencarian ke text[:2500] dan fallback nama berkas hanya dipakai bila kepala dokumen
      TIDAK ditemukan sama sekali.
    """
    m_tentang = RE_TENTANG.search(text[:3500])
    if m_tentang:
        header = text[: m_tentang.start()]

        # 1. Pola slash (e.g. 12/POJK.03/2024)
        m_slash = list(RE_NUMBER_SLASH.finditer(header))
        if m_slash:
            raw = m_slash[0].group(1)
            return re.sub(r"\s+", "", raw).strip(" ./-")

        # 2. Pola tahun (e.g. Nomor 12 Tahun 2024)
        m_tahun = list(RE_NUMBER_TAHUN.finditer(header))
        if m_tahun:
            n, y = m_tahun[0].groups()
            return f"{n} Tahun {y}"

        # 3. Pola bare slash
        m_bare = RE_BARE_SLASH.search(header)
        if m_bare:
            raw = m_bare.group(1)
            return re.sub(r"\s+", "", raw).strip(" ./-")

        # Kepala dokumen ada tapi tidak memuat nomor valid -> None
        return None

    # Kepala dokumen TIDAK ditemukan sama sekali (dokumen tanpa TENTANG):
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


def _detect_year(text: str, filename: Optional[str] = None) -> Optional[int]:
    """
    Mengekstrak tahun regulasi / draf regulasi.
    Aturan:
    - Bila kepala dokumen (sebelum TENTANG pertama) berhasil ditemukan, tahun HANYA boleh
      diambil dari kepala itu (misal "TAHUN 2026"). Jangan lanjut mencari ke text[:2500].
      Bila tidak ada tahun di kepala, biarkan kosong (None).
    - Pencarian ke text[:2500] dan fallback nama berkas hanya dipakai bila kepala dokumen
      TIDAK ditemukan sama sekali.
    """
    m_tentang = RE_TENTANG.search(text[:3500])
    if m_tentang:
        header = text[: m_tentang.start()]
        # 1. Cari pola eksplisit TAHUN YYYY di kepala dokumen
        m_tahun = re.search(r"\b(?:TAHUN|YEAR)\s+((?:19|20)\d{2})\b", header, re.IGNORECASE)
        if m_tahun:
            return int(m_tahun.group(1))

        # 2. Cari tahun dari nomor pola slash di kepala dokumen (misal /2024)
        m_slash = list(RE_NUMBER_SLASH.finditer(header))
        if m_slash:
            raw = m_slash[0].group(1)
            y_matches = re.findall(r"\b((?:19|20)\d{2})\b", raw)
            if y_matches:
                return int(y_matches[-1])

        m_bare = RE_BARE_SLASH.search(header)
        if m_bare:
            raw = m_bare.group(1)
            y_matches = re.findall(r"\b((?:19|20)\d{2})\b", raw)
            if y_matches:
                return int(y_matches[-1])

        # Bila tidak ada tahun di kepala, biarkan kosong (None)
        return None

    # Kepala dokumen TIDAK ditemukan sama sekali (dokumen tanpa TENTANG):
    m_tahun = re.search(r"\b(?:TAHUN|YEAR)\s+((?:19|20)\d{2})\b", text[:2500], re.IGNORECASE)
    if m_tahun:
        return int(m_tahun.group(1))

    m_slash = list(RE_NUMBER_SLASH.finditer(text[:2500]))
    if m_slash:
        raw = m_slash[0].group(1)
        y_matches = re.findall(r"\b((?:19|20)\d{2})\b", raw)
        if y_matches:
            return int(y_matches[-1])

    m_bare = RE_BARE_SLASH.search(text[:2500])
    if m_bare:
        raw = m_bare.group(1)
        y_matches = re.findall(r"\b((?:19|20)\d{2})\b", raw)
        if y_matches:
            return int(y_matches[-1])

    if filename:
        fn_matches = re.findall(r"\b((?:19|20)\d{2})\b", filename)
        if fn_matches:
            return int(fn_matches[-1])

    return None


def _format_title(title_raw: str) -> str:
    """Format string judul menjadi Title Case rapi dengan akronim regulasi tetap kapital."""
    res = title_raw.title()
    for acr in ("Ojk", "Pojk", "Seojk", "Pdk", "Sedk", "Pbi", "Sebi", "Uu", "Pp", "Perpres", "Perpu", "Pmk", "Ri"):
        res = re.sub(rf"\b{acr}\b", acr.upper(), res)
    return res


def _detect_title(text: str, filename: Optional[str] = None) -> Optional[str]:
    """Mengekstrak judul regulasi (klausa setelah kata TENTANG)."""
    m = RE_TENTANG.search(text[:3500])
    if m:
        tail = text[m.end() : m.end() + 1000]
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
            # Penanda berhenti tambahan (Langkah fix draf perubahan):
            # 1. Baris yang diawali "Nomor"/"No." diikuti titik dua (misal "Nomor: SIM-01/2026")
            if re.match(r"^No(?:mor)?\.?\s*:", line, re.IGNORECASE):
                break
            # 2. Baris yang diawali tanda butir (•, -, *)
            if re.match(r"^[•\*\-]", line):
                break
            # 3. Baris berpola label "Kata Kunci: nilai" atau label metadata sejenis
            if re.match(r"^(?:Kata\s+Kunci|Keywords?|Versi|Catatan|Keterangan|Penulis|Status|Tanggal|Dokumen)\s*:\s*", line, re.IGNORECASE):
                break
            if re.match(r"^[A-Za-z\s]{2,25}\s*:\s*\S+", line):
                break

            lines.append(line)
            if len(" ".join(lines)) > 400:
                break

        if lines:
            subject = re.sub(r"\s+", " ", " ".join(lines)).strip(" ,.;:-")
            if len(subject) >= 5:
                return _format_title(subject)

    # Fallback dari nama berkas jika TENTANG tidak terdeteksi
    if filename:
        clean = filename.replace(".pdf", "").replace(".PDF", "")
        # Buang prefix jenis dan nomor umum jika ada (misal SEOJK_05_, POJK_12_2024_)
        clean = re.sub(r"^(?:POJK|SEOJK|PDK|SEDK|UU|PP|PBI)[-_0-9.]+[-_]", "", clean, flags=re.IGNORECASE)
        clean = clean.replace("_", " ").replace("-", " ").strip()
        if len(clean) >= 5:
            return _format_title(clean)

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
    - regulation_year: Optional[int]
    - year: Optional[int]
    - bidang: Optional[str]
    - release_date: Optional[str] (YYYY-MM-DD)
    - page_count: int
    - raw_preview: Optional[str]
    """
    head_text, full_sample_text, total_pages = _extract_pdf_text_sample(content, max_pages=5)

    reg_type = _detect_type(head_text, filename)
    reg_number = _detect_number(head_text, filename)
    reg_year = _detect_year(head_text, filename)
    title = _detect_title(head_text, filename)
    release_date = _detect_date(full_sample_text)
    bidang = _detect_sector(head_text, title)

    return {
        "title": title,
        "regulation_number": reg_number,
        "regulation_type": reg_type,
        "regulation_year": reg_year,
        "year": reg_year,
        "bidang": bidang,
        "release_date": release_date,
        "page_count": total_pages,
        "raw_preview": head_text[:500] if head_text else None,
    }


def extract_metadata_from_text(
    text: str,
    filename: Optional[str] = None,
) -> Dict[str, Any]:
    """Mengekstrak metadata langsung dari teks (berguna untuk pengujian tanpa file PDF)."""
    reg_type = _detect_type(text, filename)
    reg_number = _detect_number(text, filename)
    reg_year = _detect_year(text, filename)
    title = _detect_title(text, filename)
    release_date = _detect_date(text)
    bidang = _detect_sector(text, title)

    return {
        "title": title,
        "regulation_number": reg_number,
        "regulation_type": reg_type,
        "regulation_year": reg_year,
        "year": reg_year,
        "bidang": bidang,
        "release_date": release_date,
        "page_count": 1,
        "raw_preview": text[:500] if text else None,
    }

