"""Aplicación académica principal. Sus datos operativos viven íntegramente en MySQL."""
import asyncio
from contextlib import asynccontextmanager
import logging
import os
from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from . import auth,catalog,commerce,social,analytics
from .bootstrap import initialize
from .database import engine
from .migration import migrate_legacy
from ..body_limit import BodyLimitMiddleware

logger = logging.getLogger(__name__)
ORIGINS = [value.strip().rstrip('/') for value in os.getenv('FRONTEND_PROD_URL','http://127.0.0.1:5174,http://localhost:5174').split(',') if value.strip()]


@asynccontextmanager
async def lifespan(app):
    await asyncio.to_thread(initialize)
    await asyncio.to_thread(migrate_legacy)
    yield


app = FastAPI(title='Tickia — Marketplace multivendedor universitario',version='2.0.0',lifespan=lifespan)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(CORSMiddleware,allow_origins=ORIGINS,allow_credentials=True,
                   allow_methods=['GET','POST','PUT','DELETE','OPTIONS'],allow_headers=['Content-Type','Authorization'])
for router in (auth.router,catalog.router,commerce.router,social.router,analytics.router):
    app.include_router(router)


@app.middleware('http')
async def headers(request:Request,call_next):
    origin = request.headers.get('origin')
    if request.method not in ('GET','HEAD','OPTIONS') and origin and origin.rstrip('/') not in ORIGINS:
        return JSONResponse({'detail':'Origen de solicitud no permitido.'},status_code=403)
    response = await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'none'; frame-ancestors 'none'"
    return response


@app.exception_handler(SQLAlchemyError)
async def database_error(request,error):
    logger.error('Fallo de MySQL: %s',type(error).__name__)
    return JSONResponse({'detail':'No se pudo completar la operación de base de datos. Intenta nuevamente.'},status_code=503)


@app.get('/health')
def health():
    return {'status':'ok'}


@app.get('/ready')
def ready():
    try:
        with engine.connect() as connection:
            connection.execute(text('SELECT 1'))
    except SQLAlchemyError:
        raise HTTPException(503,'MySQL no está disponible.')
    return {'status':'ready','database':'MySQL','payments_enabled':False}


@app.get('/api/runtime')
def runtime():
    return dict(data_mode='dataset',database='mysql',table_count=17,
                capabilities=dict(cart=True,favorites=True,reviews=True,shipping=True,analytics=True))


@app.get('/api/promotions')
def promotions():
    return dict(active=False,current_commission_rate=0,settings=dict(registrations_enabled=True,
        publications_enabled=True,purchases_enabled=True,maintenance_mode=False,announcement=''))


@app.get('/api/referrals')
def referrals():
    return dict(referral_count=0,reward_status='UNAVAILABLE',choice=None)
