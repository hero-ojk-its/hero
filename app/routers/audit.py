from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.routers.auth import get_current_admin

router = APIRouter()


@router.get("/", summary="Daftar Audit Log")
def get_audit_logs(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=500),
    action: Optional[str] = Query(None, description="Filter berdasarkan kode aksi (misal: LOGIN, UPLOAD_DOCUMENT)"),
    user_id: Optional[int] = Query(None, description="Filter berdasarkan ID pengguna"),
    db: Session = Depends(get_db),
    admin_user = Depends(get_current_admin),
):
    query = db.query(AuditLog)
    if action:
        query = query.filter(AuditLog.action == action)
    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)

    return query.order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()