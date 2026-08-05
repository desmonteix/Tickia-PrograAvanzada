from fastapi import Depends, HTTPException, status, Request
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from .database import get_db
from .auth_utils import decode_access_token
from . import models
import uuid

# We keep OAuth2PasswordBearer for swagger UI compatibility, but custom logic for cookies
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="api/auth/login", auto_error=False)

def get_current_user(request: Request, token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)):
    # SECURITY: Prioritize token from HttpOnly cookie
    cookie_token = request.cookies.get("access_token")
    actual_token = cookie_token or token
    
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials",
        headers={"WWW-Authenticate": "Bearer"},
    )
    if not actual_token:
        raise credentials_exception
    payload = decode_access_token(actual_token)
    if payload is None:
        raise credentials_exception
        
    user_id_str: str = payload.get("user_id")
    if user_id_str is None:
        raise credentials_exception
        
    try:
        user_id = uuid.UUID(user_id_str)
    except ValueError:
        raise credentials_exception

    user = db.query(models.User).filter(models.User.id == user_id).first()
    if user is None:
        raise credentials_exception
    if user.is_suspended:
        raise HTTPException(status_code=403, detail="User account is suspended")
        
    return user
