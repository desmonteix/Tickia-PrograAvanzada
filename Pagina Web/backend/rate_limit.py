"""Only authenticated gateways may supply a rate-limit identity."""
import hmac
import ipaddress
import os
import re

from slowapi import Limiter
from slowapi.util import get_remote_address


def valid_proxy_secret(secret):
    return bool(re.fullmatch(r'[A-Za-z0-9_-]{32,128}', secret or ''))


def client_address(request):
    secret = os.getenv('PROXY_SHARED_SECRET', '')
    supplied = request.headers.get('X-Tickia-Proxy-Secret', '')
    if valid_proxy_secret(secret) and hmac.compare_digest(secret.encode(), supplied.encode()):
        try:
            return str(ipaddress.ip_address(request.headers.get('X-Tickia-Client-IP', '')))
        except ValueError:
            pass
    return get_remote_address(request)


limiter = Limiter(key_func=client_address)
