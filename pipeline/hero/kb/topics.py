"""Controlled topic vocabulary for the Knowledge Base "Topik" filter.

The extractive analysis (``extract/summary.py``) already produces topic
*terms* — raw n-grams such as "perusahaan pembiayaan" or "laporan bulanan".
Those are good evidence but a poor filter: every document gets a different
set, so a dropdown built from them would have thousands of entries.

The UI needs a short, stable list ("Ketahanan Siber", "Tata Kelola",
"Manajemen Risiko", …). This module maps each document onto that list with
keyword rules over title, subject and the extracted terms — deterministic
(URD 3.1), explainable (every assignment carries the keyword that fired) and
cheap enough to recompute on every ingest.

A document can carry several topics; the first one is its *primary* topic,
shown in the table column. Order in ``TOPIC_RULES`` breaks ties, so more
specific topics are listed before broad ones.
"""
from __future__ import annotations

import re
from dataclasses import dataclass

# (label, keywords). Keywords are matched as whole words, case-insensitive,
# against "title + subject + topic terms". Specific before broad.
TOPIC_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("Ketahanan Siber", ("siber", "keamanan informasi", "cyber", "ketahanan dan keamanan")),
    ("Teknologi Informasi", ("teknologi informasi", "digital", "elektronik", "inovasi keuangan",
                             "fintech", "layanan pendanaan", "pinjam meminjam", "sandbox")),
    ("APU-PPT", ("pencucian uang", "pendanaan terorisme", "apu", "ppt", "senjata pemusnah")),
    ("Perlindungan Konsumen", ("perlindungan konsumen", "konsumen", "pengaduan", "literasi",
                               "inklusi keuangan", "sengketa")),
    ("Manajemen Risiko", ("manajemen risiko", "tingkat risiko", "risiko kredit", "profil risiko",
                          "penilaian sendiri", "aset tertimbang", "berdasarkan risiko",
                          "berbasis risiko")),
    ("Tata Kelola", ("tata kelola", "direksi", "dewan komisaris", "kepatuhan", "audit intern",
                     "fungsi kepatuhan", "komite")),
    ("Permodalan & Likuiditas", ("modal", "permodalan", "likuiditas", "kecukupan modal",
                                 "rasio", "ekuitas")),
    ("Pelaporan", ("laporan", "pelaporan", "laporan bulanan", "laporan berkala",
                   "laporan keuangan", "transparansi")),
    ("Perizinan & Kelembagaan", ("perizinan", "izin usaha", "pendirian", "kelembagaan",
                                 "penggabungan", "peleburan", "pengambilalihan", "pencabutan izin")),
    ("Keuangan Syariah", ("syariah", "sukuk", "akad")),
    ("Pasar Modal & Efek", ("efek", "penawaran umum", "emiten", "reksa dana", "bursa",
                            "perusahaan terbuka", "prospektus", "obligasi", "karbon")),
    ("Asuransi & Dana Pensiun", ("asuransi", "reasuransi", "dana pensiun", "penjaminan")),
    ("Pembiayaan & Pergadaian", ("pembiayaan", "pergadaian", "modal ventura", "multifinance")),
    ("Sanksi & Penegakan", ("sanksi", "perintah tertulis", "pemeriksaan", "penyidikan")),
    ("Kepegawaian Internal", ("cuti", "pegawai", "perjalanan dinas", "fasilitas perjalanan",
                              "remunerasi pegawai")),
)
FALLBACK_TOPIC = "Umum"

_COMPILED = tuple(
    (label, re.compile(r"\b(" + "|".join(re.escape(k) for k in kws) + r")\b", re.I))
    for label, kws in TOPIC_RULES
)


@dataclass(frozen=True)
class TopicHit:
    label: str
    keyword: str        # the word that triggered it — shown as the reason
    field: str          # "judul" | "tentang" | "istilah"


def assign_topics(title: str | None, subject: str | None,
                  terms: list[str] | None = None, *, limit: int = 3) -> list[TopicHit]:
    """Up to ``limit`` topics, strongest evidence first.

    Evidence in the title outranks the subject, which outranks extracted
    terms: the title is what the regulator chose to call the regulation,
    while terms come from anywhere in the body — including a passing mention
    of "laporan" in a document that is really about something else.
    """
    fields = (("judul", title or ""), ("tentang", subject or ""),
              ("istilah", " ; ".join(terms or [])))
    hits: list[tuple[int, int, TopicHit]] = []
    for rank, (label, pattern) in enumerate(_COMPILED):
        for strength, (fname, text) in enumerate(fields):
            m = pattern.search(text)
            if m:
                hits.append((strength, rank, TopicHit(label, m.group(1).lower(), fname)))
                break
    hits.sort(key=lambda h: (h[0], h[1]))
    return [h[2] for h in hits[:limit]]


def primary_topic(title: str | None, subject: str | None,
                  terms: list[str] | None = None) -> str:
    found = assign_topics(title, subject, terms, limit=1)
    return found[0].label if found else FALLBACK_TOPIC


ALL_TOPICS: tuple[str, ...] = tuple(label for label, _ in TOPIC_RULES) + (FALLBACK_TOPIC,)
