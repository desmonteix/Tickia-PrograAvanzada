import os
from sqlalchemy import create_engine
from sqlalchemy.orm import declarative_base, sessionmaker
from dotenv import load_dotenv

# Asegurar que se cargue el .env correcto sin importar desde dónde se ejecute
env_path = os.path.join(os.path.dirname(__file__), '.env')
load_dotenv(env_path)

DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    # Fallback to local postgres for testing if no supabase URL is provided yet
    DATABASE_URL = "postgresql+psycopg://postgres:postgres@localhost:5432/tickertrader"
elif DATABASE_URL.startswith("postgresql://"):
    # Fix for SQLAlchemy 2 with psycopg3
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+psycopg://", 1)

# PostgreSQL specific engine configuration
# Requerido por la especificación: lock_timeout y session_timeout
engine = create_engine(
    DATABASE_URL,
    connect_args={
        "options": "-c lock_timeout=5000 -c idle_in_transaction_session_timeout=30000"
    }
)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
