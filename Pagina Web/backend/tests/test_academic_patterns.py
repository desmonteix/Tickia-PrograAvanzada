"""Contratos observables de los cuatro patrones exigidos por la rúbrica."""
import sys
from pathlib import Path
from decimal import Decimal
import unittest

sys.path.insert(0, str(Path(__file__).parents[2]))
from backend.academic.patterns import (OrderBuilder, StandardShipping, ExpressShipping,
    EconomyShipping, BasePrice, PercentageDiscount, VolumeDiscount, CouponDiscount, OrderState, money)


class AcademicPatternsTests(unittest.TestCase):
    def test_builder_merges_variants_and_freezes_a_multi_item_order(self):
        builder = OrderBuilder().add_item(1, 1, '10.00').add_item(2, 2, '25.00').add_item(1, 1, '10.00')
        order = builder.with_coupon('GRUPO', 10).shipping(StandardShipping(), '12.00', 'Lima').build()
        self.assertEqual(len(order.items), 2)
        self.assertEqual(order.units, 4)
        self.assertEqual(order.subtotal, Decimal('70.00'))
        self.assertEqual(order.discount, Decimal('8.89'))  # 3% por volumen, luego 10% de cupón.
        self.assertEqual(order.total, Decimal('73.11'))
        builder.add_item(3, 1, '1.00')
        self.assertEqual(len(order.items), 2)

    def test_discount_decorators_accumulate_and_round_each_step(self):
        price = PercentageDiscount(PercentageDiscount(BasePrice(Decimal('100.00')), Decimal('10'), 'cupón'), Decimal('5'), 'volumen')
        self.assertEqual(price.total(), Decimal('85.50'))
        self.assertEqual(len(price.discounts()), 2)
        for value in (-1, 101):
            with self.assertRaises(ValueError):
                PercentageDiscount(BasePrice(Decimal('10')), Decimal(value), 'inválido')

    def test_volume_decorator_is_transparent_below_the_minimum_and_coupon_stacks_on_top(self):
        base = BasePrice(Decimal('100.00'))
        self.assertEqual(VolumeDiscount(base, Decimal('3'), 'volumen', units=2).total(), Decimal('100.00'))
        self.assertEqual(VolumeDiscount(base, Decimal('3'), 'volumen', units=2).discounts(), ())
        volume = VolumeDiscount(base, Decimal('3'), 'volumen', units=3)
        price = CouponDiscount(volume, Decimal('10'), 'Cupón X', code='X')
        self.assertEqual(price.total(), Decimal('87.30'))      # 100 -> 97,00 -> 87,30
        self.assertEqual([label for label, _ in price.discounts()], ['volumen', 'Cupón X'])
        order = OrderBuilder().add_item(1, 2, '50.00').with_coupon('X', 10).build()
        self.assertEqual([label for label, _ in order.discounts], ['Cupón X'])

    def test_builder_total_matches_the_stored_procedure_formula(self):
        # confirmar_pedido: neto = subtotal - ROUND(subtotal*0,03) si hay 3+ unidades; luego - ROUND(neto*cupón).
        import random
        rng = random.Random(20261118)
        for _ in range(500):
            items = [(i, rng.randint(1, 4), money(rng.uniform(1, 900))) for i in range(rng.randint(1, 4))]
            pct = Decimal(rng.choice([0, 5, 10, 15, 20, 25, 30]))
            builder = OrderBuilder()
            for variant, quantity, price in items:
                builder.add_item(variant, quantity, price)
            if pct:
                builder.with_coupon('C', pct)
            order = builder.build()
            units = sum(quantity for _, quantity, _ in items)
            neto = money(sum(price * quantity for _, quantity, price in items))
            if units >= 3:
                neto -= money(neto * Decimal('0.03'))
            if pct:
                neto -= money(neto * pct / 100)
            self.assertEqual(order.total, neto)

    def test_state_cancels_only_pending_orders_like_the_trigger(self):
        self.assertEqual(OrderState.from_name('pendiente').transition('cancelado').name, 'cancelado')
        for name in ('pagado', 'enviado', 'entregado', 'cancelado'):
            with self.subTest(estado=name), self.assertRaises(ValueError):
                OrderState.from_name(name).transition('cancelado')
        with self.assertRaises(ValueError):
            OrderState.from_name('cancelado').transition('pagado')

    def test_courier_strategies_have_distinct_and_deterministic_costs(self):
        costs = [strategy.calculate(Decimal('10'), 'Arequipa', 2) for strategy in (StandardShipping(), ExpressShipping(), EconomyShipping())]
        self.assertEqual(len(set(costs)), 3)
        self.assertTrue(all(value > 0 and value == value.quantize(Decimal('.01')) for value in costs))

    def test_state_allows_only_the_required_lifecycle(self):
        state = OrderState.from_name('pendiente')
        for next_state in ('pagado', 'enviado', 'entregado'):
            state = state.transition(next_state)
            self.assertEqual(state.name, next_state)
        with self.assertRaises(ValueError):
            state.transition('pendiente')
        with self.assertRaises(ValueError):
            OrderState.from_name('pendiente').transition('entregado')

    def test_builder_rejects_invalid_or_empty_orders(self):
        with self.assertRaises(ValueError):
            OrderBuilder().build()
        for quantity in (0, -1, 101):
            with self.assertRaises(ValueError):
                OrderBuilder().add_item(1, quantity, '10.00')

    def test_builder_shipping_uses_final_items_regardless_of_configuration_order(self):
        early = OrderBuilder().shipping(ExpressShipping(), '10', 'Arequipa').add_item(1, 2, '25').build()
        late = OrderBuilder().add_item(1, 2, '25').shipping(ExpressShipping(), '10', 'Arequipa').build()
        self.assertEqual(early, late)
        self.assertEqual(early.shipping_cost, Decimal('18.50'))
