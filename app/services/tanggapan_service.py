"""
app/services/tanggapan_service.py
Layanan untuk pengelolaan kunci temuan harmonisasi, penandaan analis (#71),
dan penggabungan tanggapan ke dalam payload respons harmonisasi.
"""
import copy
import hashlib
import logging
from typing import Any, Dict, Union

from sqlalchemy.orm import Session

from app.models.tanggapan_temuan import TanggapanTemuan

logger = logging.getLogger("hero")


def _clean_field(val: Any) -> str:
    """Helper untuk menormalisasi nilai string: strip spasi, kecilkan huruf, rapikan spasi berlebih."""
    if val is None:
        return ""
    return " ".join(str(val).strip().lower().split())


def kunci_temuan(temuan: Union[Dict[str, Any], Any]) -> str:
    """
    Menghasilkan kunci hash SHA-256 (32 karakter hex, disimpan pada kolom DB varchar(64)) yang stabil untuk satu temuan harmonisasi.

    Bentuk temuan engine:
    - jenis: temuan.jenis
    - pasal_draft: temuan.pasal_draft
    - pembanding:
      - identitas: pembanding.key -> fallback pembanding.doc_id -> fallback pembanding.document_id
      - pasal: pembanding.pasal -> fallback temuan.pasal_pembanding (kompatibilitas ke belakang)
    - Untuk temuan pasal_baru (pembanding bernilai None / null), identitas dan pasal pembanding bernilai string kosong.

    Rumus stabil:
    jenis|pasal_draft|identitas_pembanding|pasal_pembanding (ternormalisasi), SHA-256 dipotong 32 karakter hex.
    """
    if hasattr(temuan, "model_dump"):
        t_dict = temuan.model_dump()
    elif isinstance(temuan, dict):
        t_dict = temuan
    else:
        t_dict = getattr(temuan, "__dict__", {})

    jenis_str = _clean_field(t_dict.get("jenis"))
    pasal_draft_str = _clean_field(t_dict.get("pasal_draft"))

    pembanding = t_dict.get("pembanding")
    if hasattr(pembanding, "model_dump"):
        p_dict = pembanding.model_dump()
    elif isinstance(pembanding, dict):
        p_dict = pembanding
    else:
        p_dict = getattr(pembanding, "__dict__", {}) if pembanding else {}

    # Prioritaskan pembanding.key, jika tidak ada fallback ke doc_id, lalu document_id
    pembanding_val = p_dict.get("key")
    if pembanding_val is None or str(pembanding_val).strip() == "":
        pembanding_val = p_dict.get("doc_id")
    if pembanding_val is None or str(pembanding_val).strip() == "":
        pembanding_val = p_dict.get("document_id")
    pembanding_str = _clean_field(pembanding_val)

    # Pasal pembanding: pembanding.pasal -> fallback ke pasal_pembanding top-level
    pasal_pembanding_val = p_dict.get("pasal")
    if pasal_pembanding_val is None or str(pasal_pembanding_val).strip() == "":
        pasal_pembanding_val = t_dict.get("pasal_pembanding")
    pasal_pembanding_str = _clean_field(pasal_pembanding_val)

    gabungan = f"{jenis_str}|{pasal_draft_str}|{pembanding_str}|{pasal_pembanding_str}"
    return hashlib.sha256(gabungan.encode("utf-8")).hexdigest()[:32]


def tandai_kunci_temuan(data: Union[Dict[str, Any], Any]) -> Union[Dict[str, Any], Any]:
    """
    Menerima hasil ML mentah dan mengembalikan deepcopy dengan field 'kunci_temuan'
    terisi pada setiap elemen di list 'temuan'. Data asli / cache analysis_results tidak termodifikasi.

    Kunci dihitung SEBELUM penyaringan rujukan sensitif agar kunci stabil antar pengguna
    yang memiliki hak akses berbeda atas dokumen pembanding.
    """
    if not isinstance(data, dict):
        return data

    data_copy = copy.deepcopy(data)
    temuan_list = data_copy.get("temuan")
    if isinstance(temuan_list, list):
        for item in temuan_list:
            if isinstance(item, dict):
                existing_key = item.get("kunci_temuan")
                if isinstance(existing_key, str) and len(existing_key) == 32 and all(c in "0123456789abcdefABCDEF" for c in existing_key):
                    item["kunci_temuan"] = existing_key.lower()
                else:
                    item["kunci_temuan"] = kunci_temuan(item)
    return data_copy


def gabungkan_tanggapan_ke_harmonisasi(
    db: Session,
    document_id: int,
    data: Union[Dict[str, Any], Any],
) -> Union[Dict[str, Any], Any]:
    """
    Menggabungkan tanggapan analis yang tersimpan di database ke dalam objek data respons harmonisasi:
    - Menambahkan 'kunci_temuan' pada setiap objek di list 'temuan'
    - Menambahkan 'tanggapan' ({penilaian, catatan, dinilai_oleh_nama, diperbarui} atau null)
    - Menambahkan rekap tanggapan pada 'ringkasan': {valid, tidak_relevan, belum_dinilai}

    PENTING: Fungsi ini bekerja pada salinan (deepcopy) daftar temuan dan ringkasan,
    sehingga data asli yang tersimpan di cache analysis_results tetap murni hasil keluaran layanan ML.
    """
    if not isinstance(data, dict):
        return data

    # Buat salinan aman agar cache / data sumber tidak termodifikasi
    data_copy = copy.copy(data)
    temuan_raw = data.get("temuan")
    if isinstance(temuan_raw, list):
        temuan_list = [copy.deepcopy(item) if isinstance(item, dict) else item for item in temuan_raw]
    else:
        temuan_list = []
    data_copy["temuan"] = temuan_list

    ringkasan_raw = data.get("ringkasan")
    if isinstance(ringkasan_raw, dict):
        ringkasan = copy.deepcopy(ringkasan_raw)
    else:
        ringkasan = {}
    data_copy["ringkasan"] = ringkasan

    # Ambil seluruh tanggapan aktif untuk dokumen draft ini
    records = (
        db.query(TanggapanTemuan)
        .filter(TanggapanTemuan.document_id == document_id)
        .all()
    )
    tanggapan_map: Dict[str, TanggapanTemuan] = {r.kunci_temuan: r for r in records}

    count_valid = 0
    count_tidak_relevan = 0
    count_belum_dinilai = 0

    for item in temuan_list:
        if not isinstance(item, dict):
            continue

        existing_key = item.get("kunci_temuan")
        if isinstance(existing_key, str) and len(existing_key) == 32 and all(c in "0123456789abcdefABCDEF" for c in existing_key):
            kunci = existing_key.lower()
            item["kunci_temuan"] = kunci
        else:
            kunci = kunci_temuan(item)
            item["kunci_temuan"] = kunci

        record = tanggapan_map.get(kunci)
        if record:
            item["tanggapan"] = {
                "penilaian": record.penilaian,
                "catatan": record.catatan,
                "dinilai_oleh_nama": record.dinilai_oleh_nama,
                "diperbarui": record.diperbarui.isoformat() if record.diperbarui else None,
            }
            if record.penilaian == "valid":
                count_valid += 1
            elif record.penilaian == "tidak_relevan":
                count_tidak_relevan += 1
            else:
                count_belum_dinilai += 1
        else:
            item["tanggapan"] = None
            count_belum_dinilai += 1

    ringkasan["tanggapan"] = {
        "valid": count_valid,
        "tidak_relevan": count_tidak_relevan,
        "belum_dinilai": count_belum_dinilai,
    }

    return data_copy
