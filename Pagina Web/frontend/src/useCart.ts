import { useEffect, useState } from 'react';
import { mergeCart, restoreCart } from './cart';
import type { CartLine } from './cart';

export function useCart(enabled = true) {
  const [items, setItems] = useState<CartLine[]>(() => {
    try {
      return restoreCart(window.localStorage.getItem('tickia:cart:v1'));
    } catch {
      return [];
    }
  });
  useEffect(() => {
    if (!enabled) return;
    try {
      window.localStorage.setItem('tickia:cart:v1', JSON.stringify(items));
    } catch {
      /* El carrito sigue funcionando cuando el navegador bloquea almacenamiento. */
    }
  }, [items, enabled]);
  return {
    items,
    add: (line: CartLine) => setItems(mergeCart(items, line)),
    quantity: (id: number, quantity: number) =>
      setItems((current) =>
        current.map((line) => (line.variant_id === id ? { ...line, quantity } : line)),
      ),
    remove: (id: number) => setItems((current) => current.filter((line) => line.variant_id !== id)),
    clear: () => setItems([]),
    count: items.reduce((sum, line) => sum + line.quantity, 0),
  };
}
