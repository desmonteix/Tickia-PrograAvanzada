"""Real QR decoding and authenticated encryption; no synthetic validation."""
import hashlib
import logging
import os
from urllib.parse import urlparse

os.environ.setdefault("OPENCV_IO_MAX_IMAGE_PIXELS", "20000000")
import cv2
import numpy as np
from cryptography.fernet import Fernet

logger = logging.getLogger(__name__)
ALLOWED_DOMAINS = ("teleticket.com.pe", "joinnus.com")
MAX_FILE_BYTES = 5 * 1024 * 1024


def _get_fernet() -> Fernet:
    key = os.getenv("QR_ENCRYPTION_KEY")
    if not key:
        raise RuntimeError("QR_ENCRYPTION_KEY no está configurada")
    return Fernet(key.encode())


def encrypt_bytes_fernet(plaintext_bytes: bytes) -> bytes:
    """Fernet authenticates AES-128-CBC ciphertext using HMAC-SHA256."""
    return _get_fernet().encrypt(plaintext_bytes)


def decrypt_bytes_fernet(ciphertext_bytes: bytes) -> bytes:
    return _get_fernet().decrypt(ciphertext_bytes)


def validate_image_file(file_bytes: bytes, content_type: str) -> bool:
    return bool(file_bytes) and len(file_bytes) <= MAX_FILE_BYTES and (
        (content_type == "image/png" and file_bytes.startswith(b"\x89PNG\r\n\x1a\n"))
        or (content_type == "image/jpeg" and file_bytes.startswith(b"\xff\xd8\xff"))
    )


def process_qr_image(file_bytes: bytes):
    if not isinstance(file_bytes, bytes) or not file_bytes or len(file_bytes) > MAX_FILE_BYTES:
        return None, "Archivo vacío o demasiado grande."
    try:
        image = cv2.imdecode(np.frombuffer(file_bytes, np.uint8), cv2.IMREAD_COLOR)
        if image is None or image.shape[0] * image.shape[1] > 20_000_000:
            return None, "Imagen inválida o dimensiones demasiado grandes."
        detector = cv2.QRCodeDetector()
        found, decoded, _, _ = detector.detectAndDecodeMulti(image)
        payloads = [value for value in decoded if value] if found else []
        if len(payloads) > 1:
            return None, "Sube una imagen con una sola entrada y un solo código QR."
        data = payloads[0] if payloads else detector.detectAndDecode(image)[0]
        if not data and hasattr(cv2, "QRCodeDetectorAruco"):
            data = cv2.QRCodeDetectorAruco().detectAndDecode(image)[0]
    except (cv2.error, ValueError):
        return None, "No se pudo procesar la imagen."
    if not data:
        return None, "No se detectó ningún QR legible en la imagen."
    parsed = urlparse(data)
    if parsed.scheme or parsed.netloc:
        host = (parsed.hostname or "").lower()
        if parsed.scheme != "https" or parsed.username or parsed.password or not any(
            host == domain or host.endswith("." + domain) for domain in ALLOWED_DOMAINS
        ):
            return None, "El dominio del QR no pertenece a una ticketera admitida."
    return {"data": data, "hash": hashlib.sha256(data.encode("utf-8")).hexdigest()}, None
