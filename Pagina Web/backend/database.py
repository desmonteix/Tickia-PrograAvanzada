import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Asegurar que se cargue el .env correcto sin importar desde dónde se ejecute
env_path = os.path.join(os.path.dirname(__file__), '.env')
if os.getenv("TICKIA_LOAD_ENV", "1") != "0":
    load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("DATABASE_URL es obligatoria en producción")
    # Fallback to local postgres for testing if no supabase URL is provided yet
    DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/tickertrader"
elif DATABASE_URL.startswith("postgresql://"):
    # Fix for SQLAlchemy 2 with psycopg3
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+psycopg://", 1)

# PostgreSQL specific engine configuration
# Requerido por la especificación: lock_timeout y session_timeout
engine_options = {"pool_pre_ping": True}
if DATABASE_URL.startswith("sqlite"):
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("Producción requiere PostgreSQL para bloqueo transaccional")
    engine_options["connect_args"] = {"check_same_thread": False}
    if DATABASE_URL in {"sqlite://", "sqlite:///:memory:"}:
        from sqlalchemy.pool import StaticPool
        engine_options["poolclass"] = StaticPool
else:
    engine_options["connect_args"] = {
        "options": "-c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000"
    }
engine = create_engine(DATABASE_URL, **engine_options)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
