"""Klien HTTP untuk endpoint internal backend HERO (``/api/v1/internal/*``).

Satu kelas, satu sesi ``requests``, satu header kunci API. Hanya kegagalan
sementara yang diulang (timeout, reset koneksi, 429, 5xx) — kesalahan 4xx
adalah kontrak yang dilanggar dan harus terlihat, bukan diulang sampai habis.

Kontrak yang diikuti: ``backend/docs/api/ingest-extraction-contract.md`` dan
``backend/docs/api/crawler-adapter-contract.md``. Perubahan di kedua berkas itu
harus tercermin di sini dan di ``hero/bridge/mapping.py``.
"""
from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Iterable

import requests

from hero.bridge.config import BridgeSettings

log = logging.getLogger("hero.bridge.client")

RETRY_STATUS = {408, 425, 429, 500, 502, 503, 504}
RETRY_EXC = (requests.Timeout, requests.ConnectionError, requests.exceptions.ChunkedEncodingError)


class BackendError(RuntimeError):
    """Permintaan ke backend gagal dengan cara yang tidak bisa diulang."""

    def __init__(self, status: int | None, detail: Any, *, method: str = "", url: str = ""):
        self.status = status
        self.detail = detail
        where = f"{method} {url}".strip()
        super().__init__(f"backend {status or 'tidak dapat dihubungi'} pada {where}: {detail}")


class BackendClient:
    """Pembungkus tipis endpoint internal. Semua metode mengembalikan JSON terurai."""

    def __init__(self, settings: BridgeSettings | None = None, *,
                 session: requests.Session | None = None):
        self.s = settings or BridgeSettings()
        self.http = session or requests.Session()
        self.http.headers.update({
            "X-Internal-API-Key": self.s.api_key,
            "Accept": "application/json",
            "User-Agent": "HERO-DataBridge/1.0 (pipeline/hero)",
        })

    # -- dasar ----------------------------------------------------------
    def _request(self, method: str, path: str, *, retries: int = 3,
                 backoff: float = 1.0, stream: bool = False, **kw) -> requests.Response:
        url = self.s.url(path)
        kw.setdefault("timeout", self.s.timeout)
        kw.setdefault("verify", self.s.verify_tls)
        last: Exception | None = None
        for attempt in range(1, retries + 1):
            try:
                r = self.http.request(method, url, stream=stream, **kw)
            except RETRY_EXC as exc:
                last = exc
                if attempt == retries:
                    raise BackendError(None, exc, method=method, url=url) from exc
            else:
                if r.status_code in RETRY_STATUS and attempt < retries:
                    last = BackendError(r.status_code, _detail(r), method=method, url=url)
                elif r.status_code >= 400:
                    raise BackendError(r.status_code, _detail(r), method=method, url=url)
                else:
                    return r
            wait = backoff * (2 ** (attempt - 1))
            log.warning("percobaan %s/%s gagal (%s) — menunggu %.1fs", attempt, retries, last, wait)
            time.sleep(wait)
        raise BackendError(None, last, method=method, url=url)   # pragma: no cover

    def _json(self, method: str, path: str, **kw) -> Any:
        r = self._request(method, path, **kw)
        if not r.content:
            return None
        try:
            return r.json()
        except ValueError as exc:
            raise BackendError(r.status_code, f"respons bukan JSON: {r.text[:200]}",
                               method=method, url=self.s.url(path)) from exc

    # -- kesehatan & diagnosa -------------------------------------------
    def health(self) -> dict[str, Any]:
        """``GET /health`` — tanpa kunci API, dipakai ``hero bridge status``."""
        return self._json("GET", "/health", retries=1)

    def ping_internal(self) -> bool:
        """Apakah kunci API internal diterima? Klaim 0 dokumen tidak mengubah apa pun."""
        try:
            self._json("POST", "/api/v1/internal/extraction/claim", params={"limit": 1}, retries=1)
            return True
        except BackendError as exc:
            if exc.status == 401:
                return False
            raise

    # -- alur pindai (mode push) ----------------------------------------
    def claim_scans(self, limit: int = 1) -> list[dict[str, Any]]:
        return self._json("POST", "/api/v1/internal/scans/claim",
                          params={"limit": max(1, min(5, limit))}) or []

    def push_candidates(self, scan_id: int, candidates: Iterable[dict[str, Any]], *,
                        pages_visited: int = 0, done: bool = False, truncated: bool = False,
                        errors: list[str] | None = None, error: str | None = None) -> dict[str, Any]:
        body = {"candidates": list(candidates), "pages_visited": int(pages_visited),
                "done": bool(done), "truncated": bool(truncated),
                "errors": errors or [], "error": error}
        return self._json("POST", f"/api/v1/internal/scans/{scan_id}/candidates", json=body)

    # -- alur ekstraksi --------------------------------------------------
    def claim_extraction(self, limit: int = 5) -> list[dict[str, Any]]:
        return self._json("POST", "/api/v1/internal/extraction/claim",
                          params={"limit": max(1, min(50, limit))}) or []

    def download_pdf(self, document_id: int, dest: Path, *, chunk: int = 1 << 20) -> Path:
        """Unduh PDF asli ke ``dest``. Berkas ditulis utuh atau tidak ditulis sama sekali."""
        dest = Path(dest)
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(dest.suffix + ".part")
        r = self._request("GET", f"/api/v1/internal/documents/{document_id}/pdf", stream=True)
        try:
            with open(tmp, "wb") as fh:
                for block in r.iter_content(chunk_size=chunk):
                    if block:
                        fh.write(block)
            tmp.replace(dest)
        finally:
            r.close()
            tmp.unlink(missing_ok=True)
        return dest

    def patch_extraction(self, document_id: int, payload: dict[str, Any], *,
                         force: bool = False) -> dict[str, Any]:
        return self._json("PATCH", f"/api/v1/internal/documents/{document_id}/extraction",
                          params={"force": str(bool(force)).lower()}, json=payload)

    def post_articles(self, articles: list[dict[str, Any]]) -> dict[str, Any]:
        if not articles:
            return {"status": "ok", "inserted_count": 0, "message": "tidak ada pasal"}
        return self._json("POST", "/api/v1/internal/articles", json={"articles": articles})

    def requeue(self, document_id: int) -> dict[str, Any]:
        return self._json("POST", f"/api/v1/internal/extraction/requeue/{document_id}")

    def close(self) -> None:
        self.http.close()

    def __enter__(self) -> "BackendClient":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def _detail(r: requests.Response) -> Any:
    try:
        body = r.json()
    except ValueError:
        return r.text[:300]
    return body.get("detail", body) if isinstance(body, dict) else body
