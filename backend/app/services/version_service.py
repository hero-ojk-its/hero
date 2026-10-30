"""
app/services/version_service.py
Layanan versioning regulasi: relasi mengubah/mencabut, rekonsiliasi status, dan riwayat versi.
"""
from datetime import date, datetime, timezone
import logging
import re
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set, Tuple, Union

from sqlalchemy.orm import Session

from app.models.document import Document
from app.models.document_relation import DocumentRelation
from app.models.enums import JenisRelasi, KlasifikasiAkses, StatusKeberlakuan
from app.services.audit_service import STATUS_FROM_RELATION, record_audit

logger = logging.getLogger("hero")


def parse_identity_key_sort(key: str) -> Tuple[int, int, str]:
    """
    Ekstrak (tahun, nomor, key) dari identity_key (JENIS|NOMOR|TAHUN)
    untuk pengurutan kronologis perubahan dari yang paling lama.
    """
    if not key:
        return (9999, 9999, "")

    parts = key.split("|")
    year = 9999
    num = 9999

    if len(parts) >= 3:
        try:
            year = int(parts[2].strip())
        except Exception:
            m_yr = re.search(r"\d{4}", parts[2])
            year = int(m_yr.group(0)) if m_yr else 9999

        raw_num = parts[1].strip()
        m_num = re.search(r"\d+", raw_num)
        if m_num:
            try:
                num = int(m_num.group(0))
            except Exception:
                num = 9999
    elif len(parts) == 2:
        m_yr = re.search(r"\d{4}", parts[1])
        if m_yr:
            year = int(m_yr.group(0))

    return (year, num, key)


def is_doc_accessible(doc: Document, user: Optional[Any] = None) -> bool:
    """
    Memeriksa apakah dokumen boleh diakses oleh pengguna.
    Dalam mode lindung, dokumen non-publik tidak boleh diakses bila pengguna tidak memiliki izin.
    """
    from app.core.permissions import boleh_baca_nonpublik

    if doc.access_classification == KlasifikasiAkses.non_publik:
        if not boleh_baca_nonpublik(user):
            return False
    return True


is_accessible = is_doc_accessible


def recompute_status(
    db: Session,
    documents: Union[Sequence[Document], Document, None] = None,
    target_keys: Optional[Iterable[str]] = None,
    node_status_map: Optional[Dict[str, StatusKeberlakuan]] = None,
    commit: bool = True,
) -> int:
    """
    Menghitung ulang status_keberlakuan dokumen berdasarkan aturan relasi hukum dan tanggal berlaku (Langkah 19):
    1. status_source == "manual" -> jangan diubah.
    2. Ada relasi masuk mencabut dengan partial=false -> dicabut (relasi).
    3. Lapisan data mengirim status node dicabut untuk kunci ini -> dicabut (lapisan_data).
    4. Ada relasi masuk mengubah, atau mencabut dengan partial=true -> diubah (relasi).
    5. Lapisan data mengirim status node lain (berlaku / diubah) -> pakai status itu (lapisan_data).
    5a. Tidak ada relasi masuk, dan status_source in {None, relasi, tanggal_berlaku},
        dan effective_date terisi dan <= hari ini -> berlaku, status_source = "tanggal_berlaku", rule: "tanggal_berlaku".
    6. Tidak ada aturan yang berlaku, tetapi status_source == "relasi" -> kembalikan ke tidak_diketahui, status_source = None, rule: "relasi_dihapus".
    7. Selain itu -> biarkan.

    Ketentuan khusus:
    - Dokumen lampiran (is_attachment=True) hanya menjalankan aturan 5a.
    - Dokumen tanpa identity_key tetap menjalankan aturan 5a (relasi tidak relevan).
    """
    if documents is None:
        if target_keys:
            documents = (
                db.query(Document)
                .filter(Document.identity_key.in_(list(target_keys)), Document.is_active == True)
                .all()
            )
        else:
            return 0
    elif isinstance(documents, Document):
        documents = [documents]

    changed_count = 0
    today = date.today()

    for doc in documents:
        # 1. Keputusan pengguna manual menang
        if doc.status_source == "manual":
            continue

        target_status: Optional[StatusKeberlakuan] = None
        target_source: Optional[str] = None
        rule_matched: Optional[str] = None

        is_attachment = bool(getattr(doc, "is_attachment", False))

        if is_attachment:
            # Dokumen lampiran: hanya menjalankan aturan tanggal berlaku
            if (
                doc.status_source in (None, "relasi", "tanggal_berlaku")
                and doc.effective_date
            ):
                if doc.effective_date <= today:
                    target_status = StatusKeberlakuan.berlaku
                    target_source = "tanggal_berlaku"
                    rule_matched = "tanggal_berlaku"
                else:
                    target_status = StatusKeberlakuan.belum_berlaku
                    target_source = "tanggal_berlaku"
                    rule_matched = "belum_berlaku"
            else:
                continue
        else:
            in_rels: List[DocumentRelation] = []
            node_st: Optional[StatusKeberlakuan] = None

            if doc.identity_key:
                in_rels = (
                    db.query(DocumentRelation)
                    .filter(DocumentRelation.target_key == doc.identity_key)
                    .all()
                )
                if node_status_map:
                    node_st = node_status_map.get(doc.identity_key)

            has_full_repeal = any(
                r.relation == JenisRelasi.mencabut and not r.partial for r in in_rels
            )
            has_amendment = any(
                r.relation == JenisRelasi.mengubah or (r.relation == JenisRelasi.mencabut and r.partial)
                for r in in_rels
            )

            if has_full_repeal:
                # 2. Ada relasi masuk mencabut dengan partial=false -> dicabut (relasi)
                target_status = StatusKeberlakuan.dicabut
                target_source = "relasi"
                rule_matched = "mencabut_penuh"
            elif node_st == StatusKeberlakuan.dicabut:
                # 3. Lapisan data mengirim status node dicabut untuk kunci ini -> dicabut (lapisan_data)
                target_status = StatusKeberlakuan.dicabut
                target_source = "lapisan_data"
                rule_matched = "lapisan_data"
            elif has_amendment:
                # 4. Ada relasi masuk mengubah, atau mencabut dengan partial=true -> diubah (relasi)
                target_status = StatusKeberlakuan.diubah
                target_source = "relasi"
                rule_matched = "mengubah_atau_mencabut_sebagian"
            elif node_st in (StatusKeberlakuan.berlaku, StatusKeberlakuan.diubah):
                # 5. Lapisan data mengirim status node lain (berlaku / diubah) -> pakai status itu (lapisan_data)
                target_status = node_st
                target_source = "lapisan_data"
                rule_matched = "lapisan_data"
            elif (
                len(in_rels) == 0
                and doc.status_source in (None, "relasi", "tanggal_berlaku")
                and doc.effective_date
            ):
                # 5a. Tidak ada relasi masuk, dan status_source in {None, relasi, tanggal_berlaku},
                #     dan effective_date terisi
                if doc.effective_date <= today:
                    target_status = StatusKeberlakuan.berlaku
                    target_source = "tanggal_berlaku"
                    rule_matched = "tanggal_berlaku"
                else:
                    target_status = StatusKeberlakuan.belum_berlaku
                    target_source = "tanggal_berlaku"
                    rule_matched = "belum_berlaku"
            elif doc.status_source == "relasi":
                # 6. Tidak ada aturan yang berlaku, tetapi status_source == "relasi" -> kembalikan ke tidak_diketahui, status_source = None
                target_status = StatusKeberlakuan.tidak_diketahui
                target_source = None
                rule_matched = "relasi_dihapus"
            else:
                # 7. Selain itu -> biarkan
                continue

        before_status = doc.status_keberlakuan
        before_source = doc.status_source

        if doc.status_keberlakuan != target_status or doc.status_source != target_source:
            doc.status_keberlakuan = target_status
            doc.status_source = target_source

            record_audit(
                db,
                action=STATUS_FROM_RELATION,
                target_resource=f"document:{doc.id}",
                detail={
                    "identity_key": doc.identity_key,
                    "before": before_status.value if hasattr(before_status, "value") else str(before_status),
                    "after": target_status.value if hasattr(target_status, "value") else str(target_status),
                    "before_source": before_source,
                    "after_source": target_source,
                    "rule": rule_matched,
                },
                commit=False,
            )
            changed_count += 1

    if commit and changed_count > 0:
        db.commit()

    return changed_count


def sync_relations(
    db: Session,
    relations_data: List[Dict[str, Any]],
    nodes_data: Optional[List[Dict[str, Any]]] = None,
    replace_all: bool = False,
) -> Dict[str, int]:
    """
    Sinkronisasi graf relasi dokumen dari lapisan data (POST /internal/relations).
    """
    valid_rels: List[Dict[str, Any]] = []
    skipped = 0
    inserted = 0
    updated = 0
    deleted = 0
    touched_keys: Set[str] = set()

    for item in relations_data:
        src = (item.get("src") or "").strip()
        dst = (item.get("dst") or "").strip()
        raw_rel = (item.get("rel") or "").strip().lower()

        if not src or not dst:
            skipped += 1
            continue

        if raw_rel not in (JenisRelasi.mengubah.value, JenisRelasi.mencabut.value):
            skipped += 1
            continue

        rel_enum = JenisRelasi(raw_rel)
        partial_bool = bool(item.get("sebagian", False))
        pasal = item.get("pasal_terkait")
        asal = item.get("asal")
        bukti = item.get("bukti")
        evidence_clean = bukti[:2000] if bukti else None

        valid_rels.append({
            "source_key": src,
            "target_key": dst,
            "relation": rel_enum,
            "partial": partial_bool,
            "articles_text": pasal,
            "origin": asal,
            "evidence": evidence_clean,
        })
        touched_keys.add(src)
        touched_keys.add(dst)

    # 1. Upsert relasi
    valid_combos: Set[Tuple[str, str, JenisRelasi]] = set()

    for r in valid_rels:
        combo = (r["source_key"], r["target_key"], r["relation"])
        valid_combos.add(combo)

        existing = (
            db.query(DocumentRelation)
            .filter(
                DocumentRelation.source_key == r["source_key"],
                DocumentRelation.target_key == r["target_key"],
                DocumentRelation.relation == r["relation"],
            )
            .first()
        )

        if existing:
            existing.partial = r["partial"]
            existing.articles_text = r["articles_text"]
            existing.origin = r["origin"]
            existing.evidence = r["evidence"]
            existing.updated_at = datetime.now(timezone.utc)
            updated += 1
        else:
            new_rel = DocumentRelation(
                source_key=r["source_key"],
                target_key=r["target_key"],
                relation=r["relation"],
                partial=r["partial"],
                articles_text=r["articles_text"],
                origin=r["origin"],
                evidence=r["evidence"],
            )
            db.add(new_rel)
            inserted += 1

    # 2. replace_all: hapus relasi yang tidak ada di payload
    if replace_all:
        all_existing = db.query(DocumentRelation).all()
        for rel in all_existing:
            rel_combo = (rel.source_key, rel.target_key, rel.relation)
            if rel_combo not in valid_combos:
                touched_keys.add(rel.source_key)
                touched_keys.add(rel.target_key)
                db.delete(rel)
                deleted += 1

        docs_with_rel_source = (
            db.query(Document.identity_key)
            .filter(
                Document.status_source == "relasi",
                Document.is_active == True,
                Document.identity_key.isnot(None),
            )
            .all()
        )
        for (rk,) in docs_with_rel_source:
            if rk:
                touched_keys.add(rk)

    db.flush()

    # 3. Proses node status dari lapisan data
    node_status_map: Dict[str, StatusKeberlakuan] = {}
    if nodes_data:
        valid_statuses = {
            StatusKeberlakuan.berlaku.value: StatusKeberlakuan.berlaku,
            StatusKeberlakuan.diubah.value: StatusKeberlakuan.diubah,
            StatusKeberlakuan.dicabut.value: StatusKeberlakuan.dicabut,
        }
        if isinstance(nodes_data, dict):
            for k, st_raw in nodes_data.items():
                k_clean = str(k).strip()
                st = str(st_raw).strip().lower()
                if k_clean and st in valid_statuses:
                    node_status_map[k_clean] = valid_statuses[st]
                    touched_keys.add(k_clean)
        elif isinstance(nodes_data, list):
            for n in nodes_data:
                if isinstance(n, dict):
                    k = (n.get("key") or n.get("identity_key") or "").strip()
                    st = (n.get("status") or "").strip().lower()
                elif hasattr(n, "key"):
                    k = (n.key or "").strip()
                    st = (n.status or "").strip().lower()
                else:
                    continue
                if k and st in valid_statuses:
                    node_status_map[k] = valid_statuses[st]
                    touched_keys.add(k)

    # 4. Hitung ulang status untuk semua dokumen aktif yang disentuh
    docs_to_recompute = (
        db.query(Document)
        .filter(Document.identity_key.in_(list(touched_keys)), Document.is_active == True)
        .all()
    )

    documents_status_changed = recompute_status(
        db,
        documents=docs_to_recompute,
        node_status_map=node_status_map,
        commit=False,
    )

    db.commit()

    return {
        "inserted": inserted,
        "updated": updated,
        "skipped": skipped,
        "deleted": deleted,
        "documents_status_changed": documents_status_changed,
    }


def get_versioning_details(
    db: Session,
    doc: Document,
    current_user: Optional[Any] = None,
) -> Dict[str, Any]:
    """
    Menyiapkan data versioning untuk endpoint GET /documents/{id}/versi.
    """
    my_key = doc.identity_key

    # Dokumen tanpa identity_key -> 200 daftar kosong + catatan
    if not my_key:
        return {
            "document_id": doc.id,
            "identity_key": None,
            "status_keberlakuan": doc.status_keberlakuan.value if doc.status_keberlakuan else "tidak_diketahui",
            "status_source": doc.status_source,
            "induk": [],
            "diubah_oleh": [],
            "dicabut_oleh": [],
            "mencabut": [],
            "catatan": "Dokumen belum memiliki kunci identitas (identity_key); relasi versi belum dapat dipetakan.",
        }

    # 1. Relasi KELUAR dari dokumen ini (source_key == my_key)
    out_amends = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.source_key == my_key,
            DocumentRelation.relation == JenisRelasi.mengubah,
        )
        .all()
    )
    out_repeals = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.source_key == my_key,
            DocumentRelation.relation == JenisRelasi.mencabut,
        )
        .all()
    )

    # 2. Relasi MASUK ke dokumen ini (target_key == my_key)
    in_amends = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.target_key == my_key,
            DocumentRelation.relation == JenisRelasi.mengubah,
        )
        .all()
    )
    in_repeals = (
        db.query(DocumentRelation)
        .filter(
            DocumentRelation.target_key == my_key,
            DocumentRelation.relation == JenisRelasi.mencabut,
        )
        .all()
    )

    # Kumpulkan semua kunci yang perlu di-resolve ke Document KB
    needed_keys: Set[str] = set()
    for r in out_amends:
        needed_keys.add(r.target_key)
    for r in out_repeals:
        needed_keys.add(r.target_key)
    for r in in_amends:
        needed_keys.add(r.source_key)
    for r in in_repeals:
        needed_keys.add(r.source_key)

    doc_map: Dict[str, Document] = {}
    if needed_keys:
        found_docs = (
            db.query(Document)
            .filter(Document.identity_key.in_(list(needed_keys)), Document.is_active == True)
            .all()
        )
        for d in found_docs:
            if d.identity_key:
                doc_map[d.identity_key] = d

    def resolve_doc(k: str) -> Tuple[Optional[int], Optional[str]]:
        d = doc_map.get(k)
        if d and is_doc_accessible(d, current_user):
            return d.id, d.title
        return None, None

    # Hitung diubah_oleh: urutkan dari tahun lalu nomor yang paling lama (perubahan ke-1, ke-2, ...)
    sorted_in_amends = sorted(in_amends, key=lambda r: parse_identity_key_sort(r.source_key))
    diubah_oleh_list = []
    for idx, r in enumerate(sorted_in_amends, start=1):
        d_id, judul = resolve_doc(r.source_key)
        diubah_oleh_list.append({
            "key": r.source_key,
            "perubahan_ke": idx,
            "document_id": d_id,
            "judul": judul,
            "pasal_terkait": r.articles_text,
        })

    # Hitung dicabut_oleh
    dicabut_oleh_list = []
    sorted_in_repeals = sorted(in_repeals, key=lambda r: parse_identity_key_sort(r.source_key))
    for r in sorted_in_repeals:
        d_id, judul = resolve_doc(r.source_key)
        dicabut_oleh_list.append({
            "key": r.source_key,
            "sebagian": r.partial,
            "document_id": d_id,
            "judul": judul,
            "pasal_terkait": r.articles_text,
        })

    # Hitung mencabut
    mencabut_list = []
    sorted_out_repeals = sorted(out_repeals, key=lambda r: parse_identity_key_sort(r.target_key))
    for r in sorted_out_repeals:
        d_id, judul = resolve_doc(r.target_key)
        mencabut_list.append({
            "key": r.target_key,
            "sebagian": r.partial,
            "document_id": d_id,
            "judul": judul,
            "pasal_terkait": r.articles_text,
        })

    # Hitung induk: untuk setiap induk, tentukan perubahan_ke dokumen ini di antara pengubah induk tersebut
    induk_list = []
    for r in out_amends:
        parent_key = r.target_key
        # Ambil semua pengubah induk tersebut dari tabel relasi
        all_parent_modifiers = (
            db.query(DocumentRelation)
            .filter(
                DocumentRelation.target_key == parent_key,
                DocumentRelation.relation == JenisRelasi.mengubah,
            )
            .all()
        )
        sorted_modifiers = sorted(all_parent_modifiers, key=lambda x: parse_identity_key_sort(x.source_key))
        perubahan_ke = 1
        for m_idx, mod in enumerate(sorted_modifiers, start=1):
            if mod.source_key == my_key:
                perubahan_ke = m_idx
                break

        d_id, judul = resolve_doc(parent_key)
        induk_list.append({
            "key": parent_key,
            "relasi": "mengubah",
            "sebagian": r.partial,
            "perubahan_ke": perubahan_ke,
            "document_id": d_id,
            "judul": judul,
            "pasal_terkait": r.articles_text,
        })

    return {
        "document_id": doc.id,
        "identity_key": my_key,
        "status_keberlakuan": doc.status_keberlakuan.value if doc.status_keberlakuan else "tidak_diketahui",
        "status_source": doc.status_source,
        "induk": induk_list,
        "diubah_oleh": diubah_oleh_list,
        "dicabut_oleh": dicabut_oleh_list,
        "mencabut": mencabut_list,
        "catatan": "Draft / Rekomendasi — status dihitung dari relasi antarperaturan; periksa teks resmi.",
    }
