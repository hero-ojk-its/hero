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


def determine_doc_kind(filename_or_title: Optional[str]) -> str:
    """
    Menentukan doc_kind dokumen berdasarkan nama berkas atau judul:
    - 'abstrak'  -> mengandung 'abstrak'
    - 'faq'      -> mengandung 'faq' atau 'tanya jawab'
    - 'lampiran' -> mengandung 'lampiran' / 'lamp'
    - 'utama'    -> lainnya (default dokumen utama)
    """
    if not filename_or_title:
        return "utama"
    lower = filename_or_title.lower()
    if "abstrak" in lower:
        return "abstrak"
    if "faq" in lower or "tanya jawab" in lower or "tanya_jawab" in lower:
        return "faq"
    if "lampiran" in lower or "lamp_" in lower or "lamp-" in lower:
        return "lampiran"
    return "utama"


CRAWLER_REGULATION_ALIASES: Dict[str, str] = {
    "POJK": "POJK",
    "PERATURAN OTORITAS JASA KEUANGAN": "POJK",
    "PERATURAN OJK": "POJK",
    "SEOJK": "SEOJK",
    "SE OJK": "SEOJK",
    "SURAT EDARAN OTORITAS JASA KEUANGAN": "SEOJK",
    "SURAT EDARAN OJK": "SEOJK",
    "PADK": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER": "PADK",
    "PERATURAN ANGGOTA DEWAN KOMISIONER OTORITAS JASA KEUANGAN": "PADK",
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


def normalize_crawler_regulation_type(raw: Optional[str]) -> Optional[str]:
    """Normalisasi jenis regulasi untuk crawler."""
    if not raw or not raw.strip():
        return None
    cleaned = re.sub(r"\s+", " ", raw.strip()).upper()
    return CRAWLER_REGULATION_ALIASES.get(cleaned, cleaned)
