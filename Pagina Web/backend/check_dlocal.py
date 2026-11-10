"""Deployment check: only GET /v1/me, never prints keys or account data."""
import argparse
import json
import os

from .dlocal_go import DLocalGoProvider
from .go_fees import fee_terms
from .payment_provider import PaymentUnavailable, PaymentDeclined, PaymentUncertain


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--check-api', action='store_true')
    args = parser.parse_args()
    provider = DLocalGoProvider()
    result = {'provider_selected': os.getenv('PAYMENT_PROVIDER') == 'dlocal_go',
              'environment': os.getenv('DLOCAL_GO_ENV', 'sandbox'),
              'credentials_present': provider.configured(), 'payin_enabled': provider.enabled(),
              'payout_enabled': provider.payouts_enabled()}
    try:
        provider.public_url()
        result['public_url_valid'] = True
        fee_terms()
        result['fee_configuration_valid'] = True
        if args.check_api:
            provider._request('GET', '/v1/me')
            result['api_authenticated'] = True
    except (PaymentUnavailable, PaymentDeclined, PaymentUncertain) as exc:
        result['error'] = str(exc)
        print(json.dumps(result, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False))
    return 0 if result['provider_selected'] and result['credentials_present'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
