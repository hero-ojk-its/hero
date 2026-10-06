"""Isi kolom ``articles.embedding`` backend untuk pasal yang belum punya vektor.

Dipakai untuk dua keadaan:

* pasal yang masuk **sebelum** jembatan ada (atau saat ``bridge.embedder:
  none``), sehingga teksnya ada tetapi vektornya kosong;
* ganti model embedding — vektor dari ruang yang berbeda tidak bisa
  dibandingkan satu sama lain, jadi seluruh kolom harus diisi ulang
  (``--ulang``) dalam satu model yang sama.

Default-nya **uji coba** (dry-run): tanpa ``--apply`` tidak ada yang ditulis.
Ini satu-satunya operasi jembatan yang menulis langsung ke Postgres; kolomnya
memang disiapkan backend untuk lapisan data, dan tidak ada kolom lain yang
disentuh.
"""
from __future__ import annotations

import logging
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Sequence

from hero.bridge import pg
from hero.bridge.config import BridgeSettings
from hero.bridge.embed import ArticleEmbedder, EmbedderUnavailable
from hero.config import Settings

log = logging.getLogger("hero.bridge.vectorize")


@dataclass
class BackfillReport:
    kandidat: int = 0
    diembed: int = 0
    ditulis: int = 0
    dimensi_model: int = 0
    dimensi_kolom: int | None = None
    embedder: str = ""
    mode: str = ""
    detik: float = 0.0
    uji_coba: bool = True
    galat: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {k: v for k, v in self.__dict__.items()}


def backfill(settings: Settings, bridge: BridgeSettings, *, dsn: str | None = None,
             limit: int = 1000, document_ids: Sequence[int] | None = None,
             apply: bool = False, reset: bool = False,
             progress: Callable[[str], None] | None = None) -> BackfillReport:
    say = progress or (lambda m: None)
    rep = BackfillReport(uji_coba=not apply)
    started = time.perf_counter()
    emb = ArticleEmbedder(settings, bridge)
    if not emb.enabled:
        rep.galat.append("bridge.embedder = none — tidak ada vektor untuk diisi")
        return rep
    rep.embedder, rep.mode = emb.name, emb.mode
    try:
        rep.dimensi_model = emb.source_dim        # memuat modelnya
    except EmbedderUnavailable as exc:
        # Pesannya sudah memuat cara memperbaikinya; dilaporkan, tidak dilemparkan.
        rep.galat.append(str(exc))
        return rep

    conn = pg.connect(dsn)
    try:
        rep.dimensi_kolom = pg.embedding_dim(conn)
        if rep.dimensi_kolom and rep.dimensi_kolom < rep.dimensi_model:
            rep.galat.append(
                f"kolom articles.embedding {rep.dimensi_kolom} dimensi, model {rep.dimensi_model} "
                f"dimensi — vektor tidak muat. Ubah kolom atau pilih model lebih kecil.")
            return rep
        if rep.dimensi_kolom and rep.dimensi_kolom != bridge.backend_dim:
            say(f"catatan: kolom backend {rep.dimensi_kolom} dimensi, bridge.backend_dim "
                f"{bridge.backend_dim} — memakai {rep.dimensi_kolom}")
            emb.backend_dim = rep.dimensi_kolom

        if reset:
            if apply:
                with conn.cursor() as cur:
                    cur.execute("UPDATE articles SET embedding = NULL WHERE level = 'pasal'")
                say("seluruh vektor pasal dikosongkan (ganti model)")
            else:
                say("uji coba: vektor TIDAK dikosongkan")

        rows = pg.articles_without_embedding(conn, limit=limit, document_ids=document_ids)
        rep.kandidat = len(rows)
        say(f"{len(rows)} pasal tanpa vektor")
        if not rows:
            return rep

        batch = max(1, bridge.batch_articles)
        for start in range(0, len(rows), batch):
            chunk = rows[start:start + batch]
            vecs = emb.article_vectors([r["teks"] for r in chunk])
            pairs = [(r["id"], v) for r, v in zip(chunk, vecs) if v is not None]
            rep.diembed += len(pairs)
            if apply and pairs:
                rep.ditulis += pg.set_embeddings(conn, pairs)
            say(f"  {min(start + batch, len(rows))}/{len(rows)} pasal")
    finally:
        conn.close()
    rep.detik = round(time.perf_counter() - started, 1)
    return rep
