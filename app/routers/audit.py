from typing import Optional
from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session
from app.database import get_db
from app.models.audit_log import AuditLog
from app.routers.auth import get_current_admin

router = APIRouter()

@router.get("/", summary="Daftar Audit Log")
def get_audit_logs(
    skip: int = Query(0),
    limit: int = Query(50),
    db: Session = Depends(get_db),
    admin_user = Depends(get_current_admin)
):
    return db.query(AuditLog).order_by(AuditLog.timestamp.desc()).offset(skip).limit(limit).all()