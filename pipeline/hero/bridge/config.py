"""Konfigurasi jembatan ke backend tim.

Dibaca dari blok ``bridge:`` di ``config/sources.yaml`` (aturan domain di
konfigurasi — ADR-07), kecuali **rahasia**: kunci API internal hanya dibaca
dari environment / ``.env`` (invarian 3 — rahasia tidak masuk repo, dan YAML
ikut tersalin ke mana-mana).

Sengaja tidak menempel di ``hero.config.Settings``: jembatan adalah lapisan
opsional. Mode Deterministik dan seluruh CLI harus tetap jalan tanpa backend,
tanpa jaringan, dan tanpa blok ``bridge:`` sama sekali.
"""
from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

ENV_URL = "HERO_BACKEND_URL"
ENV_KEY = "HERO_BACKEND_INTERNAL_KEY"
# Nama yang dipakai backend di .env-nya sendiri; diterima sebagai alias supaya
# satu .env bisa dipakai bersama saat worker jalan di host yang sama.
ENV_KEY_ALIAS = "INTERNAL_API_KEY"


@dataclass
class BridgeSettings:
    """Semua yang menentukan bagaimana worker bicara dengan backend."""

    base_url: str = "http://127.0.0.1:8000"
    api_key: str = ""
    timeout: float = 60.0
    verify_tls: bool = True
    # Jeda antar-polling saat antrian kosong. Backend memberi 202/daftar kosong,
    # jadi polling adalah kontraknya — bukan pilihan kami.
    poll_seconds: float = 5.0
    claim_scans: int = 1              # batas backend: 1..5
    claim_documents: int = 5          # batas backend: 1..50
    batch_candidates: int = 200       # kandidat per POST .../candidates
    batch_articles: int = 150         # pasal per POST /internal/articles
    # Embedding yang dikirim ke kolom pgvector backend.
    #   lsa       deterministik, tanpa unduh model — jalan offline (URD 3.1)
    #   semantic  model lokal ONNX (minilm/e5-large) — lapisan AI-Assisted
    #   none      pasal dikirim tanpa vektor; backend tetap punya teksnya
    embedder: str = "lsa"
    # Dimensi kolom ``articles.embedding`` di backend. Vektor yang lebih pendek
    # di-zero-pad: untuk vektor ber-norma 1, padding nol tidak mengubah dot
    # product maupun norma, jadi cosine similarity-nya persis sama (lihat
    # hero/bridge/embed.py). Ubah hanya bila backend mengubah kolomnya.
    backend_dim: int = 1536
    send_full_text: bool = True
    # Backend hanya mengindeks 300.000 karakter pertama (kolom search_vector),
    # jadi mengirim lebih dari itu hanya menambah beban transfer.
    max_full_text_chars: int = 300_000
    # Ayat belum bisa dikirim sebagai anak pasal: skema bulk backend tidak
    # punya ``parent_id``/``parent_index`` (lihat docs/INTEGRASI_BACKEND.md §gap).
    push_ayat: bool = False
    # Dokumen non-publik tidak boleh keluar server. Worker ekstraksi berjalan
    # di sisi server, jadi defaultnya aman; penjaga ini mencegah lapisan AI
    # opsional ikut terpanggil untuk dokumen ber-NDA.
    allow_internal_to_ai: bool = False
    # Sumber yang dipakai worker pindai bila sesi pindai backend tidak
    # mencocokkan sumber manapun di sources.yaml.
    default_scan_adapter: str = "auto"
    # Batas atas kandidat per sesi pindai, di sisi worker. Backend meminta
    # sampai CRAWL_MAX_CANDIDATES (bawaan 5000); satu rekaman = satu halaman
    # detail yang dibaca, jadi angka itu berarti ribuan permintaan ke situs
    # regulasi dalam satu sesi. Batas ini adalah anggaran kesopanan scraping
    # (robots.txt + jeda per host sudah dipatuhi; ini membatasi volumenya).
    # None = ikuti apa pun yang diminta backend.
    max_candidates_cap: int | None = 500
    extra: dict[str, Any] = field(default_factory=dict)

    def url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}/{path.lstrip('/')}"

    @property
    def configured(self) -> bool:
        return bool(self.base_url and self.api_key)

    def redacted(self) -> dict[str, Any]:
        """Tampilan aman untuk log dan laporan: kunci API tidak pernah dicetak."""
        return {"base_url": self.base_url,
                "api_key": f"<diset, {len(self.api_key)} karakter>" if self.api_key else "<kosong>",
                "embedder": self.embedder, "backend_dim": self.backend_dim,
                "claim_documents": self.claim_documents, "poll_seconds": self.poll_seconds}


def _env_key() -> str:
    return (os.environ.get(ENV_KEY) or os.environ.get(ENV_KEY_ALIAS) or "").strip()


def load_bridge_settings(config: str | Path | None = "config/sources.yaml",
                         **overrides: Any) -> BridgeSettings:
    """Baca blok ``bridge:`` dari YAML, lalu timpa dengan environment & argumen.

    Urutan menang: argumen eksplisit > environment > YAML > default. Kunci API
    tidak pernah diambil dari YAML meski ditulis di sana (akan diabaikan).
    """
    from hero.config import _load_dotenv

    _load_dotenv()
    raw: dict[str, Any] = {}
    path = Path(config) if config else None
    if path and path.exists():
        doc = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
        raw = dict((doc.get("bridge") or {}))
    raw.pop("api_key", None)          # rahasia tidak dibaca dari YAML

    known = {f for f in BridgeSettings.__dataclass_fields__ if f != "extra"}
    extra = {k: v for k, v in raw.items() if k not in known}
    kwargs = {k: v for k, v in raw.items() if k in known}

    if env_url := os.environ.get(ENV_URL, "").strip():
        kwargs["base_url"] = env_url
    if key := _env_key():
        kwargs["api_key"] = key
    kwargs.update({k: v for k, v in overrides.items() if v is not None})
    if extra:
        kwargs["extra"] = extra
    return BridgeSettings(**kwargs)
