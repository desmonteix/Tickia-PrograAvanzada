import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response
from sqlalchemy.orm import Session
from .. import models
from ..database import get_db
from ..dependencies import get_current_user
from ..storage_utils import download_encrypted_qr
from ..qr_utils import decrypt_bytes_fernet

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/download", tags=["download"])


@router.get("/{token}")
def download_secure_qr(token: str, current_user: models.User = Depends(get_current_user), db: Session = Depends(get_db)):
    tx = db.query(models.Transaction).filter(models.Transaction.download_token == token).first()
    if not tx:
        raise HTTPException(404, "Enlace de descarga inválido.")
    # Lock in the same order as payment/refund paths; refresh after waiting.
    ticket = db.query(models.Ticket).filter(models.Ticket.id == tx.ticket_id).with_for_update().first()
    tx = db.query(models.Transaction).filter(models.Transaction.id == tx.id).populate_existing().with_for_update().first()
    if tx.download_token != token:
        raise HTTPException(410, "El enlace fue reemplazado.")
    if tx.buyer_id != current_user.id:
        raise HTTPException(403, "No tienes permisos para descargar esta entrada.")
    if tx.status != "SUCCEEDED":
        raise HTTPException(403, "El pago no está confirmado.")
    if tx.download_token_used:
        raise HTTPException(410, "Este enlace ya fue utilizado.")
    expires = tx.download_token_expires_at
    if expires and expires.tzinfo is None:
        expires = expires.replace(tzinfo=timezone.utc)
    if not expires or expires <= datetime.now(timezone.utc):
        raise HTTPException(410, "El enlace ha expirado.")
    if (
        not ticket or ticket.buyer_id != current_user.id
        or ticket.estado not in (models.TicketState.VENDIDA, models.TicketState.LIBERADA)
        or not ticket.qr_image_url_encrypted
    ):
        raise HTTPException(403, "Esta entrada no está disponible para descarga.")
    try:
        data = decrypt_bytes_fernet(download_encrypted_qr(ticket.qr_image_url_encrypted))
        tx.download_token_used = True
        tx.hmac_link_opened_at = datetime.now(timezone.utc)
        db.add(models.AuditLog(
            user_id=current_user.id, action="QR_DOWNLOADED", entity_type="ticket",
            entity_id=str(ticket.id), reason="Descarga de un solo uso.",
        ))
        db.commit()
    except Exception:
        db.rollback()
        logger.exception("No se pudo recuperar el archivo QR")
        raise HTTPException(503, "No se pudo recuperar el archivo. Intenta nuevamente.")
    is_png = data.startswith(b"\x89PNG")
    extension = "png" if is_png else "jpg"
    return Response(
        content=data, media_type="image/png" if is_png else "image/jpeg",
        headers={"Cache-Control": "no-store, private, max-age=0", "Pragma": "no-cache",
                 "Content-Disposition": f'inline; filename="qr_{ticket.id}.{extension}"'},
    )
