from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from contextlib import asynccontextmanager
from .routers import auth, tickets, payments
from .rate_limit import limiter
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler
import asyncio
import logging

logger = logging.getLogger(__name__)

# ─── Background Job: liberar reservas expiradas ────────────────────────────────
async def reservation_cleanup_loop():
    """Corre cada 60 segundos y libera entradas reservadas que no se pagaron."""
    from .database import SessionLocal
    from .jobs import release_expired_reservations, check_renomination_deadlines
    while True:
        await asyncio.sleep(60)
        db = SessionLocal()
        try:
            release_expired_reservations(db)
            check_renomination_deadlines(db)
        except Exception as e:
            logger.error(f"[CLEANUP-JOB] Error en jobs de background: {e}")
        finally:
            db.close()

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup: lanzar job en background
    task = asyncio.create_task(reservation_cleanup_loop())
    logger.info("[STARTUP] Job de limpieza de reservas iniciado (cada 60s).")
    yield
    # Shutdown: cancelar el job limpiamente
    task.cancel()
    logger.info("[SHUTDOWN] Job de limpieza de reservas detenido.")

import os
is_production = os.getenv("ENVIRONMENT") == "production"

# ─── Aplicación ────────────────────────────────────────────────────────────────
app = FastAPI(
    title="TickerTrader API", 
    version="1.0.0", 
    lifespan=lifespan,
    # SECURITY: Deshabilitar consolas de debug (Swagger/Redoc) en producción
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json"
)
# Rate limiting global
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# Lista blanca de orígenes permitidos (CORS) - NUNCA '*' en endpoints autenticados
ORIGINS = [
    "http://localhost:5173",
    "http://127.0.0.1:5173",
    "http://localhost:5174",
    "http://127.0.0.1:5174",
]
import os
prod_urls_env = os.getenv("FRONTEND_PROD_URL")
if prod_urls_env:
    for url in prod_urls_env.split(','):
        ORIGINS.append(url.strip())
# Also allow tickia.com by default
ORIGINS.extend([
    "https://tickia.com",
    "https://www.tickia.com",
    "https://tickia-frontend-tickia.7w1nku.easypanel.host"
])

app.add_middleware(
    CORSMiddleware,
    allow_origins=ORIGINS,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "DELETE", "OPTIONS"],
    allow_headers=["*"],
)

from .routers import auth, tickets, payments, download, admin

app.include_router(auth.router)
app.include_router(tickets.router)
app.include_router(payments.router)
app.include_router(download.router)
app.include_router(admin.router)

# ─── Middleware de Headers de Seguridad HTTP ───────────────────────────────────
@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    response = await call_next(request)
    response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'self'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    return response

@app.get("/health")
async def health_check():
    return {"status": "ok"}
