"""Configuración de esta rama académica, aislada del .env de producción."""
import base64
import json
import os
import secrets

from .dataset import LOCAL_DIR

DATA_MODE = os.getenv("TICKIA_DATA_MODE", "remote" if os.getenv("ENVIRONMENT") == "test" else "dataset")
if DATA_MODE not in ("dataset", "remote"):
    raise RuntimeError("TICKIA_DATA_MODE debe ser dataset o remote")
LOCAL_MODE = DATA_MODE == "dataset"


def configure_local():
    if os.getenv("ENVIRONMENT") == "production":
        raise RuntimeError("La versión académica es local. Usa ENVIRONMENT=development.")
    LOCAL_DIR.mkdir(parents=True, exist_ok=True)
    path = LOCAL_DIR / "secrets.json"
    try:
        with path.open("x", encoding="utf-8") as stream:
            json.dump({"SECRET_KEY": secrets.token_urlsafe(48),
                       "QR_ENCRYPTION_KEY": base64.urlsafe_b64encode(secrets.token_bytes(32)).decode()}, stream)
    except FileExistsError:
        pass
    with path.open(encoding="utf-8") as stream:
        config = json.load(stream)
    for name in ("SECRET_KEY", "QR_ENCRYPTION_KEY"):
        os.environ[name] = config[name]
    os.environ.update({"ENVIRONMENT": "development", "PAYMENT_ENABLED": "false",
                       "SETTLEMENT_ENABLED": "false", "COOKIE_SAMESITE": "lax"})
    return "sqlite:///" + (LOCAL_DIR / "tickia.sqlite3").as_posix()
