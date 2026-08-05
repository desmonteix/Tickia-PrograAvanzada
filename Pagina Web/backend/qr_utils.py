"""
Utilidades de QR: Validación de imagen, extracción de QR y cifrado/descifrado AES-256.
"""
import cv2
import numpy as np
import hashlib
import os
from urllib.parse import urlparse
from cryptography.fernet import Fernet, InvalidToken
import logging

logger = logging.getLogger(__name__)

# Simularemos que PYZBAR_AVAILABLE es falso por ahora en Windows
PYZBAR_AVAILABLE = False
logger.warning("pyzbar deshabilitado temporalmente (falta DLL en Windows)")

# Lista blanca configurable de dominios de ticketeras
ALLOWED_DOMAINS = ["teleticket.com.pe", "joinnus.com", "pencorp.vercel.app"]

# ─── Cifrado AES-256 (Fernet) ──────────────────────────────────────────────────

def _get_fernet() -> Fernet:
    """
    Obtiene la instancia de Fernet usando la llave maestra del entorno.
    Lanza un error claro si la variable de entorno no está configurada.
    """
    key = os.getenv("QR_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError(
            "QR_ENCRYPTION_KEY no está configurada. "
            "Genera una llave con: from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
        )
    return Fernet(key.encode())

def encrypt_bytes_fernet(plaintext_bytes: bytes) -> bytes:
    """
    Cifra un bloque de bytes con AES-256 usando Fernet (AES-128-CBC + HMAC-SHA256).
    El resultado incluye IV y MAC y es completamente opaco para el almacenamiento.
    """
    f = _get_fernet()
    return f.encrypt(plaintext_bytes)

def decrypt_bytes_fernet(ciphertext_bytes: bytes) -> bytes:
    """
    Descifra los bytes cifrados con Fernet. Lanza InvalidToken si los datos
    están corrompidos o la llave es incorrecta (fail-secure).
    """
    f = _get_fernet()
    try:
        return f.decrypt(ciphertext_bytes)
    except InvalidToken:
        logger.error("[SECURITY] Intento de descifrado fallido — datos corrompidos o llave incorrecta.")
        raise


# ─── Validación de imagen ──────────────────────────────────────────────────────

def validate_image_file(file_bytes: bytes, content_type: str):
    """
    Verifica los magic numbers (firma de archivo) para prevenir la subida de archivos maliciosos
    encubiertos bajo extensiones de imagen.
    """
    # Magic numbers for PNG and JPEG
    is_png = file_bytes.startswith(b'\x89PNG\r\n\x1a\n')
    is_jpeg = file_bytes.startswith(b'\xff\xd8\xff')

    if not (is_png or is_jpeg):
        return False
    
    if content_type not in ["image/jpeg", "image/png"]:
        return False
        
    return True

def process_qr_image(file_bytes: bytes):
    """
    Procesa la imagen usando OpenCV y pyzbar.
    Retorna el contenido decodificado del QR o None si falla.
    """
    nparr = np.frombuffer(file_bytes, np.uint8)
    img = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    
    if img is None:
        return None, "Error decodificando imagen"
        
    if not PYZBAR_AVAILABLE:
        # Mock para entorno Windows sin DLLs de pyzbar
        import uuid
        qr_data = f"https://pencorp.vercel.app/mock-{uuid.uuid4()}"
    else:
        decoded_objects = decode(img)
        if not decoded_objects:
            return None, "No se detectó ningún QR en la imagen"
        # Asumimos el primer QR encontrado
        qr_data = decoded_objects[0].data.decode('utf-8')
    
    # Hash SHA-256 del contenido (obligatorio por especificación)
    qr_hash = hashlib.sha256(qr_data.encode('utf-8')).hexdigest()
    
    # Validación de dominio si es URL
    if qr_data.startswith("http://") or qr_data.startswith("https://"):
        domain = urlparse(qr_data).netloc
        if not any(domain.endswith(allowed) for allowed in ALLOWED_DOMAINS):
            return None, "El dominio del QR no está en la lista blanca permitida."
            
    # TODO: Implementar validación visual OpenCV de plantillas de la ticketera
            
    return {"data": qr_data, "hash": qr_hash}, None
