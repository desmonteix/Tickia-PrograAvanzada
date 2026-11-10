"""Culqi charges, verified against the provider. No simulated settlements.

Protocol: https://apidocs.culqi.com/#tag/Cargos/operation/crear-cargo
Seller disbursements require a separate contracted marketplace integration.
"""
import os
import httpx


class PaymentUnavailable(Exception):
    pass


class PaymentDeclined(Exception):
    def __init__(self, message='La pasarela rechazó la operación.', http_status=None):
        super().__init__(message)
        self.http_status = http_status


class PaymentUncertain(Exception):
    pass


class CulqiProvider:
    name = 'culqi'
    def enabled(self):
        key = os.getenv("CULQI_PRIVATE_KEY", "")
        expected = "sk_live_" if os.getenv("ENVIRONMENT") == "production" else "sk_test_"
        return os.getenv("PAYMENT_ENABLED", "false").lower() == "true" and key.startswith(expected) and len(key) > 16

    def _request(self, method, path, payload=None):
        if not self.enabled():
            raise PaymentUnavailable("Los pagos aún no están habilitados.")
        try:
            response = httpx.request(
                method, "https://api.culqi.com/v2" + path,
                headers={"Authorization": "Bearer " + os.environ["CULQI_PRIVATE_KEY"],
                         "Content-Type": "application/json", "x-culqi-product": "online"},
                json=payload, timeout=15.0,
            )
        except httpx.HTTPError as exc:
            raise PaymentUncertain("No se pudo confirmar el resultado del pago.") from exc
        if response.status_code in (400, 402, 422):
            raise PaymentDeclined("La pasarela rechazó el pago o requiere autenticación adicional.")
        if response.status_code >= 400:
            raise PaymentUncertain("La pasarela no confirmó la operación.")
        try:
            return response.json(), response.status_code
        except ValueError as exc:
            raise PaymentUncertain("Respuesta de pasarela inválida.") from exc

    def create_charge(self, token, amount_cents, email, metadata):
        data, code = self._request("POST", "/charges", {
            "amount": amount_cents, "currency_code": "PEN", "email": email,
            "source_id": token, "capture": True, "metadata": metadata,
        })
        if code != 201:
            raise PaymentUncertain("La pasarela requiere verificación adicional.")
        return data

    def retrieve_charge(self, charge_id):
        return self._request("GET", "/charges/" + charge_id)[0]

    def release_funds_to_seller(self, charge_id, amount_cents=None, operation_id=None, seller_id=None):
        raise PaymentUnavailable("El desembolso a vendedores requiere integración y validación operativa.")

    def refund_buyer(self, charge_id, amount_cents, operation_id):
        if os.getenv('SETTLEMENT_ENABLED', 'false').lower() != 'true':
            raise PaymentUnavailable('Las liquidaciones no están habilitadas.')
        # A separate gate allows refunds after disabling new checkouts.
        key = os.getenv('CULQI_PRIVATE_KEY', '')
        expected = 'sk_live_' if os.getenv('ENVIRONMENT') == 'production' else 'sk_test_'
        if not key.startswith(expected) or len(key) <= 16:
            raise PaymentUnavailable('Falta la credencial de reembolso del entorno correcto.')
        try:
            response = httpx.post('https://api.culqi.com/v2/refunds',
                headers={'Authorization': 'Bearer ' + key, 'Content-Type': 'application/json', 'x-culqi-product': 'online'},
                json={'charge_id': charge_id, 'amount': amount_cents, 'reason': 'solicitud_comprador'}, timeout=15.0)
            data = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise PaymentUncertain('Reembolso pendiente de conciliación.') from error
        if response.status_code != 201 or not isinstance(data, dict) or data.get('object') != 'refund' or data.get('charge_id') != charge_id or data.get('amount') != amount_cents or str(data.get('status', '')).casefold() != 'completa' or not isinstance(data.get('id'), str) or not data['id'].startswith('ref_'):
            raise PaymentUncertain('La pasarela aún no confirmó un reembolso completo.')
        return {'operation_id': operation_id, 'reference': data['id'], 'amount_cents': amount_cents, 'status': 'SUCCEEDED'}

    def refund_is_complete(self, charge_id, amount_cents):
        if os.getenv('SETTLEMENT_ENABLED', 'false').lower() != 'true':
            return False
        key = os.getenv('CULQI_PRIVATE_KEY', '')
        expected = 'sk_live_' if os.getenv('ENVIRONMENT') == 'production' else 'sk_test_'
        if not key.startswith(expected) or len(key) <= 16:
            return False
        response = httpx.get('https://api.culqi.com/v2/charges/' + charge_id,
            headers={'Authorization':'Bearer ' + key}, timeout=15.0)
        if response.status_code != 200:
            return False
        data = response.json()
        return bool(isinstance(data, dict) and data.get('object') == 'charge' and data.get('id') == charge_id
            and data.get('currency_code') == 'PEN' and data.get('amount') == amount_cents
            and data.get('amount_refunded') == amount_cents)


def get_payment_provider():
    if os.getenv('PAYMENT_PROVIDER', 'culqi') == 'dlocal_go':
        from .dlocal_go import DLocalGoProvider
        return DLocalGoProvider()
    return CulqiProvider()
