"""Cuentas MySQL; mantiene JWT y cookies de Tickia sin cuentas en Supabase."""
from dataclasses import dataclass
import uuid
from datetime import datetime,timezone
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from fastapi.security import OAuth2PasswordBearer, OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError
from .settings import configure_security

configure_security()
from ..auth_utils import get_password_hash, verify_password, create_access_token, decode_access_token, ACCESS_TOKEN_EXPIRE_MINUTES
from .database import get_db, row

router = APIRouter(prefix='/api/auth', tags=['cuentas MySQL'])
oauth = OAuth2PasswordBearer(tokenUrl='/api/auth/login', auto_error=False)


@dataclass(frozen=True)
class AcademicUser:
    id_usuario: int
    id: str
    email: str
    nombre: str
    is_admin: bool


def get_current_user(request: Request, token=Depends(oauth), db=Depends(get_db, scope="function")):
    payload = decode_access_token(request.cookies.get('access_token') or token or '')
    try:
        identifier = str(uuid.UUID(payload['user_id'])) if payload else None
    except (KeyError, ValueError, TypeError):
        identifier = None
    user = row(db, 'SELECT * FROM usuarios WHERE auth_uuid=:id AND password_hash IS NOT NULL', {'id': identifier}) if identifier else None
    if not user:
        raise HTTPException(401, 'Ingresa con tu cuenta para continuar.')
    if user['suspendido'] or (user['banned_until'] and user['banned_until']>datetime.now(timezone.utc).replace(tzinfo=None)):
        raise HTTPException(403,'Tu cuenta está suspendida.')
    return AcademicUser(user['id_usuario'], user['auth_uuid'], user['email'], user['nombre'], bool(user['es_admin']))


def optional_user(request: Request, token=Depends(oauth), db=Depends(get_db, scope="function")):
    try:
        return get_current_user(request, token, db)
    except HTTPException as error:
        if error.status_code == 401:
            return None
        raise


def user_view(user):
    return dict(id=user.id, id_usuario=user.id_usuario, email=user.email,
                full_name=user.nombre, is_admin=user.is_admin, rating=4.0)


class Registration(BaseModel):
    email: EmailStr
    password: str = Field(min_length=8, max_length=72)
    phone_number: str = Field(min_length=6, max_length=25)
    full_name: str = Field(default='', max_length=160)
    id_distrito: int = Field(default=1, ge=1)


@router.post('/register', status_code=201)
def register(data: Registration, db=Depends(get_db, scope="function")):
    email = str(data.email).strip().lower()
    if len(data.password.encode('utf-8')) > 72:
        raise HTTPException(422, 'La contraseña no debe superar 72 bytes UTF-8.')
    if row(db, 'SELECT id_usuario FROM usuarios WHERE email=:email LIMIT 1', {'email': email}):
        raise HTTPException(400, 'No se pudo crear la cuenta con ese correo. Usa otro o inicia sesión.')
    if not row(db, 'SELECT id_distrito FROM distritos WHERE id_distrito=:id', {'id': data.id_distrito}):
        raise HTTPException(422, 'Selecciona un distrito válido.')
    identifier, name = str(uuid.uuid4()), data.full_name.strip() or email.split('@')[0]
    try:
        result = db.execute(text('''INSERT INTO usuarios(id_distrito,nombre,email,fecha_registro,auth_uuid,password_hash,telefono)
            VALUES(:district,:name,:email,DATE(CONVERT_TZ(UTC_TIMESTAMP(),'+00:00','-05:00')),:uuid,:password,:phone)'''),
            dict(district=data.id_distrito, name=name, email=email, uuid=identifier,
                 password=get_password_hash(data.password), phone=data.phone_number))
    except IntegrityError:
        raise HTTPException(400, 'No se pudo completar el registro.')
    return user_view(AcademicUser(result.lastrowid, identifier, email, name, False))


@router.post('/login')
def login(response: Response, form=Depends(OAuth2PasswordRequestForm), db=Depends(get_db, scope="function")):
    record = row(db, 'SELECT * FROM usuarios WHERE auth_email=:email', {'email': form.username.strip().lower()})
    if not record or not verify_password(form.password, record['password_hash']):
        raise HTTPException(401, 'Correo o contraseña incorrectos.')
    if record['suspendido'] or (record['banned_until'] and record['banned_until']>datetime.now(timezone.utc).replace(tzinfo=None)):
        raise HTTPException(403,'Tu cuenta está suspendida.')
    token = create_access_token({'user_id': record['auth_uuid']})
    response.set_cookie('access_token', token, httponly=True, samesite='lax',
                        max_age=ACCESS_TOKEN_EXPIRE_MINUTES*60, secure=False)
    return dict(access_token=token, token_type='bearer')


@router.get('/me')
def me(user=Depends(get_current_user)):
    return user_view(user)


@router.post('/logout')
def logout(response: Response):
    response.delete_cookie('access_token', httponly=True, samesite='lax')
    return {'message': 'Sesión cerrada.'}
