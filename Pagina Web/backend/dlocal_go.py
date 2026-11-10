"""dLocal Go only: never mix these endpoints with dLocal Platforms/Payouts v3.

Official protocol: https://docs.dlocalgo.com/integration-api/welcome-to-dlocal-go-api
Create payouts: /payouts-integration/payouts-v2
Signed notifications: /payments/notifications#notification-validation
"""
import hashlib
import hmac
import os
import re
from decimal import Decimal
from urllib.parse import urlsplit

import httpx

from .payment_provider import PaymentUnavailable, PaymentDeclined, PaymentUncertain


def money_cents(value):
    try:
        amount = Decimal(str(value))
        if not amount.is_finite() or amount < 0 or amount.as_tuple().exponent < -2:
            raise ValueError()
        return int(amount * 100)
    except (ValueError, ArithmeticError):
        raise PaymentUncertain('Importe de pasarela no válido.') from None


def safe_https_url(value, hosts):
    if not isinstance(value, str):
        return False
    try:
        url = urlsplit(value)
        return bool(url.scheme == 'https' and url.hostname in hosts and url.port in (None, 443)
                    and not url.username and not url.password and '\\' not in value)
    except ValueError:
        return False


class DLocalGoProvider:
    name = 'dlocal_go'

    def __init__(self, transport=None):
        self.transport = transport

    def configured(self):
        values = [os.getenv('DLOCAL_GO_API_KEY', ''), os.getenv('DLOCAL_GO_SECRET_KEY', '')]
        return (os.getenv('DLOCAL_GO_ENV', 'sandbox') in ('sandbox', 'live')
                and all(len(x) >= 8 and not any(c.isspace() for c in x)
                        and 'XXXX' not in x and not x.startswith(('REPLACE', 'YOUR_')) for x in values))

    def enabled(self):
        return self.configured() and os.getenv('PAYMENT_ENABLED', 'false').lower() == 'true'

    def payouts_enabled(self):
        return self.configured() and os.getenv('SETTLEMENT_ENABLED', 'false').lower() == 'true'

    @staticmethod
    def public_url():
        value = os.getenv('DLOCAL_GO_PUBLIC_URL', '').rstrip('/')
        try:
            url = urlsplit(value)
            port = url.port
        except ValueError:
            raise PaymentUnavailable('Configura DLOCAL_GO_PUBLIC_URL con el origen HTTPS de Tickia.') from None
        if (url.scheme != 'https' or not url.hostname or url.username or url.password
                or url.path or url.query or url.fragment or port not in (None, 443) or '\\' in value):
            raise PaymentUnavailable('Configura DLOCAL_GO_PUBLIC_URL con el origen HTTPS de Tickia.')
        return value

    def notification_url(self):
        return self.public_url() + '/api/payments/webhooks/dlocal-go'

    def _request(self, method, path, payload=None, key=None, params=None):
        if not self.configured():
            raise PaymentUnavailable('Faltan las credenciales de dLocal Go.')
        base = ('https://api.dlocalgo.com' if os.getenv('DLOCAL_GO_ENV') == 'live'
                else 'https://api-sbx.dlocalgo.com')
        headers = {'Authorization': 'Bearer ' + os.environ['DLOCAL_GO_API_KEY'] + ':'
                   + os.environ['DLOCAL_GO_SECRET_KEY'], 'Content-Type': 'application/json'}
        if key:
            headers['Idempotency-Key'] = key
        try:
            with httpx.Client(transport=self.transport, timeout=20.0, follow_redirects=False) as client:
                response = client.request(method, base + path, headers=headers, json=payload, params=params)
            if response.status_code == 409 and path != '/v2/beneficiaries':
                # A conflict can refer to an existing order/idempotency key.
                # Never authorize a fresh money order before reconciling it.
                raise PaymentUncertain('Conflicto pendiente de conciliación con dLocal Go.')
            if response.status_code in (400, 402, 404, 409, 422):
                # No provider message/body is exposed: it can contain account data.
                raise PaymentDeclined('La operación fue rechazada por dLocal Go; revisa datos, saldo o límites.',
                                      http_status=response.status_code)
            if response.status_code in (401, 403):
                raise PaymentUnavailable('dLocal Go no autorizó la operación. Revisa la habilitación de la cuenta.')
            if not 200 <= response.status_code < 300:
                raise PaymentUncertain('dLocal Go no confirmó el resultado.')
            result = response.json()
            if not isinstance(result, (dict, list)):
                raise ValueError()
            return result
        except (httpx.HTTPError, ValueError):
            raise PaymentUncertain('Resultado pendiente de conciliación con dLocal Go.') from None

    @staticmethod
    def _id(value):
        if not isinstance(value, (str, int)) or not re.fullmatch(r'[A-Za-z0-9_-]{1,128}', str(value)):
            raise PaymentUncertain('Referencia de pasarela no válida.')
        return str(value)

    def create_checkout(self, order_id, amount_cents, email):
        if not self.enabled():
            raise PaymentUnavailable('Los pagos no están habilitados.')
        callback = self.public_url() + '/?payment_transaction=' + self._id(order_id) + '#wallet'
        result = self._request('POST', '/v1/payments', {
            'country': 'PE', 'currency': 'PEN', 'amount': amount_cents / 100,
            'order_id': str(order_id), 'payer': {'email': email},
            'description': 'Entrada Tickia ' + str(order_id),
            'success_url': callback, 'back_url': callback,
            'notification_url': self.notification_url(),
            # Short-lived checkout + durable reservation: late/asynchronous payments
            # are reconciled before making the ticket available to another buyer.
            'expiration_type': 'MINUTES', 'expiration_value': 10,
            'max_installments': 1, 'allow_3ds': True,
        })
        if not isinstance(result, dict) or not result.get('id') or not safe_https_url(
                result.get('redirect_url'), {'checkout.dlocalgo.com', 'checkout-sbx.dlocalgo.com'}):
            raise PaymentUncertain('No se pudo comprobar el enlace de pago.')
        self._id(result['id'])
        return result

    def retrieve_payment(self, payment_id):
        return self._request('GET', '/v1/payments/' + self._id(payment_id))

    def list_payments(self, email, page=0):
        return self._request('GET', '/v1/payments', params={'country': 'PE', 'client_email': email,
                                                         'page': page, 'size': 20})

    def create_beneficiary(self, payload):
        return self._request('POST', '/v2/beneficiaries', payload)

    def list_beneficiaries(self):
        return self._request('GET', '/v2/beneficiaries')

    def retrieve_beneficiary(self, beneficiary_id):
        return self._request('GET', '/v2/beneficiaries/' + self._id(beneficiary_id))

    def validation_link(self, beneficiary_id):
        result = self._request('GET', '/v2/beneficiaries/' + self._id(beneficiary_id) + '/validation-link')
        link = result.get('validation_link') if isinstance(result, dict) else None
        if link is not None and not safe_https_url(link, {'verify.legaltalent.ai'}):
            raise PaymentUncertain('No se pudo verificar el enlace de identidad.')
        return link

    def create_payout(self, bank_account_id, amount_cents, operation_id, purpose):
        return self.submit_payout({
            'bank_account_id': bank_account_id, 'transfer_amount': amount_cents / 100,
            'purpose': purpose, 'description': 'Tickia ' + operation_id,
            'notification_url': self.notification_url(),
        }, operation_id)

    def submit_payout(self, payload, operation_id):
        return self._request('POST', '/v2/payouts', payload, key=operation_id)

    def retrieve_payout(self, payout_id):
        return self._request('GET', '/v1/payouts/' + self._id(payout_id))

    def create_refund(self, payment_id, amount_cents):
        # Go does not document idempotency for refunds: never blindly resend.
        return self._request('POST', '/v1/refunds', {
            'payment_id': self._id(payment_id), 'amount': amount_cents / 100,
            'notification_url': self.notification_url(),
        })

    def retrieve_refund(self, refund_id):
        return self._request('GET', '/v1/refunds/' + self._id(refund_id))

    def list_refunds(self, page=0):
        return self._request('GET', '/v1/refunds', params={'page': page, 'size': 20})

    def verify_notification(self, raw, authorization):
        if not self.configured() or not isinstance(authorization, str):
            return False
        match = re.fullmatch(r'V2-HMAC-SHA256, Signature: ([a-fA-F0-9]{64})', authorization)
        if not match:
            return False
        digest = hmac.new(os.environ['DLOCAL_GO_SECRET_KEY'].encode(),
                          os.environ['DLOCAL_GO_API_KEY'].encode() + raw, hashlib.sha256).hexdigest()
        return hmac.compare_digest(digest, match[1].lower())
