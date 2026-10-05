import httpx
import ssl
import re

ctx = ssl.create_default_context()
ctx.set_ciphers("DEFAULT@SECLEVEL=1")

headers = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
}

samples = [
    ("PADK Nomor 4 Tahun 2026 Wali Amanat", "95716c28-8ed1-5964-7ed5-592615a5b53c"),
    ("POJK Nomor 10 Tahun 2026 Perdagangan Karbon", "ffba8600-32dd-1c98-e8c3-68d0c8922808"),
    ("POJK Nomor 9 Tahun 2026 Pelaporan Insidental", "d123dff4-9d95-6f53-9568-5224e371a676"),
]

client = httpx.Client(verify=ctx, timeout=30)

for name, guid in samples:
    print("=" * 60)
    print(f"SAMPLE: {name}")
    print(f"GUID Regulasi: {guid}")

    # 1. Direct DownloadDokumen/{guid} probe
    dl_url = f"https://jdih.ojk.go.id/Web/ViewPeraturan/DownloadDokumen/{guid}"
    try:
        head_resp = client.head(dl_url, headers=headers, follow_redirects=True)
        print(f"Direct HEAD {dl_url} -> {head_resp.status_code}")
        print(f"  Content-Disposition: {head_resp.headers.get('content-disposition')}")
        print(f"  Content-Length: {head_resp.headers.get('content-length')}")
    except Exception as e:
        print(f"Direct HEAD error: {e}")

    # 2. Detail Page
    detail_url = f"https://jdih.ojk.go.id/Web/ViewPeraturan/Detail/{guid}/All/"
    try:
        det_resp = client.get(detail_url, headers=headers)
        print(f"Detail Page {detail_url} -> {det_resp.status_code} (HTML length: {len(det_resp.text)})")

        # Cari potongan bagian lampiran
        section_m = re.search(r'(<table[^>]*class=["\']table.*?lampiran.*?</table>|<div[^>]*class=["\']card.*?lampiran.*?</div>)', det_resp.text, re.DOTALL | re.IGNORECASE)
        if not section_m:
            # Cari baris yang memuat DownloadDokumen
            dl_lines = [line.strip() for line in det_resp.text.splitlines() if "DownloadDokumen" in line]
            print(f"Detail snippet lampiran ({len(dl_lines)} baris):")
            for l in dl_lines[:10]:
                print(f"    {l}")

        # Extract attachment links in detail page
        att_matches = re.findall(
            r'href=[\'"](/Web/ViewPeraturan/DownloadDokumen/([a-f0-9-]+))[\'"][^>]*>(.*?)</a>',
            det_resp.text,
            re.DOTALL | re.IGNORECASE,
        )
        print(f"Lampiran sebenarnya di halaman detail ({len(att_matches)} ditemukan):")
        seen = set()
        for path, doc_guid, link_txt in att_matches:
            if doc_guid in seen:
                continue
            seen.add(doc_guid)
            clean_txt = re.sub(r"<[^>]+>", "", link_txt).strip()
            att_url = f"https://jdih.ojk.go.id{path}"
            att_head = client.head(att_url, headers={**headers, "Referer": detail_url}, follow_redirects=True)
            print(f"  * GUID Lampiran: {doc_guid}")
            print(f"    Teks Label   : {clean_txt}")
            print(f"    HEAD Status  : {att_head.status_code}")
            print(f"    CD           : {att_head.headers.get('content-disposition')}")
            print(f"    CL           : {att_head.headers.get('content-length')}")
    except Exception as e:
        print(f"Detail page error: {e}")
