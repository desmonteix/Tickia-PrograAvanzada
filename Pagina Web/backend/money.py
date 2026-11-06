"""PEN accounting: buyer pays listed price; charges are borne by the seller."""
from decimal import Decimal, ROUND_HALF_UP


def amounts(price):
    total = Decimal(str(price)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    platform_fee = (total * Decimal("0.10")).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    return total, platform_fee, total - platform_fee
