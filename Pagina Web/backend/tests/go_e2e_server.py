"""Loopback-only Go browser fixture: real API/SQLite/QR, mocked provider HTTP.

Excluded with backend/tests from production images. No credentials, database or
payment services belonging to a real user are accessed by this module.
"""
import json
import os
import threading
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from urllib.parse import urlsplit

# Import first: the legacy fixture creates a temporary DB, encrypted in-memory
# storage and four isolated accounts, and disables local .env loading.
from . import e2e_server as fixture

os.environ.update({
    'PAYMENT_PROVIDER': 'dlocal_go', 'PAYMENT_ENABLED': 'true', 'SETTLEMENT_ENABLED': 'true',
    'DLOCAL_GO_ENV': 'sandbox', 'DLOCAL_GO_API_KEY': 'go_e2e_api_key',
    'DLOCAL_GO_SECRET_KEY': 'go_e2e_secret_key',
    'DLOCAL_GO_PAYIN_PERCENT': '3.53', 'DLOCAL_GO_PAYIN_FIXED_PEN': '0',
    'DLOCAL_GO_PAYOUT_PERCENT': '0', 'DLOCAL_GO_PAYOUT_FIXED_PEN': '1',
    'DLOCAL_GO_FEES_TAX_PERCENT': '0', 'DLOCAL_GO_MIN_PAYOUT_PEN': '5',
    'DLOCAL_GO_PAYOUT_PURPOSE': 'ENTERTAINMENT',
})

import httpx
from fastapi import HTTPException
from .. import dlocal_go, models, post_purchase
from ..database import SessionLocal
from ..go_payments import reconcile_go_payments
from ..go_settlements import process_go_settlements
from ..routers import dlocal, payments, tickets

app = fixture.app
guard = threading.RLock()
beneficiaries, payins, payouts, payout_keys, refunds = {}, {}, {}, {}, {}
provider_posts = {'payins': 0, 'payouts': 0, 'refunds': 0}


def provider_http(request):
    """The only simulated boundary; real provider adapters serialize requests."""
    payload = json.loads(request.content) if request.content else None
    path, method = request.url.path, request.method
    with guard:
        if path == '/v2/beneficiaries':
            if method == 'POST':
                if any(x['document'] == payload['document'] for x in beneficiaries.values()):
                    return httpx.Response(409, json={'code': 409})
                identifier = len(beneficiaries) + 1
                value = {**payload, 'id': identifier, 'status': 'PENDING', 'bank_accounts': [
                    {**payload['bank_account'], 'id': identifier, 'bank_name': 'Fixture Bank'}]}
                value.pop('bank_account')
                beneficiaries[str(identifier)] = value
                return httpx.Response(201, json=value)
            return httpx.Response(200, json=list(beneficiaries.values()))
        if path.startswith('/v2/beneficiaries/'):
            identifier = path.split('/')[3]
            if identifier not in beneficiaries:
                return httpx.Response(404, json={'code': 404})
            if path.endswith('/validation-link'):
                return httpx.Response(200, json={'validation_link': 'https://verify.legaltalent.ai/s/fixture-' + identifier})
            return httpx.Response(200, json=beneficiaries[identifier])
        if path == '/v1/payments':
            if method == 'POST':
                provider_posts['payins'] += 1
                identifier = 'DP-' + payload['order_id']
                amount = Decimal(str(payload['amount']))
                fee = (amount * Decimal('0.0353')).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                payins[identifier] = {**payload, 'id': identifier, 'status': 'PENDING',
                    'balance_fee': float(fee), 'balance_amount': float(amount - fee), 'balance_currency': 'PEN',
                    # Simulates an already matured balance without waiting seven days.
                    'approved_date': (datetime.now(timezone.utc) - timedelta(days=8)).isoformat(),
                    'redirect_url': 'https://checkout-sbx.dlocalgo.com/validate/' + payload['order_id']}
                return httpx.Response(200, json=payins[identifier])
            rows = [value for value in payins.values() if not request.url.params.get('client_email') or value['payer']['email'] == request.url.params['client_email']]
            page = int(request.url.params.get('page', '0'))
            return httpx.Response(200, json={'data': rows[page * 20:(page + 1) * 20], 'totalPages': (len(rows) + 19) // 20})
        if path.startswith('/v1/payments/'):
            value = payins.get(path.split('/')[-1])
            return httpx.Response(200 if value else 404, json=value or {'code': 404})
        if path == '/v2/payouts' and method == 'POST':
            key = request.headers.get('Idempotency-Key')
            if key in payout_keys:
                return httpx.Response(201, json=payouts[payout_keys[key]])
            if not any(x['status'] == 'VERIFIED' and any(a['id'] == payload['bank_account_id'] for a in x['bank_accounts']) for x in beneficiaries.values()):
                return httpx.Response(400, json={'code': 400})
            provider_posts['payouts'] += 1
            identifier = 'PO-' + key
            value = {**payload, 'payout_id': identifier, 'amount': payload['transfer_amount'],
                     'currency_to_pay': 'PEN', 'country': 'PE', 'status': 'PENDING'}
            payouts[identifier], payout_keys[key] = value, identifier
            return httpx.Response(201, json=value)
        if path.startswith('/v1/payouts/'):
            value = payouts.get(path.split('/')[-1])
            return httpx.Response(200 if value else 404, json=value or {'code': 404})
        if path == '/v1/refunds':
            if method == 'POST':
                provider_posts['refunds'] += 1
                original = payins.get(payload['payment_id'])
                if not original:
                    return httpx.Response(404, json={'code': 404})
                identifier = 'REF-' + uuid.uuid4().hex
                value = {**payload, 'id': identifier, 'order_id': original['order_id'],
                         'currency': 'PEN', 'status': 'PENDING'}
                refunds[identifier] = value
                return httpx.Response(200, json=value)
            return httpx.Response(200, json={'data': list(refunds.values()), 'totalPages': 1})
        if path.startswith('/v1/refunds/'):
            value = refunds.get(path.split('/')[-1])
            return httpx.Response(200 if value else 404, json=value or {'code': 404})
    return httpx.Response(404, json={'code': 404})


class OfflineGo(dlocal_go.DLocalGoProvider):
    def __init__(self, transport=None):
        super().__init__(transport=httpx.MockTransport(provider_http))

    @staticmethod
    def public_url():
        origin = os.getenv('E2E_GO_FRONTEND', 'http://127.0.0.1:5180')
        if urlsplit(origin).hostname not in ('127.0.0.1', 'localhost'):
            raise RuntimeError('The fixture only permits a loopback frontend')
        return origin


# Patch every factory, including the class imported by the maintenance job.
# Even if a test exceeds one maintenance interval it cannot use an external API.
dlocal_go.DLocalGoProvider = OfflineGo
dlocal.get_go_provider = OfflineGo
payments.get_payment_provider = OfflineGo
tickets.get_payment_provider = OfflineGo
post_purchase.get_payment_provider = OfflineGo


@app.post('/api/_test/go/verify')
def verify():
    with guard:
        for value in beneficiaries.values():
            value['status'] = 'VERIFIED'
        return {'fixture_only': True, 'beneficiary_ids': list(beneficiaries)}


@app.post('/api/_test/go/pay/{transaction_id}')
def pay(transaction_id: uuid.UUID):
    with guard:
        identifier = 'DP-' + str(transaction_id)
        if identifier not in payins:
            raise HTTPException(404, 'No provider order in this isolated fixture')
        payins[identifier]['status'] = 'PAID'
        return {'fixture_only': True, 'payment_id': identifier, 'amount': payins[identifier]['amount']}


@app.post('/api/_test/go/complete-payout')
def complete():
    with guard:
        for value in payouts.values():
            value['status'] = 'COMPLETED'
        for value in refunds.values():
            value['status'] = 'SUCCESS'
        return {'fixture_only': True, 'payout_ids': list(payouts), 'refund_ids': list(refunds)}


@app.post('/api/_test/go/settle')
def settle():
    with SessionLocal() as db:
        reconcile_go_payments(db, OfflineGo())
        process_go_settlements(db, OfflineGo())
        operations = [{'kind': x.kind, 'status': x.status, 'amount': str(x.amount), 'provider_id': x.provider_id}
                      for x in db.query(models.FinancialOperation).all()]
    with guard:
        return {'fixture_only': True, 'provider_posts': dict(provider_posts), 'operations': operations}


if __name__ == '__main__':
    import uvicorn
    uvicorn.run(app, host='127.0.0.1', port=int(os.getenv('E2E_API_PORT', '8007')))
