"""Split documents into the units that get embedded.

The unit is the Pasal, because the Pasal is what the harmonisation feature
compares (URD 3.4) — a match must point at "Pasal 12 of POJK X", not at a
whole 100-page regulation. Surat Edaran have no Pasal, so they fall back to
their Roman-numeral sections, then to plain text windows.

Why long units are split: the multilingual MiniLM model reads at most 128
tokens (roughly 80 Indonesian words) and silently ignores the rest. A 400-word
Pasal embedded whole is represented by its first paragraph only. Windows of
``WINDOW_WORDS`` with overlap keep every part of the Pasal searchable, and
every window remembers which Pasal it came from.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
from dataclasses import dataclass

WINDOW_WORDS = 80
OVERLAP_WORDS = 20
MAX_FALLBACK_WINDOWS = 150   # per document without Pasal/sections
MIN_WORDS = 6


@dataclass
class Chunk:
    chunk_id: str
    doc_id: str
    level: str          # 'dokumen' | 'pasal' | 'seksi' | 'teks'
    ref: str | None     # "Pasal 12", "II. KETENTUAN UMUM", None
    part: int           # window index inside the Pasal (0 = first)
    page: int | None
    text: str


def windows(text: str, size: int = WINDOW_WORDS, overlap: int = OVERLAP_WORDS) -> list[str]:
    words = text.split()
    if len(words) <= size:
        return [" ".join(words)] if len(words) >= MIN_WORDS else []
    step = size - overlap
    out = []
    for start in range(0, len(words), step):
        piece = words[start:start + size]
        if len(piece) < MIN_WORDS:
            break
        out.append(" ".join(piece))
        if start + size >= len(words):
            break
    return out


def section_bodies(sections: list[dict], full_text: str) -> list[tuple[str, int | None, str]]:
    """Recover each section's body from the full text.

    The structure parser records a section's number, title and page but not
    its text, so without this a Surat Edaran would be indexed by its headings
    alone. Each heading ("II. KETENTUAN UMUM") is located in the text in order;
    a section's body runs to the next located heading. Returns [] when fewer
    than half the headings can be found — then plain windows are safer than
    bodies attributed to the wrong section.
    """
    text = re.sub(r"\s+", " ", full_text)
    found: list[tuple[int, str, int | None]] = []
    cursor = 0
    for sec in sections:
        num, title = str(sec.get("number") or "").strip(), str(sec.get("title") or "").strip()
        if not title:
            continue
        rx = re.compile(rf"\b{re.escape(num)}\.\s*{re.escape(title[:40])}" if num
                        else re.escape(title[:40]), re.I)
        m = rx.search(text, cursor)
        if m:
            page = sec.get("page")
            found.append((m.start(), f"{num}. {title}".strip(". "),
                          int(page) if str(page).isdigit() else None))
            cursor = m.end()
    if len(found) < max(1, len(sections) // 2):
        return []
    out = []
    for i, (start, label, page) in enumerate(found):
        end = found[i + 1][0] if i + 1 < len(found) else len(text)
        out.append((label, page, text[start:end]))
    return out


def _cid(doc_id: str, level: str, ref: str | None, part: int) -> str:
    return hashlib.sha1(f"{doc_id}|{level}|{ref}|{part}".encode()).hexdigest()[:16]


def chunk_document(doc_id: str, *, judul: str, tentang: str | None, ringkasan: str | None,
                   articles: list[tuple[str, int | None, str]], sections: list[dict],
                   full_text: str | None) -> tuple[list[Chunk], dict[str, int]]:
    """Returns (chunks, stats). ``articles`` = [(number, page, text)]."""
    chunks: list[Chunk] = []
    stats = {"pasal": 0, "seksi": 0, "teks": 0, "dipotong": 0}

    head = " — ".join(x for x in (judul, tentang, (ringkasan or "")[:600]) if x)
    if head:
        chunks.append(Chunk(_cid(doc_id, "dokumen", None, 0), doc_id, "dokumen", None, 0, None,
                            " ".join(head.split()[:WINDOW_WORDS])))

    if articles:
        # A Surat Edaran can quote "Pasal 13" of several regulations; repeats
        # get an occurrence suffix so ids stay unique (first one unchanged).
        seen: dict[str, int] = {}
        for number, page, text in articles:
            occ = seen.get(number, 0)
            seen[number] = occ + 1
            key = number if occ == 0 else f"{number}#{occ}"
            for i, w in enumerate(windows(text)):
                chunks.append(Chunk(_cid(doc_id, "pasal", key, i), doc_id, "pasal", number, i, page, w))
            stats["pasal"] += 1
    elif sections and full_text and (bodies := section_bodies(sections, full_text)):
        seen_s: dict[str, int] = {}
        for label, page, body in bodies:
            occ = seen_s.get(label, 0)
            seen_s[label] = occ + 1
            for i, w in enumerate(windows(body)):
                key = label if occ == 0 else f"{label}#{occ}"
                chunks.append(Chunk(_cid(doc_id, "seksi", key, i), doc_id, "seksi", label[:80],
                                    i, page, w))
            stats["seksi"] += 1
    elif full_text:
        parts = windows(re.sub(r"\s+", " ", full_text))
        stats["dipotong"] = max(0, len(parts) - MAX_FALLBACK_WINDOWS)
        for i, w in enumerate(parts[:MAX_FALLBACK_WINDOWS]):
            chunks.append(Chunk(_cid(doc_id, "teks", None, i), doc_id, "teks", None, i, None, w))
        stats["teks"] = min(len(parts), MAX_FALLBACK_WINDOWS)
    return chunks, stats


def chunk_catalog(conn: sqlite3.Connection, doc_ids: list[str] | None = None) -> tuple[list[Chunk], dict]:
    """Chunk every document (or ``doc_ids``) using the read model + articles."""
    conn.row_factory = sqlite3.Row
    where = ""
    params: list = []
    if doc_ids is not None:
        if not doc_ids:
            return [], {}
        where = f"WHERE v.doc_id IN ({', '.join('?' for _ in doc_ids)})"
        params = list(doc_ids)
    docs = conn.execute(
        f"SELECT v.doc_id, v.judul, v.tentang, v.ringkasan, t.structure, t.full_text "
        f"FROM kb_document_view v LEFT JOIN document_text t USING (doc_id) {where}", params).fetchall()
    all_chunks: list[Chunk] = []
    totals = {"dokumen": 0, "pasal": 0, "seksi": 0, "teks": 0, "dipotong": 0}
    for d in docs:
        arts = [(r["number"], r["page"], r["text"]) for r in conn.execute(
            "SELECT number, page, text FROM articles WHERE doc_id = ? ORDER BY id", (d["doc_id"],))]
        structure = json.loads(d["structure"] or "{}")
        chunks, st = chunk_document(
            d["doc_id"], judul=d["judul"], tentang=d["tentang"], ringkasan=d["ringkasan"],
            articles=arts, sections=structure.get("sections") or [], full_text=d["full_text"])
        all_chunks.extend(chunks)
        totals["dokumen"] += 1
        for k, v in st.items():
            totals[k] += v
    return all_chunks, totals
