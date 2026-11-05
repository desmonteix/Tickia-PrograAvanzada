from .database import engine, Base
from . import models
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    logger.info("Conectando a la base de datos Supabase...")
    try:
        # Crea todas las tablas definidas en models.py
        Base.metadata.create_all(bind=engine)
        logger.info("¡Tablas creadas exitosamente!")
    except Exception as e:
        logger.error("No se pudieron inicializar las tablas")
        raise

if __name__ == "__main__":
    init_db()
