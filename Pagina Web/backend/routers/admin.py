from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from datetime import datetime, timezone, timedelta
from typing import List, Dict, Any

from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user

router = APIRouter(prefix="/api/admin", tags=["admin"])

def get_admin_user(current_user: models.User = Depends(get_current_user)):
    if not getattr(current_user, 'is_admin', False):
        raise HTTPException(status_code=403, detail="Not authorized. Admin access required.")
    return current_user

@router.get("/metrics")
def get_metrics(db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    total_users = db.query(models.User).count()
    total_tickets = db.query(models.Ticket).count()
    total_transactions = db.query(models.Transaction).filter(models.Transaction.status == "SUCCEEDED").count()
    
    # Calculate revenue
    revenue_result = db.query(func.sum(models.Transaction.commission_platform)).filter(models.Transaction.status == "SUCCEEDED").scalar()
    total_revenue = float(revenue_result) if revenue_result else 0.0
    
    return {
        "total_users": total_users,
        "total_tickets": total_tickets,
        "total_transactions": total_transactions,
        "total_revenue": total_revenue
    }

@router.get("/users")
def list_users(skip: int = 0, limit: int = 50, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    users = db.query(models.User).offset(skip).limit(limit).all()
    return [{
        "id": u.id,
        "email": u.email,
        "trust_score": u.trust_score,
        "is_suspended": u.is_suspended,
        "banned_until": u.banned_until,
        "is_admin": getattr(u, 'is_admin', False)
    } for u in users]

@router.post("/users/{user_id}/ban")
def ban_user(user_id: str, days: int = 7, db: Session = Depends(get_db), admin: models.User = Depends(get_admin_user)):
    user = db.query(models.User).filter(models.User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
        
    user.banned_until = datetime.now(timezone.utc) + timedelta(days=days)
    user.trust_score = 0
    db.commit()
    
    audit = models.AuditLog(
        user_id=admin.id,
        action="ADMIN_BANNED_USER",
        entity_type="user",
        entity_id=str(user.id),
        reason=f"Banned by admin for {days} days"
    )
    db.add(audit)
    db.commit()
    
    return {"message": f"User banned for {days} days"}
