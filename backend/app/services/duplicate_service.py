"""
app/services/duplicate_service.py
Layanan deteksi dan penanganan duplikat identitas regulasi (Langkah 17).
"""
import logging
from datetime import datetime, timezone
from functools import cmp_to_key
from typing import List, Optional

from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.enums import PeranDokumen, StatusPemrosesan
from app.services.audit_service import DUPLICATE_IDENTITY_DETECTED, record_audit

logger = logging.getLogger("hero")


class DuplicateResult(BaseModel):
    identity_key: str
    kept_document_id: int
    deactivated_document_ids: List[int]
    rule: str  # "page_count" | "file_size" | "older"


def compare_docs(a: Document, b: Document) -> tuple[int, str]:
    """
    Membandingkan dua dokumen berdasarkan urutan prioritas pemenang:
    1. page_count lebih besar, bila keduanya diketahui (rule: "page_count")
    2. file_size_bytes lebih besar (rule: "file_size")
    3. bila masih seri, id lebih kecil / yang lebih dulu ada (rule: "older")

    Returns:
        (-1, rule) jika a menang atas b
        (1, rule) jika b menang atas a
        (0, rule) jika sama persis
    """
    # 1. page_count lebih besar, bila keduanya diketahui
    if a.page_count is not None and b.page_count is not None:
        if a.page_count > b.page_count:
            return (-1, "page_count")
        elif b.page_count > a.page_count:
            return (1, "page_count")

    # 2. file_size_bytes lebih besar
    size_a = a.file_size_bytes or 0
    size_b = b.file_size_bytes or 0
    if size_a > size_b:
        return (-1, "file_size")
    elif size_b > size_a:
        return (1, "file_size")

    # 3. bila masih seri, id lebih kecil (yang lebih dulu ada)
    id_a = a.id or 0
    id_b = b.id or 0
    if id_a < id_b:
        return (-1, "older")
    elif id_b < id_a:
        return (1, "older")

    return (0, "older")


def check_identity_duplicate(
    db: Session,
    doc: Document,
    actor_user_id: Optional[int] = None,
) -> Optional[DuplicateResult]:
    """
    Mengecek apakah dokumen memiliki duplikat identitas pada corpus eksisting.

    Aturan:
    - Abaikan bila doc.identity_key kosong, doc.document_role != corpus_eksisting, atau doc.is_active false.
    - Pasangan: dokumen lain dengan identity_key sama, document_role = corpus_eksisting,
      is_active = true, dan processing_status in ('terindeks', 'perlu_koreksi').
    - Pengecualian: dokumen yang pernah ditandai duplikat lalu diaktifkan kembali secara manual
      (duplicate_of_id terisi tetapi is_active = true) dianggap keputusan pengguna, jangan dinonaktifkan lagi.
    - Pemenang dipilih dengan urutan:
      1. page_count lebih besar (bila keduanya diketahui)
      2. file_size_bytes lebih besar
      3. id lebih kecil (lebih dulu ada)
    - Yang kalah dinonaktifkan (mekanisme US-30) dengan duplicate_of_id = id_pemenang.
    - Audit log DUPLICATE_IDENTITY_DETECTED dicatat.
    - Mengembalikan ringkasan DuplicateResult atau None jika tidak ada penonaktifan.
    """
    if not doc.identity_key or not doc.is_active:
        return None

    role_val = doc.document_role.value if hasattr(doc.document_role, "value") else str(doc.document_role)
    if role_val != PeranDokumen.corpus_eksisting.value:
        return None

    # Cari pasangan aktif dengan identity_key yang sama
    peers = (
        db.query(Document)
        .filter(
            Document.identity_key == doc.identity_key,
            Document.id != doc.id,
            Document.document_role == PeranDokumen.corpus_eksisting,
            Document.is_active == True,  # noqa: E712
            Document.processing_status.in_([
                StatusPemrosesan.terindeks,
                StatusPemrosesan.perlu_koreksi,
            ]),
        )
        .all()
    )

    if not peers:
        return None

    # Kumpulkan seluruh kandidat
    all_candidates = [doc] + peers

    # Urutkan berdasarkan komparator
    sorted_candidates = sorted(
        all_candidates,
        key=cmp_to_key(lambda a, b: compare_docs(a, b)[0]),
    )

    winner = sorted_candidates[0]
    losers = sorted_candidates[1:]

    deactivated_ids: List[int] = []
    applied_rule: Optional[str] = None

    now = datetime.now(timezone.utc)

    for loser in losers:
        # Pengecualian: Dokumen yang pernah duplikat lalu diaktifkan manual (duplicate_of_id is not None dan is_active=True)
        # jangan dinonaktifkan kembali secara otomatis.
        if loser.duplicate_of_id is not None and loser.is_active:
            logger.info(
                "Dokumen ID #%s diabaikan dari penonaktifan otomatis karena pernah diaktifkan secara manual.",
                loser.id,
            )
            continue

        _, rule_name = compare_docs(winner, loser)
        if applied_rule is None:
            applied_rule = rule_name

        loser.is_active = False
        loser.deactivated_at = now
        loser.deactivated_reason = f"duplikat_identitas: sama dengan dokumen #{winner.id} ({doc.identity_key})"
        loser.deactivated_by = actor_user_id
        loser.duplicate_of_id = winner.id
        deactivated_ids.append(loser.id)

    if not deactivated_ids:
        return None

    rule_final = applied_rule or "older"

    # Catat audit log
    record_audit(
        db,
        action=DUPLICATE_IDENTITY_DETECTED,
        user_id=actor_user_id,
        target_resource=f"document:{winner.id}",
        detail={
            "identity_key": doc.identity_key,
            "kept_document_id": winner.id,
            "deactivated_document_ids": deactivated_ids,
            "rule": rule_final,
        },
        commit=False,
    )

    db.flush()

    return DuplicateResult(
        identity_key=doc.identity_key,
        kept_document_id=winner.id,
        deactivated_document_ids=deactivated_ids,
        rule=rule_final,
    )
