"""Datos sintéticos reproducibles: se verifican importes, claves y fechas."""
from decimal import Decimal
from pathlib import Path
import sys
import unittest

sys.path.insert(0,str(Path(__file__).parents[2]))
from backend.academic.generation import generate_orders


class AcademicGenerationTests(unittest.TestCase):
    def test_seed_produces_repeatable_valid_multi_item_orders(self):
        users=[dict(id_usuario=1,id_distrito=1,departamento='Lima'),dict(id_usuario=2,id_distrito=2,departamento='Cusco')]
        variants=[dict(id_variante=1,precio=Decimal('10.50')),dict(id_variante=2,precio=Decimal('25.00')),dict(id_variante=3,precio=Decimal('7.25'))]
        couriers=[dict(id_courier=1,costo_base=Decimal('12'),estrategia='estandar')]
        first=generate_orders(users,variants,couriers,count=30,seed=7)
        second=generate_orders(users,variants,couriers,count=30,seed=7)
        self.assertEqual(first,second)
        self.assertNotEqual(first,generate_orders(users,variants,couriers,count=30,seed=8))
        self.assertTrue(any(len(order.items)>1 for order in first))
        for order in first:
            self.assertIn(order.user_id,(1,2))
            self.assertEqual(len({item[0] for item in order.items}),len(order.items))
            subtotal=sum(quantity*price for _,quantity,price in order.items)
            discount=(subtotal*Decimal('.03')).quantize(Decimal('.01'),rounding='ROUND_HALF_UP') if sum(item[1] for item in order.items)>=3 else 0
            self.assertEqual(order.total,subtotal-discount+order.shipping_cost)
            if order.received:
                self.assertGreaterEqual(order.received,order.sent)

    def test_empty_dimensions_or_invalid_count_are_rejected(self):
        for count in (0,-1,100001):
            with self.assertRaises(ValueError):
                generate_orders([],[],[],count=count)
