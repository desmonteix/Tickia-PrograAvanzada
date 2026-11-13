"""PEN accounting; buyer subsidies never reduce the seller's listed-price base."""
from decimal import Decimal, ROUND_HALF_UP


def amounts(price, commission_rate=Decimal('.10'), buyer_discount=Decimal('0')):
    listed = Decimal(str(price)).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    rate, discount = Decimal(str(commission_rate)), Decimal(str(buyer_discount))
    if (not listed.is_finite() or listed <= 0 or not rate.is_finite() or not 0 <= rate <= 1
            or not discount.is_finite() or discount < 0 or discount >= listed
            or discount != discount.quantize(Decimal('.01'))):
        raise ValueError('Importes o comisión inválidos.')
    platform_fee = (listed * rate).quantize(Decimal('.01'), rounding=ROUND_HALF_UP)
    return listed - discount, platform_fee, listed - platform_fee
