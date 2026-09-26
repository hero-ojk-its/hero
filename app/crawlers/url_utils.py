"""
app/crawlers/url_utils.py
Utilitas URL: normalisasi, pendeteksian tautan PDF, dan proteksi SSRF (guard_url).
PENTING: Modul ini TIDAK BOLEH mengimpor app.database, app.models, app.routers, app.services.
"""
import ipaddress
import socket
from urllib.parse import urlsplit, urlunsplit, quote, unquote
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
            # Handle IPv6 brackets
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
    # Quote kembali path dengan membiarkan slash dan karakter path standar
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


def _is_blocked_ip(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """Memeriksa apakah sebuah alamat IP terlarang (privat, loopback, link-local, dll)."""
    if str(ip) == "169.254.169.254":
        return True
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
        # Bukan IP literal, lanjutkan ke resolusi DNS
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
