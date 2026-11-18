export interface CartLine {
  variant_id: number;
  product_id: number;
  title: string;
  quantity: number;
  unit_cents: number;
  variant: string;
  stock: number;
  image: string | null;
}

export function mergeCart(current: CartLine[], incoming: CartLine): CartLine[] {
  const previous = current.find((item) => item.variant_id === incoming.variant_id);
  const quantity = (previous?.quantity ?? 0) + incoming.quantity;
  if (!Number.isInteger(quantity) || quantity < 1 || quantity > Math.min(100, incoming.stock))
    throw new Error('La cantidad supera el stock disponible o el máximo de 100 unidades.');
  if (!previous && current.length >= 20)
    throw new Error('Puedes comprar hasta 20 variantes por pedido.');
  return previous
    ? current.map((item) =>
        item.variant_id === incoming.variant_id ? { ...incoming, quantity } : item,
      )
    : [...current, { ...incoming, quantity }];
}

export function restoreCart(raw: string | null): CartLine[] {
  try {
    const parsed: unknown = JSON.parse(raw ?? '[]');
    if (!Array.isArray(parsed) || parsed.length > 20) return [];
    const result: CartLine[] = [];
    for (const value of parsed) {
      if (typeof value !== 'object' || value === null) return [];
      const item = value as Record<string, unknown>;
      if (
        !Number.isInteger(item.variant_id) ||
        !Number.isInteger(item.product_id) ||
        typeof item.quantity !== 'number' ||
        !Number.isInteger(item.quantity) ||
        item.quantity < 1 ||
        item.quantity > 100 ||
        typeof item.unit_cents !== 'number' ||
        !Number.isInteger(item.unit_cents) ||
        item.unit_cents < 1 ||
        typeof item.title !== 'string' ||
        item.title.length > 160 ||
        typeof item.variant !== 'string' ||
        typeof item.stock !== 'number' ||
        !Number.isInteger(item.stock) ||
        item.stock < 0 ||
        typeof item.variant_id !== 'number' ||
        item.variant_id < 1 ||
        typeof item.product_id !== 'number' ||
        item.product_id < 1 ||
        result.some((existing) => existing.variant_id === item.variant_id)
      )
        return [];
      result.push({
        variant_id: item.variant_id,
        product_id: item.product_id,
        title: item.title,
        quantity: item.quantity,
        unit_cents: item.unit_cents,
        variant: item.variant,
        stock: item.stock,
        image:
          typeof item.image === 'string' && /^[0-9a-f]{32}\.jpg$/.test(item.image)
            ? item.image
            : null,
      });
    }
    return result;
  } catch {
    return [];
  }
}
