"""Fase 2 — Analisa, Summary & Key Takeaways (URD 3.3).

* ``structured``  v2 Deterministik: ringkasan terstruktur & poin kunci berbasis pasal
* ``ai``          AI-Assisted: narasi natural di atas fakta v2, terverifikasi, dengan fallback
* ``clauses``     klausul yang relevan dengan kebutuhan pengguna
* ``evaluate``    v1 vs v2, indikator Fase 2, templat telaah ahli
"""
from __future__ import annotations

import sqlite3
from typing import Any

from hero.analysis.ai import AiNarrator
from hero.analysis.structured import AnalysisV2, analyse_all, analyse_document


def analysis_payload(conn: sqlite3.Connection, doc_id: str, *, mode: str, narrator: AiNarrator,
                     force_ai: bool = False) -> dict[str, Any] | None:
    """One response shape for CLI and API: Deterministic always, AI layered on top."""
    a = analyse_document(conn, doc_id)
    if a is None:
        return None
    akses = (conn.execute("SELECT COALESCE(access_class, 'publik') FROM documents WHERE doc_id = ?",
                          (doc_id,)).fetchone() or ["publik"])[0]
    out = a.to_dict()
    out["poin_utama"] = [vars(p) for p in a.poin_utama(10)]
    out["jumlah_poin"] = len(a.poin)
    out.pop("poin")
    out["mode_diminta"] = mode
    out["mode_dipakai"] = "deterministik"
    out["ai"] = None
    if mode == "ai":
        res = narrator.narrate(a, akses=akses, conn=conn, force=force_ai)
        out["ai"] = res.to_dict()
        if res.status == "ai":
            out["mode_dipakai"] = "ai"
            out["ringkasan_ai"] = res.ringkasan
            for p in out["poin_utama"]:
                p["parafrase"] = res.poin_kunci.get(p["id"])
    return out


__all__ = ["AiNarrator", "AnalysisV2", "analyse_all", "analyse_document", "analysis_payload"]
