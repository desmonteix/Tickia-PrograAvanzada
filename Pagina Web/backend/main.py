import asyncio
import logging
import os
from contextlib import asynccontextmanager, suppress

from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text, inspect
from slowapi.errors import RateLimitExceeded
from slowapi import _rate_limit_exceeded_handler

from .database import SessionLocal, engine
from .routers import auth, tickets, payments, download, admin, purchases, dlocal, promotions
from .rate_limit import limiter
from .body_limit import BodyLimitMiddleware
from .local_config import DATA_MODE, LOCAL_MODE

logger = logging.getLogger(__name__)
is_production = os.getenv("ENVIRONMENT") == "production"
ORIGINS = [value.strip().rstrip("/") for value in os.getenv(
    "FRONTEND_PROD_URL", "https://tickia.com,https://www.tickia.com"
).split(",") if value.strip()]
if not is_production:
    ORIGINS += ["http://localhost:5173", "http://127.0.0.1:5173", "http://localhost:5174", "http://127.0.0.1:5174"]


def run_maintenance():
    from .jobs import release_expired_reservations, check_renomination_deadlines
    with SessionLocal() as db:
        release_expired_reservations(db)
        check_renomination_deadlines(db)
        from .post_purchase import close_expired_reviews, process_settlements, reconcile_refunds
        close_expired_reviews(db)
        process_settlements(db)
        reconcile_refunds(db)
        from .go_payments import reconcile_go_payments
        from .go_settlements import process_go_settlements
        from .dlocal_go import DLocalGoProvider
        go = DLocalGoProvider()
        reconcile_go_payments(db, go)
        process_go_settlements(db, go)


async def reservation_cleanup_loop():
    while True:
        await asyncio.sleep(60)
        try:
            await asyncio.to_thread(run_maintenance)
        except Exception:
            logger.exception("Falló el mantenimiento de reservas")


def validate_production():
    if not is_production:
        return
    from .rate_limit import valid_proxy_secret
    if not valid_proxy_secret(os.getenv('PROXY_SHARED_SECRET')):
        raise RuntimeError(
            'PROXY_SHARED_SECRET requiere 32-128 caracteres aleatorios URL-safe '
            '(A-Z, a-z, 0-9, _ y -). Configura la misma clave privada en '
            'backend y frontend/nginx desde las variables de entorno de Easypanel.'
        )
    from .qr_utils import _get_fernet
    _get_fernet()
    if os.getenv("COOKIE_SAMESITE", "lax") not in ("lax", "strict", "none"):
        raise RuntimeError("COOKIE_SAMESITE inválido")
    if not ORIGINS or any(not origin.startswith("https://") for origin in ORIGINS):
        raise RuntimeError("FRONTEND_PROD_URL requiere orígenes HTTPS explícitos")
    inspector = inspect(engine)
    if not {'purchase_reviews', 'dispute_evidence'} <= set(inspector.get_table_names()) or not {'rating', 'warning_count'} <= {column['name'] for column in inspector.get_columns('users')} or 'event_end_date' not in {column['name'] for column in inspector.get_columns('tickets')}:
        raise RuntimeError('Aplica la migración purchase_reviews.sql antes de iniciar producción.')
    tx_columns = {column["name"] for column in inspector.get_columns("transactions")}
    if not {"payment_token_hash", "provider_fee", "seller_net_amount"} <= tx_columns:
        raise RuntimeError("Aplica la migración production_readiness.sql antes del lanzamiento")
    if (not {'payout_profiles', 'financial_operations'} <= set(inspector.get_table_names())
            or not {'payment_provider', 'provider_payment_id', 'available_after', 'approved_at', 'fee_terms_hash', 'payout_terms', 'payin_fee', 'payout_fee', 'checkout_url'} <= tx_columns
            or 'settlement_check_at' not in {c['name'] for c in inspector.get_columns('purchase_reviews')}):
        raise RuntimeError('Aplica la migración dlocal_go.sql antes de iniciar esta versión.')
    if (not {'referrals', 'referral_rewards'} <= set(inspector.get_table_names())
            or not {'listed_amount', 'buyer_discount', 'commission_rate', 'referral_reward_user_id'} <= tx_columns
            or not {'commission_rate', 'reservation_id', 'reservation_total', 'reservation_discount'} <=
                {c['name'] for c in inspector.get_columns('tickets')}):
        raise RuntimeError('Aplica la migración launch_promotions.sql antes de iniciar esta versión.')
    if (not {'promotion_campaigns', 'site_settings'} <= set(inspector.get_table_names())
            or not {'buyer_discount_rate', 'seller_referral_reward_user_id'} <= tx_columns
            or not {'reservation_discount_rate', 'reservation_commission_rate', 'reservation_seller_reward_id'} <=
                {c['name'] for c in inspector.get_columns('tickets')}
            or not {'seller_ticket_id', 'seller_qualified_at'} <= {c['name'] for c in inspector.get_columns('referrals')}
            or not {'campaign_id', 'choice', 'reward_kind', 'buyer_discount_rate', 'seller_commission_rate', 'pending_upgrade', 'revoked_at'} <=
                {c['name'] for c in inspector.get_columns('referral_rewards')}):
        raise RuntimeError('Aplica la migración campaign_controls.sql después de launch_promotions.sql antes de iniciar esta versión.')
    if os.getenv('PAYMENT_PROVIDER', 'culqi') not in ('culqi', 'dlocal_go'):
        raise RuntimeError('PAYMENT_PROVIDER debe ser culqi o dlocal_go.')
    for table, index_name in (("tickets", "uq_ticket_active_qr"), ("transactions", "uq_ticket_settlement")):
        if index_name not in {index["name"] for index in inspector.get_indexes(table)}:
            raise RuntimeError("Falta un índice de integridad. Aplica production_readiness.sql")


@asynccontextmanager
async def lifespan(app: FastAPI):
    if LOCAL_MODE:
        from .init_db import init_db
        await asyncio.to_thread(init_db)
    validate_production()
    task = asyncio.create_task(reservation_cleanup_loop())
    try:
        yield
    finally:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task


app = FastAPI(
    title="Tickia API", version="1.1.0", lifespan=lifespan,
    docs_url=None if is_production else "/docs",
    redoc_url=None if is_production else "/redoc",
    openapi_url=None if is_production else "/openapi.json",
)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(BodyLimitMiddleware)
app.add_middleware(
    CORSMiddleware, allow_origins=ORIGINS, allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization"],
)
for router in (auth.router, tickets.router, payments.router, download.router, admin.router, purchases.router, dlocal.router, promotions.router):
    app.include_router(router)

if LOCAL_MODE:
    from .routers.dataset import router as dataset_router
    app.include_router(dataset_router)


@app.get("/api/runtime")
def runtime_config():
    return {"data_mode": DATA_MODE}


@app.middleware("http")
async def security_headers_middleware(request: Request, call_next):
    try:
        content_length = int(request.headers.get("content-length", "0"))
    except ValueError:
        return JSONResponse({"detail": "Content-Length inválido."}, status_code=400)
    if content_length > 6 * 1024 * 1024:
        return JSONResponse({"detail": "La solicitud es demasiado grande."}, status_code=413)
    origin = request.headers.get("origin")
    if request.method not in ("GET", "HEAD", "OPTIONS") and origin and origin.rstrip("/") not in ORIGINS:
        return JSONResponse({"detail": "Origen de solicitud no permitido."}, status_code=403)
    response = await call_next(request)
    if is_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    response.headers["Content-Security-Policy"] = "default-src 'none'; frame-ancestors 'none'"
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "no-referrer"
    response.headers["Permissions-Policy"] = "geolocation=(), camera=(), microphone=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/ready")
def ready_check():
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
            enabled = payments.payment_status(db)['enabled']
    except Exception:
        raise HTTPException(503, "Base de datos no disponible.")
    return {"status": "ready", "payments_enabled": enabled}
