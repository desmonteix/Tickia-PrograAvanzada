from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.responses import Response
from sqlalchemy.orm import Session
from datetime import datetime, timezone
from .. import models
from ..database import get_db
from ..dependencies import get_current_user
from ..storage_utils import download_encrypted_qr
from ..qr_utils import decrypt_bytes_fernet
import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/download", tags=["download"])

@router.get("/{token}")
def download_secure_qr(
    token: str, 
    current_user: models.User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Endpoint de descarga segura.
    SECURITY: Valida propiedad del registro (current_user) y token de 1 solo uso.
    """
    # 1. Buscar la transacción con este token
    tx = db.query(models.Transaction).filter(
        models.Transaction.download_token == token
    ).first()

    if not tx:
        logger.warning(f"[SECURITY] Intento de descarga con token inválido: {token}")
        raise HTTPException(status_code=404, detail="Enlace de descarga no encontrado o inválido.")

    # 1.5 SECURITY: Validar propiedad (OWASP) - No basta el enlace, el usuario debe ser el comprador
    if tx.buyer_id != current_user.id:
        logger.warning(f"[SECURITY] Intento de acceso a QR ajeno por el usuario {current_user.id}")
        raise HTTPException(status_code=403, detail="No tienes permisos para descargar este ticket.")

    # 2. Verificar que no se haya usado
    if tx.download_token_used:
        logger.warning(f"[SECURITY] Intento de re-uso de token de descarga (ticket {tx.ticket_id})")
        raise HTTPException(status_code=410, detail="Este enlace ya fue utilizado (Gone).")

    # 3. Verificar expiración
    if not tx.download_token_expires_at or datetime.now(timezone.utc) > tx.download_token_expires_at:
        logger.warning(f"[SECURITY] Intento de uso de token expirado (ticket {tx.ticket_id})")
        raise HTTPException(status_code=410, detail="El enlace ha expirado.")

    # 4. Obtener el ticket para sacar la ruta en storage
    ticket = db.query(models.Ticket).filter(models.Ticket.id == tx.ticket_id).first()
    if not ticket or not ticket.qr_image_url_encrypted:
        raise HTTPException(status_code=404, detail="Archivo QR no encontrado en el sistema.")

    try:
        # 5. Descargar el ciphertext desde Supabase
        # qr_image_url_encrypted guarda el path, e.g., "tickets/encrypted_xxx.enc"
        encrypted_bytes = download_encrypted_qr(ticket.qr_image_url_encrypted)

        # 6. Descifrar con la llave maestra
        decrypted_bytes = decrypt_bytes_fernet(encrypted_bytes)

        # 7. Marcar el token como usado (quema el enlace)
        tx.download_token_used = True
        
        # Opcional: Auditar que se descargó
        db.add(models.AuditLog(
            user_id=tx.buyer_id,
            action="QR_DOWNLOADED",
            entity_type="ticket",
            entity_id=str(ticket.id),
            reason="Descarga de QR mediante token de un solo uso"
        ))
        
        db.commit()

        # 8. Retornar la imagen con cabeceras correctas anti-caché
        return Response(
            content=decrypted_bytes,
            media_type="image/png",
            headers={
                "Cache-Control": "no-store, no-cache, must-revalidate, max-age=0",
                "Pragma": "no-cache",
                "Expires": "0",
                # Opcional: Content-Disposition inline o attachment
                "Content-Disposition": f'inline; filename="qr_{ticket.id}.png"'
            }
        )

    except Exception as e:
        db.rollback()
        logger.error(f"[SECURITY] Error procesando la descarga del QR (ticket {tx.ticket_id}): {e}")
        raise HTTPException(status_code=500, detail="Error interno al recuperar el archivo seguro.")
