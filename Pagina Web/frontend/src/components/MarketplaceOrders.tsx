import { useState } from 'react';
import { useResource } from '../useResource';
import { money } from '../types';

interface Order {
  id: string;
  titulo: string;
  vendedor: string;
  variante: string;
  cantidad: number;
  total_centimos: number;
  created_at: string;
}
interface OrderPage {
  items: Order[];
  total: number;
  page: number;
  pages: number;
}

function OrdersPage({
  kind,
  page,
  onPage,
}: {
  kind: 'orders' | 'sales';
  page: number;
  onPage: (page: number) => void;
}) {
  const { data, loading, error, refresh } = useResource<OrderPage>(
    `/marketplace/${kind}?page=${page}`,
  );
  if (loading) return <p role="status">Cargando pedidos…</p>;
  if (error)
    return (
      <p className="error-message" role="alert">
        {error}{' '}
        <button className="btn btn-secondary" onClick={refresh}>
          Reintentar
        </button>
      </p>
    );
  return (
    <>
      {!data?.items.length && (
        <p className="empty-state">
          {kind === 'orders'
            ? 'Todavía no has comprado productos.'
            : 'Todavía no tienes ventas registradas.'}
        </p>
      )}
      <div className="marketplace-orders">
        {data?.items.map((order) => (
          <article key={order.id} className="form-card">
            <p className="eyebrow">Pedido confirmado · Demostración</p>
            <h3>{order.titulo}</h3>
            <p>
              {order.vendedor} · {order.variante}
            </p>
            <p>
              {order.cantidad} {order.cantidad === 1 ? 'unidad' : 'unidades'} ·{' '}
              <strong>{money(order.total_centimos / 100)}</strong>
            </p>
            <p className="muted">
              {new Intl.DateTimeFormat('es-PE', {
                dateStyle: 'medium',
                timeStyle: 'short',
                timeZone: 'America/Lima',
              }).format(
                new Date(
                  /(Z|[+-]\d{2}:\d{2})$/.test(order.created_at)
                    ? order.created_at
                    : order.created_at + 'Z',
                ),
              )}
            </p>
            <small>Pedido {order.id}</small>
          </article>
        ))}
      </div>
      {data && data.pages > 1 && (
        <nav className="catalog-pagination" aria-label="Páginas de pedidos">
          <button
            className="btn btn-secondary"
            disabled={page <= 1}
            onClick={() => onPage(page - 1)}
          >
            Anterior
          </button>
          <span>
            Página {page} de {data.pages}
          </span>
          <button
            className="btn btn-secondary"
            disabled={page >= data.pages}
            onClick={() => onPage(page + 1)}
          >
            Siguiente
          </button>
        </nav>
      )}
    </>
  );
}

export default function MarketplaceOrders({ kind = 'orders' }: { kind?: 'orders' | 'sales' }) {
  const [page, setPage] = useState(1);
  return (
    <section className="marketplace-history">
      <h2>{kind === 'orders' ? 'Mis compras' : 'Mis ventas'}</h2>
      <p className="muted">Pedidos del proyecto académico. No implican cobros ni envíos reales.</p>
      <OrdersPage key={`${kind}-${page}`} kind={kind} page={page} onPage={setPage} />
    </section>
  );
}
