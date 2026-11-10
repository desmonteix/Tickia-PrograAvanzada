"""Protocol regressions against the official dLocal Go contract (no real money)."""
import hashlib
import hmac
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).parents[2]))


class DLocalProtocolTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {
            'DLOCAL_GO_ENV': 'sandbox', 'DLOCAL_GO_API_KEY': 'offline_api_key',
            'DLOCAL_GO_SECRET_KEY': 'offline_secret_key', 'PAYMENT_ENABLED': 'true',
            'DLOCAL_GO_PUBLIC_URL': 'https://tickia.example',
        })
        self.env.start()
        self.addCleanup(self.env.stop)

    def provider(self, handler):
        from backend.dlocal_go import DLocalGoProvider
        return DLocalGoProvider(transport=httpx.MockTransport(handler))

    def test_checkout_uses_go_bearer_and_price_in_soles(self):
        import json
        def handler(request):
            self.assertEqual(str(request.url), 'https://api-sbx.dlocalgo.com/v1/payments')
            self.assertEqual(request.headers['Authorization'], 'Bearer offline_api_key:offline_secret_key')
            body = json.loads(request.content)
            self.assertEqual(body['amount'], 123.45)
            self.assertEqual(body['currency'], 'PEN')
            self.assertEqual(body['order_id'], 'order-1')
            self.assertEqual(body['max_installments'], 1)
            self.assertEqual(body['expiration_type'], 'MINUTES')
            return httpx.Response(200, json={'id': 'DP-1', 'redirect_url': 'https://checkout-sbx.dlocalgo.com/validate/token'})
        result = self.provider(handler).create_checkout('order-1', 12345, 'buyer@example.com')
        self.assertEqual(result['id'], 'DP-1')

    def test_untrusted_checkout_redirect_is_rejected(self):
        from backend.payment_provider import PaymentUncertain
        p = self.provider(lambda r: httpx.Response(200, json={'id': 'DP-1', 'redirect_url': 'https://attacker.example/pay'}))
        with self.assertRaises(PaymentUncertain):
            p.create_checkout('order-1', 10000, 'buyer@example.com')

    def test_payout_uses_documented_v2_route_and_idempotency(self):
        import json
        def handler(request):
            self.assertEqual(request.url.path, '/v2/payouts')
            self.assertEqual(request.headers['Idempotency-Key'], 'operation-1')
            body = json.loads(request.content)
            self.assertEqual(body['bank_account_id'], 17)
            self.assertEqual(body['transfer_amount'], 85.47)
            self.assertEqual(body['purpose'], 'ENTERTAINMENT')
            return httpx.Response(201, json={'payout_id': '987', 'amount': 85.47, 'currency_to_pay': 'PEN', 'status': 'PENDING'})
        self.assertEqual(self.provider(handler).create_payout(17, 8547, 'operation-1', 'ENTERTAINMENT')['status'], 'PENDING')

    def test_signature_uses_original_bytes_and_constant_scheme(self):
        p = self.provider(lambda r: httpx.Response(500))
        raw = b'{ "payment_id": "DP-1" }'
        signature = hmac.new(b'offline_secret_key', b'offline_api_key' + raw, hashlib.sha256).hexdigest()
        header = 'V2-HMAC-SHA256, Signature: ' + signature
        self.assertTrue(p.verify_notification(raw, header))
        self.assertFalse(p.verify_notification(b'{"payment_id":"DP-1"}', header))
        self.assertFalse(p.verify_notification(raw, 'Bearer ' + signature))

    def test_non_json_and_transport_errors_stay_uncertain(self):
        from backend.payment_provider import PaymentUncertain
        p = self.provider(lambda r: httpx.Response(200, content=b'not json'))
        with self.assertRaises(PaymentUncertain):
            p.retrieve_payment('DP-1')

    def test_bad_environment_and_path_are_not_used(self):
        from backend.payment_provider import PaymentUnavailable, PaymentUncertain
        p = self.provider(lambda r: self.fail('Network must not be called'))
        with self.assertRaises(PaymentUncertain):
            p.retrieve_payment('../beneficiaries')
        with patch.dict(os.environ, {'DLOCAL_GO_ENV': 'https://attacker.example'}):
            self.assertFalse(p.enabled())
            with self.assertRaises(PaymentUnavailable):
                p.retrieve_payment('DP-1')

    def test_disable_new_payments_does_not_disable_refund_lookup(self):
        p = self.provider(lambda r: httpx.Response(200, json={'id': 'REF-1', 'status': 'SUCCESS'}))
        with patch.dict(os.environ, {'PAYMENT_ENABLED': 'false'}):
            self.assertFalse(p.enabled())
            self.assertEqual(p.retrieve_refund('REF-1')['status'], 'SUCCESS')

    def test_deployment_probe_only_reads_account_and_never_prints_credentials(self):
        import io
        from contextlib import redirect_stdout
        from backend import check_dlocal
        calls = []
        def handler(request):
            calls.append((request.method, request.url.path))
            return httpx.Response(200, json={'private_account_data': 'must_not_print'})
        env = {'PAYMENT_PROVIDER': 'dlocal_go', 'DLOCAL_GO_PAYIN_PERCENT': '3.53',
            'DLOCAL_GO_PAYIN_FIXED_PEN': '0', 'DLOCAL_GO_PAYOUT_PERCENT': '0',
            'DLOCAL_GO_PAYOUT_FIXED_PEN': '1', 'DLOCAL_GO_FEES_TAX_PERCENT': '0',
            'DLOCAL_GO_MIN_PAYOUT_PEN': '5', 'DLOCAL_GO_PAYOUT_PURPOSE': 'ENTERTAINMENT'}
        output = io.StringIO()
        with patch.dict(os.environ, env), patch.object(check_dlocal, 'DLocalGoProvider', lambda: self.provider(handler)), \
                patch.object(sys, 'argv', ['check_dlocal', '--check-api']), redirect_stdout(output):
            self.assertEqual(check_dlocal.main(), 0)
        self.assertEqual(calls, [('GET', '/v1/me')])
        for private in ('offline_secret_key', 'offline_api_key', 'private_account_data', 'must_not_print'):
            self.assertNotIn(private, output.getvalue())

    def test_conflicts_cannot_authorize_new_money_orders(self):
        from backend.payment_provider import PaymentUncertain, PaymentDeclined
        p = self.provider(lambda r: httpx.Response(409, json={'code': 'existing_order'}))
        with self.assertRaises(PaymentUncertain):
            p.create_checkout('order-1', 10000, 'buyer@example.com')
        with self.assertRaises(PaymentUncertain):
            p.submit_payout({'bank_account_id': 17, 'transfer_amount': 85.47}, 'operation-1')
        with self.assertRaises(PaymentDeclined):
            p.create_beneficiary({'document': '87654321'})


if __name__ == '__main__':
    unittest.main()
