import os
from datetime import datetime, timedelta, timezone
import bcrypt
import jwt
import secrets
from pydantic import ValidationError
from typing import Optional

SECRET_KEY = os.getenv("SECRET_KEY")
if os.getenv("ENVIRONMENT") == "production" and (not SECRET_KEY or len(SECRET_KEY) < 32):
    raise RuntimeError("SECRET_KEY debe tener al menos 32 caracteres en producción")
SECRET_KEY = SECRET_KEY or secrets.token_urlsafe(48)
ALGORITHM = os.getenv("ALGORITHM", "HS256")
if ALGORITHM != "HS256":
    raise RuntimeError("ALGORITHM debe ser HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "30"))

def get_password_hash(password: str) -> str:
    # Cost factor mínimo 12 requerido por especificación
    salt = bcrypt.gensalt(rounds=12)
    pwd_bytes = password.encode('utf-8')
    if len(pwd_bytes) > 72:
        raise ValueError("La contraseña no debe superar 72 bytes UTF-8")
    return bcrypt.hashpw(pwd_bytes, salt).decode('utf-8')

def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))
    except (ValueError, TypeError):
        return False

def create_access_token(data: dict, expires_delta: Optional[timedelta] = None):
    to_encode = data.copy()
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    encoded_jwt = jwt.encode(to_encode, SECRET_KEY, algorithm=ALGORITHM)
    return encoded_jwt

def decode_access_token(token: str) -> dict:
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM],
                             options={"require": ["exp", "user_id"], "verify_signature": True, "verify_exp": True})
        return payload
    except jwt.ExpiredSignatureError:
        return None
    except jwt.PyJWTError:
        return None
