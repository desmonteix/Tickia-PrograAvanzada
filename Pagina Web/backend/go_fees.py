"""Explicit contractual fee configuration; never guess fees from a payin headline."""
import hashlib
import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from .payment_provider import PaymentUnavailable

CENT = Decimal('0.01')


def quantize(value):
    return value.quantize(CENT, rounding=ROUND_HALF_UP)


def fee_terms():
    fields = {
        'payin_percent': 'DLOCAL_GO_PAYIN_PERCENT', 'payin_fixed': 'DLOCAL_GO_PAYIN_FIXED_PEN',
        'payout_percent': 'DLOCAL_GO_PAYOUT_PERCENT', 'payout_fixed': 'DLOCAL_GO_PAYOUT_FIXED_PEN',
        'tax_rate': 'DLOCAL_GO_FEES_TAX_PERCENT', 'minimum': 'DLOCAL_GO_MIN_PAYOUT_PEN',
    }
    try:
        values = {name: Decimal(os.environ[env]) for name, env in fields.items()}
        if any(not x.is_finite() or x < 0 or x > 10000 for x in values.values()):
            raise ValueError()
        if any(values[x] >= 100 for x in ('payin_percent', 'payout_percent', 'tax_rate')) or values['minimum'] <= 0:
            raise ValueError()
        purpose = os.environ['DLOCAL_GO_PAYOUT_PURPOSE']
        # These describe the actual marketplace activity, unlike payroll/rewards.
        if purpose not in ('ENTERTAINMENT', 'DIGITAL_GOODS', 'SUPPLIER', 'PHYSICAL_GOODS', 'OTHER_SERVICES'):
            raise ValueError()
    except (KeyError, ValueError, InvalidOperation):
        raise PaymentUnavailable('Falta configurar el tarifario, el mínimo o el propósito aprobado de dLocal Go.') from None
    result = {name: str(value) for name, value in values.items()}
    result['purpose'] = purpose
    result['hash'] = hashlib.sha256(json.dumps(result, sort_keys=True).encode()).hexdigest()
    return result


def payin_estimate(total, terms):
    return quantize((total * Decimal(terms['payin_percent']) / 100 + Decimal(terms['payin_fixed']))
                    * (1 + Decimal(terms['tax_rate']) / 100))


def payout_amount(seller_before_payout, terms):
    """Fee contract: percentage of amount sent + fixed, plus the configured tax.

    Solve net + payout fee = seller's available amount; absorb at most a cent
    of upward rounding into the fee, rather than overdraw the reserved balance.
    """
    tax = 1 + Decimal(terms['tax_rate']) / 100
    rate = Decimal(terms['payout_percent']) / 100 * tax
    fixed = Decimal(terms['payout_fixed']) * tax
    net = quantize((seller_before_payout - fixed) / (1 + rate))
    fee = quantize(net * rate + fixed)
    if net + fee > seller_before_payout:
        net -= CENT
    return net, seller_before_payout - net
