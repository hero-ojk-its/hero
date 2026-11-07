"""
app/responses.py
Kustomisasi response class untuk memastikan header charset=utf-8 pada seluruh respons JSON.
"""
from fastapi.responses import JSONResponse


class Utf8JSONResponse(JSONResponse):
    """
    JSONResponse dengan Content-Type: application/json; charset=utf-8 (Langkah 38).
    Memastikan karakter khusus seperti em-dash ("—") terbaca sempurna di seluruh klien/terminal.
    """
    media_type = "application/json"

    def init_headers(self, headers=None) -> None:
        super().init_headers(headers)
        self.headers["content-type"] = "application/json; charset=utf-8"

