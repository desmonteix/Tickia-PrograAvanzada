from .database import engine, Base
from . import models
from .local_config import LOCAL_MODE
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

def init_db():
    logger.info("Inicializando la base de datos %s...", "SQLite local" if LOCAL_MODE else "configurada")
    try:
        # Crea todas las tablas definidas en models.py
        Base.metadata.create_all(bind=engine)
        if LOCAL_MODE:
            from .dataset import ensure_dataset
            manifest = ensure_dataset()
            logger.info("Dataset local: %s tablas, %s registros", len(manifest), sum(t["rows"] for t in manifest))
        logger.info("¡Tablas creadas exitosamente!")
    except Exception as e:
        logger.error("No se pudieron inicializar las tablas")
        raise

if __name__ == "__main__":
    init_db()
