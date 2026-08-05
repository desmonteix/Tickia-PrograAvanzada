from fastapi import APIRouter, Depends, HTTPException, status, Request, Response
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..auth_utils import get_password_hash, verify_password, create_access_token
from ..rate_limit import limiter
from fastapi.security import OAuth2PasswordRequestForm
import uuid

router = APIRouter(prefix="/api/auth", tags=["auth"])

@router.post("/register", response_model=schemas.UserResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # SECURITY: Máximo 5 registros por minuto por IP
def register(request: Request, user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    db_user = db.query(models.User).filter(models.User.email == user_in.email).first()
    if db_user:
        # SECURITY: Mensaje genérico para evitar enumeración de emails (OWASP)
        raise HTTPException(status_code=400, detail="No se pudo completar el registro. Verifica tus datos e intenta de nuevo.")
        
    hashed_password = get_password_hash(user_in.password)
    
    import string
    import random
    
    # Generar código de referido único
    while True:
        ref_code = ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        if not db.query(models.User).filter(models.User.referral_code == ref_code).first():
            break
            
    # Procesar referido
    referrer_id = None
    if user_in.ref_code:
        referrer = db.query(models.User).filter(models.User.referral_code == user_in.ref_code).first()
        if referrer:
            referrer_id = referrer.id
            referrer.referral_count += 1
            
    new_user = models.User(
        email=user_in.email,
        hashed_password=hashed_password,
        phone_number=user_in.phone_number,
        referral_code=ref_code,
        referred_by_id=referrer_id,
        has_access=False
    )
    db.add(new_user)
    db.commit()
    db.refresh(new_user)
    
    # Audit log (registration)
    audit = models.AuditLog(
        user_id=new_user.id,
        action="USER_REGISTER",
        entity_type="user",
        entity_id=str(new_user.id)
    )
    db.add(audit)
    db.commit()
    
    return new_user

@router.post("/login", response_model=schemas.Token)
@limiter.limit("10/minute")  # SECURITY: Máximo 10 intentos de login por minuto por IP (anti brute-force)
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(models.User.email == form_data.username).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        # SECURITY: Log fallos de login para monitoreo y prevención de intrusos
        failed_audit = models.AuditLog(
            user_id=user.id if user else None,
            action="FAILED_LOGIN",
            entity_type="user",
            entity_id=form_data.username,  # Guardar el email intentado, NUNCA el password
            ip_address=request.client.host if request.client else "unknown",
            reason="Credenciales incorrectas"
        )
        db.add(failed_audit)
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
        
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="Account suspended")
        
    from datetime import datetime, timezone
    if user.banned_until and user.banned_until > datetime.now(timezone.utc):
        raise HTTPException(status_code=403, detail="Tu cuenta ha sido baneada temporalmente por infringir las políticas de la plataforma.")
        
    access_token = create_access_token(data={"user_id": str(user.id)})
    
    # Audit log
    audit = models.AuditLog(
        user_id=user.id,
        action="USER_LOGIN",
        entity_type="user",
        entity_id=str(user.id)
    )
    db.add(audit)
    db.commit()
    
    import os
    is_production = os.getenv("ENVIRONMENT") == "production"
    
    # SECURITY: Set HttpOnly, Secure cookie for XSS protection
    response.set_cookie(
        key="access_token",
        value=access_token,
        httponly=True,
        secure=is_production,  # Debe ser true en producción (HTTPS), false en localhost
        samesite="lax",
        max_age=15 * 60  # 15 minutes
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.post("/logout")
def logout(response: Response):
    import os
    is_production = os.getenv("ENVIRONMENT") == "production"
    response.delete_cookie(
        key="access_token",
        httponly=True,
        secure=is_production,
        samesite="lax"
    )
    return {"message": "Logged out"}

@router.get("/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user

@router.get("/waitlist/status", response_model=schemas.WaitlistStatus)
def get_waitlist_status(current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    # Calculate position based strictly on referral_count (and tie-break by email for stability)
    from sqlalchemy import or_, and_
    position = db.query(models.User).filter(
        or_(
            models.User.referral_count > current_user.referral_count,
            and_(
                models.User.referral_count == current_user.referral_count,
                models.User.email < current_user.email
            )
        )
    ).count() + 1
    
    return {
        "position": position,
        "referral_code": current_user.referral_code or "",
        "referral_count": current_user.referral_count,
        "has_access": current_user.has_access
    }
