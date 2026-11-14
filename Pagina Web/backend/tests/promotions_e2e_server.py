"""Loopback-only campaign fixture; real routes and encrypted QR, offline gateway."""
import os

from . import e2e_server as fixture
from .. import models, promotions
from ..database import SessionLocal

# Policy boundary is date-controlled; payment/session clocks remain real.
promotions.in_launch_window = lambda *_args: True
app = fixture.app


@app.get('/api/_test/promotion-ledger')
def promotion_ledger():
    with SessionLocal() as db:
        return [{'status': tx.status, 'listed_amount': float(tx.listed_amount or tx.amount_total),
                 'buyer_discount': float(tx.buyer_discount), 'amount_total': float(tx.amount_total),
                 'commission': float(tx.commission_platform), 'seller_amount': float(tx.amount_seller)}
                for tx in db.query(models.Transaction).order_by(models.Transaction.created_at).all()]


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_API_PORT', '8010')))
