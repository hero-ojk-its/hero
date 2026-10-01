"""
app/crawlers/url_utils.py
Utilitas URL: normalisasi, pendeteksian tautan PDF, proteksi SSRF (guard_url),
deteksi captcha/WAF, ekstraksi redirect, dan penentuan tipe dokumen.
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import ipaddress
import re
import socket
from typing import Optional, Tuple, Dict, Any, Union
from urllib.parse import urlsplit, urlunsplit, quote, unquote, urljoin

import httpx

from app.crawlers.base import BlockedUrlError


def normalize_url(url: str) -> str:
    """
    Menormalisasi URL secara konsisten:
    - Skema dan host diubah menjadi huruf kecil.
    - Port default (:80 untuk http, :443 untuk https) dibuang.
    - Fragment (#...) dibuang.
    - Percent-encoding pada path dirapikan (unquote lalu quote dengan aman).
    - Query parameter dipertahankan sesuai urutan asli.
    """
    if not url:
        return ""

    url_clean = url.strip()
    parsed = urlsplit(url_clean)

    scheme = parsed.scheme.lower()
    hostname = parsed.hostname.lower() if parsed.hostname else ""
    port = parsed.port

    # Format netloc tanpa port default
    if not hostname:
        netloc = ""
    else:
        # Periksa apakah port perlu dihilangkan
        if (scheme == "http" and port == 80) or (scheme == "https" and port == 443) or port is None:
            if ":" in hostname and not hostname.startswith("["):
                netloc = f"[{hostname}]"
            else:
                netloc = hostname
        else:
            if ":" in hostname and not hostname.startswith("["):
                netloc = f"[{hostname}]:{port}"
            else:
                netloc = f"{hostname}:{port}"

    # Normalisasi path (unquote lalu quote aman)
    unquoted_path = unquote(parsed.path)
    normalized_path = quote(unquoted_path, safe="/:@&+$,;=-_.~%*'")

    # Query dipertahankan apa adanya
    query = parsed.query

    return urlunsplit((scheme, netloc, normalized_path, query, ""))


def is_pdf_link(url: str, link_text: str = "") -> bool:
    """
    Memeriksa apakah URL atau teks tautan merujuk ke berkas PDF.
    - Path berakhiran .pdf (case-insensitive, query diabaikan).
    - ATAU teks tautan berakhiran .pdf.
    """
    if not url:
        return False

    parsed = urlsplit(url)
    path = unquote(parsed.path).strip()
    if path.lower().endswith(".pdf"):
        return True

    if link_text and link_text.strip().lower().endswith(".pdf"):
        return True

    return False


def _is_blocked_ip(ip: Union[ipaddress.IPv4Address, ipaddress.IPv6Address]) -> bool:
    """Memeriksa apakah sebuah alamat IP terlarang (privat, loopback, link-local, dll)."""
    if str(ip) == "169.254.169.254":
        return True

    # Handle IPv6 NAT64 Well-Known Prefix (64:ff9b::/96) yang memetakan IPv4 publik
    if isinstance(ip, ipaddress.IPv6Address) and ip in ipaddress.IPv6Network("64:ff9b::/96"):
        embedded_v4 = ipaddress.IPv4Address(ip.packed[12:])
        return _is_blocked_ip(embedded_v4)

    return (
        ip.is_private
        or ip.is_loopback
        or ip.is_link_local
        or ip.is_reserved
        or ip.is_multicast
        or ip.is_unspecified
    )


def guard_url(url: str, allow_private: bool = False) -> None:
    """
    Perlindungan SSRF dan validasi skema URL:
    - Hanya skema 'http' dan 'https' yang diizinkan.
    - Host di-resolve lewat DNS dan setiap IP hasil resolusi diperiksa.
    - Tolak IP privat, loopback, link-local, multicast, dan AWS metadata (169.254.169.254).
    - Melempar BlockedUrlError dengan pesan Indonesia jika terlarang.
    """
    if not url:
        raise BlockedUrlError("URL tidak boleh kosong.")

    try:
        parsed = urlsplit(url.strip())
    except Exception as e:
        raise BlockedUrlError(f"Format URL tidak valid: {e}")

    scheme = parsed.scheme.lower()
    if scheme not in ("http", "https"):
        raise BlockedUrlError(
            f"Skema URL '{parsed.scheme}' tidak diizinkan. Hanya 'http' dan 'https' yang didukung."
        )

    host = parsed.hostname
    if not host:
        raise BlockedUrlError("URL tidak memiliki host yang valid.")

    if allow_private:
        return

    # Periksa jika host adalah representasi IP literal
    try:
        ip = ipaddress.ip_address(host)
        if _is_blocked_ip(ip):
            raise BlockedUrlError(
                f"Akses ke alamat IP privat/lokal/khusus diblokir demi keamanan (SSRF): {ip}"
            )
        return
    except ValueError:
        pass

    # Resolusi DNS untuk memeriksa semua alamat IP host
    try:
        addr_info = socket.getaddrinfo(host, None)
        if not addr_info:
            raise BlockedUrlError(f"Host '{host}' tidak dapat di-resolve via DNS.")

        for item in addr_info:
            ip_str = item[4][0]
            try:
                resolved_ip = ipaddress.ip_address(ip_str)
                if _is_blocked_ip(resolved_ip):
                    raise BlockedUrlError(
                        f"Akses ke host '{host}' yang mengarah ke IP privat/lokal ({resolved_ip}) "
                        f"diblokir demi keamanan (SSRF)."
                    )
            except ValueError:
                continue
    except socket.gaierror as gai_err:
        raise BlockedUrlError(f"Gagal melakukan resolusi DNS untuk host '{host}': {gai_err}")
    except BlockedUrlError:
        raise
    except Exception as err:
        raise BlockedUrlError(f"Kesalahan saat memeriksa keamanan host '{host}': {err}")


def extract_filename_from_cd(cd_header: Optional[str]) -> Optional[str]:
    """Mengekstrak nama file dari header Content-Disposition."""
    if not cd_header:
        return None
    # Cari format filename*=UTF-8''...
    match_star = re.search(r"filename\*\s*=\s*UTF-8''([^;\s]+)", cd_header, re.IGNORECASE)
    if match_star:
        return unquote(match_star.group(1))
    # Cari format filename="..." atau filename=...
    match = re.search(r'filename\s*=\s*(?:"([^"]+)"|([^;\s]+))', cd_header, re.IGNORECASE)
    if match:
        raw_name = match.group(1) or match.group(2)
        return unquote(raw_name)
    return None


def detect_captcha_or_waf(
    status_code: int,
    headers: Union[Dict[str, str], httpx.Headers, None] = None,
    body_text: str = "",
) -> Optional[str]:
    """
    Mendeteksi proteksi Captcha, Cloudflare, atau WAF (Web Application Firewall).
    Mengembalikan nama penanda yang terdeteksi jika ada, atau None jika bersih.
    """
    h_dict = {k.lower(): v.lower() for k, v in (headers or {}).items()}
    body_lower = (body_text or "").lower()

    # 1. Deteksi penanda header Cloudflare
    if "cf-chl-bypass" in h_dict or "cf-mitigated" in h_dict:
        return "cf-chl"

    # 2. Deteksi status 403 / 429 / 503 dengan penanda Cloudflare / WAF
    if status_code in (403, 429, 503):
        if "cf-ray" in h_dict and ("just a moment" in body_lower or "cf-chl" in body_lower or "cloudflare" in body_lower):
            return "cf-ray:Just a moment"
        if "cf-chl" in body_lower or "challenges.cloudflare.com" in body_lower or "cf-turnstile" in body_lower:
            return "cf-chl"
        if "attention required! | cloudflare" in body_lower:
            return "cloudflare:Attention Required"
        if "g-recaptcha" in body_lower or "recaptcha" in body_lower or "www.google.com/recaptcha" in body_lower:
            return "g-recaptcha"
        if "hcaptcha" in body_lower or "h-captcha" in body_lower:
            return "hcaptcha"
        if "the requested url was rejected" in body_lower or "request rejected" in body_lower or "support id is:" in body_lower:
            return "waf_rejected"
        if "access denied" in body_lower or "forbidden" in body_lower:
            return f"http_{status_code}_access_denied"

    # 3. Deteksi Captcha / Cloudflare / WAF di halaman status 200
    if "cf-chl" in body_lower or "challenges.cloudflare.com" in body_lower:
        return "cf-chl"
    if "g-recaptcha" in body_lower or "recaptcha/api.js" in body_lower:
        return "g-recaptcha"
    if "hcaptcha.com" in body_lower or "class=\"h-captcha\"" in body_lower:
        return "hcaptcha"
    if "the requested url was rejected" in body_lower and "support id is:" in body_lower:
        return "waf_rejected"
    if "<title>just a moment...</title>" in body_lower and "cloudflare" in body_lower:
        return "cf-ray:Just a moment"

    return None


def extract_meta_or_js_redirect(html_content: str, base_url: str) -> Optional[str]:
    """
    Mengekstrak URL redirect dari tag <meta http-equiv="refresh"> atau JavaScript sederhana.
    """
    if not html_content:
        return None

    # Meta refresh: <meta http-equiv="refresh" content="0; url=https://example.com/target">
    meta_match = re.search(
        r'<meta\s+[^>]*http-equiv=["\']?refresh["\']?[^>]*content=["\']?[0-9]+;\s*url=([^"\'\s>]+)["\']?',
        html_content,
        re.IGNORECASE,
    )
    if meta_match:
        target = meta_match.group(1).strip()
        return urljoin(base_url, target)

    # JS redirect: window.location.href = '...'; or window.location = '...'; or window.location.replace('...');
    js_match = re.search(
        r'(?:window\.)?location(?:\.href|\.replace)?\s*(?:=|\()\s*["\']([^"\']+)["\']',
        html_content,
        re.IGNORECASE,
    )
    if js_match:
        target = js_match.group(1).strip()
        return urljoin(base_url, target)

    return None


def determine_doc_kind(filename_or_title: Optional[str], label: Optional[str] = None) -> str:
    """
    Menentukan peran dokumen: utama | abstrak | faq | lampiran.
    Mengenali:
    - Pola dengan spasi ('Abstrak POJK ...', 'FAQ POJK ...')
    - Pola kode kompak tanpa spasi ('2026abspojk008.pdf', '2024faqseojk020.pdf', '2026abspadk004.pdf')
    - Label terpisah bila disediakan dari situs/detail ('Abstrak', 'FAQ', 'Dokumen Utama', 'Lampiran')
    - Penanda salinan resmi ('SAL POJK ...', 'Salinan ...') -> 'utama'
    """
    targets = []
    if label:
        targets.append(label.lower().strip())
    if filename_or_title:
        targets.append(filename_or_title.lower().strip())

    combined = " ".join(targets)
    if not combined.strip():
        return "utama"

    # 1. Abstrak
    if re.search(r'\babstrak\b|abs(?:pojk|seojk|padk|pdk|kdk)|\babs\b|(?:\d{4})abs|^abs[-_]', combined):
        return "abstrak"

    # 2. FAQ / Tanya Jawab
    if re.search(r'\bfaq\b|faq(?:pojk|seojk|padk|pdk|kdk)|(?:\d{4})faq|\btanya\s*jawab\b', combined):
        return "faq"

    # 3. Lampiran
    if re.search(r'\blampiran\b|\blamp[-_]|\blamp\b', combined):
        return "lampiran"

    # 4. Salinan / Dokumen Utama: 'salinan', 'sal ' -> utama
    if re.search(r'\bsalinan\b|^sal\s+|^sal[-_]', combined):
        return "utama"

    return "utama"


CRAWLER_REGULATION_ALIASES: Dict[str, str] = {
    "POJK": "POJK",
    "PERATURAN OTORITAS JASA KEUANGAN": "POJK",
    "PERATURAN OJK": "POJK",
    "SEOJK": "SEOJK",
    "SE OJK": "SEOJK",
    "SE_OJK": "SEOJK",
    "SURAT EDARAN OTORITAS JASA KEUANGAN": "SEOJK",
    "SURAT EDARAN OJK": "SEOJK",
    "SURAT EDARAN": "SEOJK",
    "PADK": "PADK",
    "PERATURAN ADK": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER OTORITAS JASA KEUANGAN": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER OJK": "PADK",
    "KDK": "KDK",
    "KEPUTUSAN DEWAN KOMISIONER": "KDK",
    "KEPUTUSAN DEWAN KOMISIONER OTORITAS JASA KEUANGAN": "KDK",
    "PDK": "PDK",
    "PERATURAN DEWAN KOMISIONER": "PDK",
    "UU": "UU",
    "UNDANG-UNDANG": "UU",
    "UNDANG UNDANG": "UU",
    "PP": "PP",
    "PERATURAN PEMERINTAH": "PP",
    "PERPRES": "PERPRES",
    "PERATURAN PRESIDEN": "PERPRES",
    "PERMENKEU": "PERMENKEU",
    "PMK": "PERMENKEU",
    "PERATURAN MENTERI KEUANGAN": "PERMENKEU",
    "PBI": "PBI",
    "PERATURAN BANK INDONESIA": "PBI",
    "SEBI": "SEBI",
    "SURAT EDARAN BANK INDONESIA": "SEBI",
    "PERDA": "PERDA",
    "PERATURAN DAERAH": "PERDA",
    "INPRES": "INPRES",
    "INSTRUKSI PRESIDEN": "INPRES",
}


def normalize_crawler_regulation_type(raw: Optional[str], title: Optional[str] = None) -> Optional[str]:
    """
    Normalisasi jenis regulasi untuk crawler.
    Mendukung pemetaan dari label mentah maupun inferensi dari judul regulasi
    (misal bila label mentah berupa kategori gabungan).
    """
    # 1. Inferensi dari judul jika judul tersedia
    if title:
        t_low = title.lower()
        if "peraturan anggota dewan komisioner" in t_low or re.search(r'\bpadk\b', t_low):
            return "PADK"
        if "surat edaran" in t_low or re.search(r'\bseojk\b', t_low):
            return "SEOJK"
        if "peraturan otoritas jasa keuangan" in t_low or re.search(r'\bpojk\b', t_low):
            return "POJK"
        if "keputusan dewan komisioner" in t_low or re.search(r'\bkdk\b', t_low):
            return "KDK"
        if "peraturan dewan komisioner" in t_low or re.search(r'\bpdk\b', t_low):
            return "PDK"

    if not raw or not raw.strip():
        return None

    cleaned = re.sub(r"\s+", " ", raw.strip()).upper()

    # Jika label mentah adalah label gabungan JDIH
    if "SURAT EDARAN" in cleaned and "PERATURAN ANGGOTA DEWAN KOMISIONER" in cleaned:
        if title:
            t_low = title.lower()
            if "peraturan anggota dewan komisioner" in t_low:
                return "PADK"
            if "surat edaran" in t_low:
                return "SEOJK"
        return "PADK"

    return CRAWLER_REGULATION_ALIASES.get(cleaned, cleaned)


def validate_regulation_filename_match(
    filename: str,
    regulation_number: Optional[str] = None,
    release_date: Optional[Any] = None,
    document_title: Optional[str] = None,
    regulation_type: Optional[str] = None,
) -> Optional[str]:
    """
    Memvalidasi kecocokan antara nama berkas PDF dengan metadata regulasi (nomor dan tahun).
    Toleran terhadap format:
    - '2026pojk008.pdf', '2026abspojk008.pdf'
    - 'SAL POJK 72 - ...'
    - 'POJK 17 Tahun 2023.pdf'
    - 'Salinan POJK Nomor 19 Tahun 2023.pdf'
    - 'Peraturan_OJK_3_2015.pdf'
    Jika nomor atau tahun bertentangan secara jelas, mengembalikan pesan peringatan.
    Jika cocok atau data tidak cukup untuk disimpulkan, mengembalikan None.
    """
    if not filename:
        return None

    fn_lower = filename.lower()

    # 1. Ekstrak tahun dari berkas
    fn_years = re.findall(r'(?:^|[\W_])(20\d\d|19\d\d)(?:[\W_]|$)', fn_lower)
    if not fn_years:
        prefix_y = re.match(r'^(20\d\d|19\d\d)', fn_lower)
        if prefix_y:
            fn_years = [prefix_y.group(1)]

    # Ekstrak tahun dari metadata regulasi
    # Prioritaskan tahun dari nomor resmi atau judul regulasi (bukan release_date)
    reg_year = None
    if regulation_number:
        # Contoh: "24/SEOJK.03/2016", "POJK 18 Tahun 2025", "18/2025"
        rn_y = re.findall(r'(?:^|[\W_])(20\d\d|19\d\d)(?:[\W_]|$)', regulation_number)
        if rn_y:
            reg_year = int(rn_y[-1])

    if not reg_year and document_title:
        # Pola "Tahun 2025" atau 4-digit tahun di judul
        t_y = re.search(r'\bTahun\s+(20\d\d|19\d\d)\b', document_title, re.IGNORECASE)
        if t_y:
            reg_year = int(t_y.group(1))
        else:
            title_y = re.findall(r'(?:^|[\W_])(20\d\d|19\d\d)(?:[\W_]|$)', document_title)
            if title_y:
                reg_year = int(title_y[0])

    if not reg_year and release_date and hasattr(release_date, "year") and release_date.year:
        reg_year = release_date.year

    # 2. Ekstrak nomor regulasi dari metadata
    reg_num_int = None
    if regulation_number:
        num_m = re.search(r'\b(\d+)\b', regulation_number)
        if num_m:
            reg_num_int = int(num_m.group(1))
    elif document_title:
        num_m = re.search(r'nomor\s*[:\s]*(\d+)', document_title, re.IGNORECASE)
        if num_m:
            reg_num_int = int(num_m.group(1))

    # 3. Ekstrak nomor dari nama berkas
    fn_num_ints = []
    # Pola pojk008 / abspojk008 / padk004
    code_m = re.search(r'(?:pojk|seojk|padk|pdk|kdk)[-_]?0*(\d+)', fn_lower)
    if code_m:
        fn_num_ints.append(int(code_m.group(1)))

    # Pola nomor 19 / no. 19 / no 19
    no_m = re.search(r'(?:nomor|no\.?)[-_ ]*0*(\d+)', fn_lower)
    if no_m:
        fn_num_ints.append(int(no_m.group(1)))

    # Pola angka setelah jenis: peraturan_ojk_3 / pojk_17 / pojk 17 / sal pojk 72
    after_kind_m = re.search(r'(?:peraturan_ojk|pojk|seojk|padk|pdk|kdk)[-_ ]+0*(\d+)', fn_lower)
    if after_kind_m:
        fn_num_ints.append(int(after_kind_m.group(1)))

    warnings = []

    # Cek konflik tahun jika berkas dan regulasi sama-sama punya tahun
    if fn_years and reg_year:
        fn_y_ints = [int(y) for y in fn_years]
        if reg_year not in fn_y_ints:
            warnings.append(f"Tahun berkas ({fn_years[0]}) != regulasi ({reg_year})")

    # Cek konflik nomor jika berkas dan regulasi sama-sama punya nomor
    if fn_num_ints and reg_num_int is not None:
        if reg_num_int not in fn_num_ints:
            warnings.append(f"Nomor berkas ({fn_num_ints[0]}) != regulasi ({reg_num_int})")

    if warnings:
        return "; ".join(warnings)
    return None


def parse_onedrive_filename_metadata(filename: str) -> Dict[str, Any]:
    """
    Mengekstrak metadata (jenis, nomor, tahun/release_date) dari nama berkas OneDrive.
    Contoh:
    - Peraturan_OJK_3_2015.pdf -> jenis POJK, nomor 3, tahun 2015
    - POJK_17_2023.pdf -> jenis POJK, nomor 17, tahun 2023
    - SEOJK_46_2017.pdf -> jenis SEOJK, nomor 46, tahun 2017
    - PADK_4_2026.pdf -> jenis PADK, nomor 4, tahun 2026
    """
    if not filename:
        return {}

    stem = re.sub(r'\.pdf$', '', filename.strip(), flags=re.IGNORECASE)

    # 1. Deteksi jenis
    stem_lower = stem.lower()
    reg_type = None
    if "peraturan_ojk" in stem_lower or stem_lower.startswith("pojk"):
        reg_type = "POJK"
    elif "surat_edaran" in stem_lower or stem_lower.startswith("seojk") or stem_lower.startswith("se_ojk"):
        reg_type = "SEOJK"
    elif "peraturan_adk" in stem_lower or stem_lower.startswith("padk"):
        reg_type = "PADK"
    elif "keputusan_dewan" in stem_lower or stem_lower.startswith("kdk"):
        reg_type = "KDK"
    elif "peraturan_dewan" in stem_lower or stem_lower.startswith("pdk"):
        reg_type = "PDK"

    # 2. Deteksi tahun (4 digit)
    year = None
    year_m = re.findall(r'(?:^|[\W_])(20\d\d|19\d\d)(?:[\W_]|$)', stem)
    if year_m:
        year = int(year_m[-1])

    # 3. Deteksi nomor
    num_str = None
    # Pola: Peraturan_OJK_3_2015 atau POJK_17_2023
    num_m = re.search(r'(?:peraturan_ojk|pojk|seojk|se_ojk|padk|kdk|pdk)[-_ ]+0*(\d+)', stem, re.IGNORECASE)
    if num_m:
        num_str = num_m.group(1)
    else:
        # Cari angka pertama yang bukan tahun
        for token in re.split(r'[-_ ]+', stem):
            if token.isdigit() and token != (str(year) if year else ""):
                num_str = token
                break

    if not reg_type and not num_str and not year:
        return {}

    from datetime import date as d_date
    res: Dict[str, Any] = {
        "regulation_type": reg_type,
        "regulation_number": num_str,
        "year": year,
        "release_date": d_date(year, 1, 1) if year else None,
    }
    return res


