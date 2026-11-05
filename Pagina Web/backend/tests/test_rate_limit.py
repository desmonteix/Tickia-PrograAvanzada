"""Proxy identity and rate limits, without trusting public forwarded headers."""
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).parents[2]))
os.environ['TICKIA_LOAD_ENV'] = '0'
from fastapi import FastAPI, Request
from fastapi.testclient import TestClient
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from backend.rate_limit import client_address

SECRET = 'isolated-proxy-test-' + 'a' * 32


class ProxyIdentityTests(unittest.TestCase):
    def setUp(self):
        self.env = patch.dict(os.environ, {'PROXY_SHARED_SECRET': SECRET})
        self.env.start()
        app = FastAPI()
        limiter = Limiter(key_func=client_address)
        app.state.limiter = limiter
        app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

        @app.get('/limited')
        @limiter.limit('1/minute')
        def limited(request: Request):
            return {'address': client_address(request)}

        self.client = TestClient(app)

    def tearDown(self):
        self.client.close()
        self.env.stop()

    def headers(self, address, secret=SECRET):
        return {'X-Tickia-Client-IP': address, 'X-Tickia-Proxy-Secret': secret}

    def test_distinct_verified_clients_have_separate_limits(self):
        first = self.headers('203.0.113.1')
        second = self.headers('203.0.113.2')
        self.assertEqual(self.client.get('/limited', headers=first).status_code, 200)
        self.assertEqual(self.client.get('/limited', headers=first).status_code, 429)
        self.assertEqual(self.client.get('/limited', headers=second).status_code, 200)

    def test_spoofed_forwarded_headers_cannot_reset_limits(self):
        self.assertEqual(self.client.get('/limited', headers=self.headers('203.0.113.1', 'wrong')).status_code, 200)
        spoof = {**self.headers('203.0.113.2', 'wrong'), 'X-Forwarded-For': '203.0.113.3'}
        self.assertEqual(self.client.get('/limited', headers=spoof).status_code, 429)

    def test_invalid_ip_falls_back_to_peer(self):
        response = self.client.get('/limited', headers=self.headers('203.0.113.1, 203.0.113.2'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['address'], 'testclient')

    def test_ipv6_is_canonicalized(self):
        response = self.client.get('/limited', headers=self.headers('2001:db8:0:0::1'))
        self.assertEqual(response.json()['address'], '2001:db8::1')
