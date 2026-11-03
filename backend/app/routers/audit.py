from datetime import datetime
from typing import Optional, Literal, List, Dict, Any
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
import sqlalchemy as sa

from app.config import settings
from app.database import get_db
from app.models.audit_log import AuditLog
from app.core.permissions import perlu_izin_admin, Izin

router = APIRouter()


@router.get("/ringkasan", summary="Ringkasan Audit Log per Aksi")
def get_audit_summary(
    db: Session = Depends(get_db),
    admin_user=Depends(perlu_izin_admin(Izin.AUDIT_BACA)),
) -> List[Dict[str, Any]]:
    """
    Mengembalikan ringkasan statistik audit log per jenis aksi:
    - jumlah: total kemunculan aksi
    - jumlah_detail_kosong: jumlah baris dengan detail null atau kosong
    - terakhir: waktu kejadian terakhir
    """
    is_empty = sa.or_(
        AuditLog.detail.is_(None),
        sa.cast(AuditLog.detail, sa.String) == '{}',
        sa.cast(AuditLog.detail, sa.String) == 'null',
        sa.cast(AuditLog.detail, sa.String) == '""',
        sa.cast(AuditLog.detail, sa.String) == '',
    )
    kosong_case = sa.case((is_empty, 1), else_=0)

    results = (
        db.query(
            AuditLog.action,
            func.count(AuditLog.id).label("jumlah"),
            func.sum(kosong_case).label("jumlah_detail_kosong"),
            func.max(AuditLog.timestamp).label("terakhir"),
        )
        .group_by(AuditLog.action)
        .order_by(AuditLog.action.asc())
        .all()
    )
    return [
        {
            "action": row.action,
            "jumlah": row.jumlah,
            "jumlah_detail_kosong": int(row.jumlah_detail_kosong or 0),
            "terakhir": row.terakhir,
        }
        for row in results
    ]


@router.get("/", summary="Daftar Audit Log")
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    action: Optional[str] = Query(None, description="Filter berdasarkan kode aksi (misal: LOGIN, UPLOAD_DOCUMENT)"),
    user_id: Optional[int] = Query(None, description="Filter berdasarkan ID pengguna"),
    target_resource: Optional[str] = Query(None, description="Filter berdasarkan target resource (prefix match, misal: document:12)"),
    mode: Optional[Literal["deterministik", "ai"]] = Query(None, description="Filter berdasarkan mode analisa (detail->>'mode_dipakai')"),
    ada_detail: Optional[bool] = Query(None, description="Filter ketersediaan detail (true: tidak kosong; false: kosong)"),
    dari: Optional[datetime] = Query(None, description="Filter rentang awal waktu timestamp (inklusif)"),
    sampai: Optional[datetime] = Query(None, description="Filter rentang akhir waktu timestamp (inklusif)"),
    db: Session = Depends(get_db),
    admin_user=Depends(perlu_izin_admin(Izin.AUDIT_BACA)),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if target_resource:
        query = query.filter(AuditLog.target_resource.like(f"{target_resource}%"))
    if mode:
        query = query.filter(AuditLog.detail["mode_dipakai"].astext == mode)
    if ada_detail is True:
        is_filled = sa.and_(
            AuditLog.detail.isnot(None),
            sa.cast(AuditLog.detail, sa.String) != '{}',
            sa.cast(AuditLog.detail, sa.String) != 'null',
            sa.cast(AuditLog.detail, sa.String) != '""',
            sa.cast(AuditLog.detail, sa.String) != '',
        )
        query = query.filter(is_filled)
    elif ada_detail is False:
        is_empty = sa.or_(
            AuditLog.detail.is_(None),
            sa.cast(AuditLog.detail, sa.String) == '{}',
            sa.cast(AuditLog.detail, sa.String) == 'null',
            sa.cast(AuditLog.detail, sa.String) == '""',
            sa.cast(AuditLog.detail, sa.String) == '',
        )
        query = query.filter(is_empty)
    if dari is not None:
        query = query.filter(AuditLog.timestamp >= dari)
    if sampai is not None:
        query = query.filter(AuditLog.timestamp <= sampai)

    logs = query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()
    return [
        {
            "id": log.id,
            "user_id": log.user_id,
            "action": log.action,
            "target_resource": log.target_resource,
            "detail": log.detail,
            "ip_address": log.ip_address if settings.auth_enabled else None,
            "timestamp": log.timestamp,
        }
        for log in logs
    ]
