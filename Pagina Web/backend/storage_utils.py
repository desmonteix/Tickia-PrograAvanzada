"""
Módulo de integración con Supabase Storage.
Gestiona la subida y descarga de archivos cifrados al bucket privado de QRs.
"""
import os
import io
import logging
from supabase import create_client, Client, ClientOptions

logger = logging.getLogger(__name__)

# Nombre del bucket privado en Supabase Storage
QR_BUCKET = "qr-encrypted"

def _get_supabase_client() -> Client:
    """Crea y retorna el cliente de Supabase."""
    url = os.getenv("SUPABASE_URL")
    key = os.getenv("SUPABASE_KEY")
    if not url or not key:
        raise RuntimeError("SUPABASE_URL o SUPABASE_KEY no están configuradas.")
    return create_client(url, key, options=ClientOptions(storage_client_timeout=15, postgrest_client_timeout=15))


def upload_encrypted_qr(storage_path: str, encrypted_bytes: bytes) -> str:
    """
    Sube los bytes ya cifrados de un QR al bucket privado de Supabase Storage.

    Args:
        storage_path: Ruta destino dentro del bucket, e.g. "tickets/uuid.enc"
        encrypted_bytes: El ciphertext producido por qr_utils.encrypt_bytes_fernet()

    Returns:
        La misma storage_path confirmada, para guardar en la BD.

    Raises:
        Exception si la subida falla.
    """
    client = _get_supabase_client()
    
    try:
        # Supabase Storage espera un objeto file-like o bytes.
        # Usamos upsert=True para idempotencia en caso de retry.
        client.storage.from_(QR_BUCKET).upload(
            path=storage_path,
            file=encrypted_bytes,
            file_options={
                "content-type": "application/octet-stream",
                "upsert": "true",
                "cache-control": "private, no-store, no-cache"
            }
        )
        logger.info(f"[STORAGE] QR cifrado subido exitosamente: {storage_path}")
        return storage_path
    except Exception as e:
        logger.error(f"[STORAGE] Error subiendo QR a Supabase Storage: {e}")
        raise


def download_encrypted_qr(storage_path: str) -> bytes:
    """
    Descarga el ciphertext de un QR desde Supabase Storage.

    Args:
        storage_path: Ruta dentro del bucket (guardada en la BD como qr_image_url_encrypted).

    Returns:
        Los bytes cifrados listos para descifrar con qr_utils.decrypt_bytes_fernet().

    Raises:
        Exception si la descarga falla o el archivo no existe.
    """
    client = _get_supabase_client()

    try:
        response = client.storage.from_(QR_BUCKET).download(storage_path)
        logger.info(f"[STORAGE] QR cifrado descargado exitosamente: {storage_path}")
        return response
    except Exception as e:
        logger.error(f"[STORAGE] Error descargando QR de Supabase Storage: {e}")
        raise


def delete_qr_file(storage_path: str) -> None:
    """
    Elimina un archivo de QR del bucket. Se usa durante reembolsos o devoluciones.
    """
    client = _get_supabase_client()
    try:
        client.storage.from_(QR_BUCKET).remove([storage_path])
        logger.info(f"[STORAGE] QR eliminado del bucket: {storage_path}")
    except Exception as e:
        logger.error(f"[STORAGE] Error eliminando QR de Supabase Storage: {e}")
        raise
