"""
tests/test_docs_enums.py
Pengujian otomatis untuk memvalidasi nilai enum di semua contoh JSON pada docs/api/*.md.
Mencegah ketidakkonsistenan dokumentasi API terhadap models/enums.py.
"""
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Set
import pytest

from app.models.enums import (
    HasilTarik,
    JenisJobIngest,
    JenisKegagalan,
    JenisRujukan,
    JenisSumber,
    KlasifikasiAkses,
    MetodeEkstraksi,
    PeranDokumen,
    StatusJobIngest,
    StatusKandidat,
    StatusKeberlakuan,
    StatusPemrosesan,
    StatusPindai,
    StatusTindakLanjut,
    TujuanTarik,
)

# Himpunan nilai valid per key
VALID_ENUM_VALUES: Dict[str, Set[str]] = {
    "job_status": {e.value for e in StatusJobIngest},
    "processing_status": {e.value for e in StatusPemrosesan},
    "status_keberlakuan": {e.value for e in StatusKeberlakuan},
    "access_classification": {e.value for e in KlasifikasiAkses},
    "document_role": {e.value for e in PeranDokumen},
    "match_status": {e.value for e in StatusKandidat},
    "failure_type": {e.value for e in JenisKegagalan},
    "follow_up_status": {e.value for e in StatusTindakLanjut},
    "source_type": {e.value for e in JenisSumber},
    "destination": {e.value for e in TujuanTarik},
    "job_type": {e.value for e in JenisJobIngest},
    "pull_outcome": {e.value for e in HasilTarik} | {"success", "duplicate", "failed", "downloaded"},
    # Key 'status' mencocokkan gabungan enum status yang relevan di sistem HERO
    "status": (
        {e.value for e in StatusPindai}
        | {e.value for e in StatusJobIngest}
        | {e.value for e in StatusPemrosesan}
        | {e.value for e in StatusKeberlakuan}
        | {e.value for e in StatusTindakLanjut}
        | {"ok", "degraded", "error", "sukses", "gagal_dicatat", "requeued"}  # Status health / status respon aksi
    ),
}


def extract_json_blocks_from_markdown(md_content: str) -> List[str]:
    """Mengekstrak seluruh blok kode ```json ... ``` dari markdown."""
    pattern = r"```json\s*\n(.*?)\n```"
    return re.findall(pattern, md_content, flags=re.DOTALL)


def check_dict_enums(data: Any, path: str = "", errors: List[str] = None) -> List[str]:
    """Rekursif memeriksa setiap key/value pada struktur JSON terhadap kamus enum."""
    if errors is None:
        errors = []

    if isinstance(data, dict):
        for k, v in data.items():
            current_path = f"{path}.{k}" if path else k
            if k in VALID_ENUM_VALUES:
                if isinstance(v, str):
                    if v not in VALID_ENUM_VALUES[k]:
                        errors.append(
                            f"Key '{current_path}' memiliki nilai '{v}' yang tidak valid. "
                            f"Nilai yang diizinkan: {sorted(list(VALID_ENUM_VALUES[k]))}"
                        )
                elif isinstance(v, list):
                    for item in v:
                        if isinstance(item, str) and item not in VALID_ENUM_VALUES[k]:
                            errors.append(
                                f"Item array pada '{current_path}' bernilai '{item}' yang tidak valid. "
                                f"Nilai yang diizinkan: {sorted(list(VALID_ENUM_VALUES[k]))}"
                            )
            # Rekursif ke children
            check_dict_enums(v, current_path, errors)

    elif isinstance(data, list):
        for idx, item in enumerate(data):
            check_dict_enums(item, f"{path}[{idx}]", errors)

    return errors


def test_docs_api_enum_validity():
    """Memindai seluruh docs/api/*.md dan memastikan semua nilai enum valid."""
    docs_dir = Path("docs/api")
    assert docs_dir.exists(), "Direktori docs/api tidak ditemukan!"

    md_files = list(docs_dir.glob("*.md"))
    assert len(md_files) > 0, "Tidak ada file markdown di docs/api!"

    all_errors = []

    for md_file in md_files:
        content = md_file.read_text(encoding="utf-8")
        blocks = extract_json_blocks_from_markdown(content)

        for block_idx, block in enumerate(blocks, start=1):
            # Coba parse JSON (abaikan jika contoh parsial / placeholder ellipsis)
            clean_block = re.sub(r",\s*\.\.\.", "", block)
            clean_block = re.sub(r"\.\.\.", "", clean_block)
            clean_block = re.sub(r"//.*", "", clean_block)  # Hapus komentar jika ada
            try:
                parsed = json.loads(clean_block)
            except json.JSONDecodeError:
                # Lewati blok yang sengaja bukan JSON murni / hanya potongan sintaks
                continue

            errors = check_dict_enums(parsed, path="")
            for err in errors:
                all_errors.append(f"[{md_file.name} Block #{block_idx}] {err}")

    assert not all_errors, "Ditemukan ketidakkonsistenan enum pada dokumentasi API:\n" + "\n".join(all_errors)


def test_docs_enums_validation_failure_on_invalid_fixture():
    """R03: Memastikan test_docs_enums akan GAGAL jika disisipkan nilai enum palsu."""
    fake_json = {
        "status": "status_palsu_tidak_dikenal",
        "job_status": "memproses_palsu",
        "access_classification": "rahasia_palsu",
    }
    errors = check_dict_enums(fake_json)
    assert len(errors) == 3
    assert any("status_palsu_tidak_dikenal" in e for e in errors)
    assert any("memproses_palsu" in e for e in errors)
    assert any("rahasia_palsu" in e for e in errors)
