import os
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy import func
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session
from .. import models, schemas
from ..database import get_db
from ..dependencies import get_current_user
from ..auth_utils import get_password_hash, verify_password, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from ..rate_limit import limiter

router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.post("/register", response_model=schemas.UserResponse, status_code=201)
@limiter.limit("5/minute")
def register(request: Request, user_in: schemas.UserCreate, db: Session = Depends(get_db)):
    failure = HTTPException(400, "No se pudo completar el registro. Verifica tus datos.")
    if db.query(models.User).filter(func.lower(models.User.email) == user_in.email).first():
        raise failure
    user = models.User(
        email=user_in.email, hashed_password=get_password_hash(user_in.password),
        phone_number=user_in.phone_number, has_access=True,
    )
    try:
        db.add(user)
        db.flush()
        db.add(models.AuditLog(user_id=user.id, action="USER_REGISTER", entity_type="user", entity_id=str(user.id)))
        db.commit()
        db.refresh(user)
    except IntegrityError:
        db.rollback()
        raise failure
    return user


@router.post("/login", response_model=schemas.Token)
@limiter.limit("10/minute")
def login(request: Request, response: Response, form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = db.query(models.User).filter(func.lower(models.User.email) == form_data.username.strip().lower()).first()
    if not user or not verify_password(form_data.password, user.hashed_password):
        db.add(models.AuditLog(
            user_id=user.id if user else None, action="FAILED_LOGIN", entity_type="user",
            entity_id=form_data.username[:254], ip_address=request.client.host if request.client else None,
            reason="Credenciales incorrectas",
        ))
        db.commit()
        raise HTTPException(401, "Correo o contraseña incorrectos.", headers={"WWW-Authenticate": "Bearer"})
    banned = user.banned_until
    if banned and banned.tzinfo is None:
        banned = banned.replace(tzinfo=timezone.utc)
    if user.is_suspended or (banned and banned > datetime.now(timezone.utc)):
        raise HTTPException(403, "Tu cuenta está suspendida.")
    token = create_access_token({"user_id": str(user.id)})
    db.add(models.AuditLog(user_id=user.id, action="USER_LOGIN", entity_type="user", entity_id=str(user.id)))
    db.commit()
    response.set_cookie(
        "access_token", token, httponly=True,
        secure=os.getenv("ENVIRONMENT") == "production",
        samesite=os.getenv("COOKIE_SAMESITE", "lax"),
        max_age=ACCESS_TOKEN_EXPIRE_MINUTES * 60,
    )
    return schemas.Token(access_token=token, token_type="bearer")


@router.post("/logout")
def logout(response: Response):
    response.delete_cookie(
        "access_token", httponly=True, secure=os.getenv("ENVIRONMENT") == "production",
        samesite=os.getenv("COOKIE_SAMESITE", "lax"),
    )
    return {"message": "Sesión cerrada."}


@router.get("/me", response_model=schemas.UserResponse)
def read_users_me(current_user: models.User = Depends(get_current_user)):
    return current_user
