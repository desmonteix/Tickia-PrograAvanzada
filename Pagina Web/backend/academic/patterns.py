"""Patrones usados en cotización y ciclo de vida, sin dependencias de infraestructura."""
from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal, ROUND_HALF_UP


def money(value):
    value = Decimal(str(value))
    if not value.is_finite():
        raise ValueError('El importe debe ser finito.')
    return value.quantize(Decimal('.01'), rounding=ROUND_HALF_UP)


class ShippingStrategy(ABC):
    @abstractmethod
    def calculate(self, base: Decimal, department: str, units: int) -> Decimal:
        """Tarifas educativas, no cotizaciones de un courier real."""


class StandardShipping(ShippingStrategy):
    def calculate(self, base, department, units):
        return money(base * (Decimal('1') if department.casefold() == 'lima' else Decimal('1.35')))


class ExpressShipping(ShippingStrategy):
    def calculate(self, base, department, units):
        return money(base * (Decimal('1.40') if department.casefold() == 'lima' else Decimal('1.75')) + Decimal('.50') * units)


class EconomyShipping(ShippingStrategy):
    def calculate(self, base, department, units):
        return money(base * (Decimal('.85') if department.casefold() == 'lima' else Decimal('1.15')))


SHIPPING_STRATEGIES = {'estandar': StandardShipping, 'rapido': ExpressShipping, 'economico': EconomyShipping}


class PriceComponent(ABC):
    @abstractmethod
    def total(self) -> Decimal:
        pass

    def discounts(self):
        return ()


@dataclass(frozen=True)
class BasePrice(PriceComponent):
    amount: Decimal

    def total(self):
        return money(self.amount)


@dataclass(frozen=True)
class PercentageDiscount(PriceComponent):
    """Decorator: envuelve otro componente y conserva su desglose."""
    wrapped: PriceComponent
    percentage: Decimal
    label: str

    def __post_init__(self):
        if not self.percentage.is_finite() or not 0 <= self.percentage <= 100:
            raise ValueError('Porcentaje de descuento inválido.')

    def total(self):
        return money(self.wrapped.total() - money(self.wrapped.total() * self.percentage / 100))

    def discounts(self):
        return self.wrapped.discounts() + ((self.label, self.wrapped.total() - self.total()),)


@dataclass(frozen=True)
class OrderItem:
    variant_id: int
    quantity: int
    unit_price: Decimal


@dataclass(frozen=True)
class OrderDraft:
    items: tuple[OrderItem, ...]
    units: int
    subtotal: Decimal
    discount: Decimal
    shipping_cost: Decimal
    total: Decimal
    discounts: tuple
    coupon: str | None


class OrderBuilder:
    def __init__(self):
        self._items = {}
        self._coupon = None
        self._coupon_percentage = Decimal('0')
        self._shipping = None

    def add_item(self, variant_id, quantity, unit_price):
        if not isinstance(quantity, int) or isinstance(quantity, bool) or quantity < 1:
            raise ValueError('La cantidad debe ser un entero positivo.')
        price = money(unit_price)
        previous = self._items.get(variant_id)
        quantity += previous.quantity if previous else 0
        if quantity > 100 or price <= 0 or (previous and previous.unit_price != price):
            raise ValueError('Cantidad o precio inválido.')
        self._items[variant_id] = OrderItem(variant_id, quantity, price)
        if len(self._items) > 20:
            raise ValueError('Máximo 20 variantes por pedido.')
        return self

    def with_coupon(self, code, percentage):
        self._coupon = code
        self._coupon_percentage = Decimal(str(percentage))
        return self

    def shipping(self, strategy, base, department):
        self._shipping = (strategy, money(base), department)
        return self

    def build(self):
        if not self._items:
            raise ValueError('El pedido no contiene artículos.')
        items = tuple(self._items[key] for key in sorted(self._items))
        units = sum(item.quantity for item in items)
        subtotal = money(sum((item.unit_price * item.quantity for item in items), Decimal('0')))
        price = BasePrice(subtotal)
        if units >= 3:
            price = PercentageDiscount(price, Decimal('3'), 'Volumen (3 unidades o más)')
        if self._coupon:
            price = PercentageDiscount(price, self._coupon_percentage, 'Cupón ' + self._coupon)
        shipping_cost = self._shipping[0].calculate(self._shipping[1], self._shipping[2], units) if self._shipping else Decimal('0.00')
        return OrderDraft(items, units, subtotal, subtotal - price.total(), shipping_cost,
                          price.total() + shipping_cost, price.discounts(), self._coupon)


class OrderState(ABC):
    name: str

    def transition(self, next_name):
        action = {'pagado': self.pay, 'enviado': self.ship, 'entregado': self.deliver}.get(next_name)
        if action is None:
            self.invalid(next_name)
        return action()

    def invalid(self, target):
        raise ValueError(f'Transición no permitida: {self.name} → {target}.')

    def pay(self):
        self.invalid('pagado')

    def ship(self):
        self.invalid('enviado')

    def deliver(self):
        self.invalid('entregado')

    @staticmethod
    def from_name(name):
        states = {'pendiente': PendingState, 'pagado': PaidState, 'enviado': ShippedState,
                  'entregado': DeliveredState, 'cancelado': CancelledState}
        if name not in states:
            raise ValueError('Estado desconocido.')
        return states[name]()


class PendingState(OrderState):
    name = 'pendiente'

    def pay(self):
        return PaidState()


class PaidState(OrderState):
    name = 'pagado'

    def ship(self):
        return ShippedState()


class ShippedState(OrderState):
    name = 'enviado'

    def deliver(self):
        return DeliveredState()


class DeliveredState(OrderState):
    name = 'entregado'


class CancelledState(OrderState):
    name = 'cancelado'


class OrderContext:
    """Contexto State: delega el comportamiento al estado actual del pedido."""
    def __init__(self, name):
        self.state = OrderState.from_name(name)

    def transition(self, target):
        self.state = self.state.transition(target)
        return self.state
