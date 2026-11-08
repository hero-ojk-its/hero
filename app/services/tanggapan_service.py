"""
app/services/tanggapan_service.py
Layanan untuk pengelolaan kunci temuan harmonisasi, penandaan analis (#71),
dan penggabungan tanggapan ke dalam payload respons harmonisasi.
"""
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
    Menghasilkan kunci hash SHA-256 (32 karakter hex) yang stabil untuk satu temuan harmonisasi.

    Alasan arsitektural:
    ID temuan dari layanan ML (mis. 't-1234') tidak dijamin stabil antar eksekusi harmonisasi.
    Agar penandaan analis (valid / tidak_relevan) tetap menempel pada temuan yang sama
    walaupun harmonisasi dijalankan ulang dan 'id' dari ML berubah, kunci dihitung secara murni
    dari substansi temuan: kombinasi ternormalisasi jenis temuan, pasal draft, kunci/ID regulasi
    pembanding, dan pasal pembanding.
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

    # Prioritaskan pembanding.key, jika tidak ada/kosong fallback ke pembanding.document_id
    pembanding_val = p_dict.get("key")
    if pembanding_val is None or str(pembanding_val).strip() == "":
        pembanding_val = p_dict.get("document_id")
    pembanding_str = _clean_field(pembanding_val)

    pasal_pembanding_str = _clean_field(t_dict.get("pasal_pembanding"))

    gabungan = f"{jenis_str}|{pasal_draft_str}|{pembanding_str}|{pasal_pembanding_str}"
    return hashlib.sha256(gabungan.encode("utf-8")).hexdigest()[:32]


def gabungkan_tanggapan_ke_harmonisasi(
    db: Session,
    document_id: int,
    data: Dict[str, Any],
) -> Dict[str, Any]:
    """
    Menggabungkan tanggapan analis yang tersimpan di database ke dalam objek data respons harmonisasi:
    - Menambahkan 'kunci_temuan' pada setiap objek di list 'temuan'
    - Menambahkan 'tanggapan' ({penilaian, catatan, dinilai_oleh_nama, diperbarui} atau null)
    - Menambahkan rekap tanggapan pada 'ringkasan': {valid, tidak_relevan, belum_dinilai}

    PENTING: Fungsi ini dipanggil hanya pada dictionary respons sebelum dikembalikan ke klien,
    sehingga data yang tersimpan di cache analysis_results tetap murni hasil keluaran layanan ML.
    """
    if not isinstance(data, dict):
        return data

    # Ambil seluruh tanggapan aktif untuk dokumen draft ini
    records = (
        db.query(TanggapanTemuan)
        .filter(TanggapanTemuan.document_id == document_id)
        .all()
    )
    tanggapan_map: Dict[str, TanggapanTemuan] = {r.kunci_temuan: r for r in records}

    temuan_list = data.get("temuan")
    if not isinstance(temuan_list, list):
        temuan_list = []

    count_valid = 0
    count_tidak_relevan = 0
    count_belum_dinilai = 0

    for item in temuan_list:
        if not isinstance(item, dict):
            continue

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

    ringkasan = data.get("ringkasan")
    if not isinstance(ringkasan, dict):
        ringkasan = {}
        data["ringkasan"] = ringkasan

    ringkasan["tanggapan"] = {
        "valid": count_valid,
        "tidak_relevan": count_tidak_relevan,
        "belum_dinilai": count_belum_dinilai,
    }

    return data
