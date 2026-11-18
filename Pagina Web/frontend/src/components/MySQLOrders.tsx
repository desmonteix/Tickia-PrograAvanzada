import { useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';

interface Order {
  id: string;
  estado: string;
  total_centimos: number;
  subtotal_centimos: number;
  descuento_centimos: number;
  envio_centimos: number;
  created_at: string;
  items: {
    id_producto: number;
    titulo: string;
    variante: string;
    cantidad: number;
    precio_unit_centimos: number;
  }[];
  pagos: { metodo: string; estado: string }[];
  envios: {
    courier: string;
    fecha_estimada: string | null;
    fecha_envio: string | null;
    fecha_entrega: string | null;
  }[];
  destino: { distrito: string; provincia: string; departamento: string } | null;
}
const STEPS = ['pendiente', 'pagado', 'enviado', 'entregado'];
const LABELS: Record<string, string> = {
  pendiente: 'Pendiente',
  pagado: 'Pagado',
  enviado: 'Enviado',
  entregado: 'Entregado',
  cancelado: 'Cancelado',
};
const dateTime = (value: string) =>
  new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'America/Lima',
  }).format(new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : value + 'Z'));

function OrderCard({
  order,
  kind,
  onRefresh,
  onProduct,
}: {
  order: Order;
  kind: 'orders' | 'sales';
  onRefresh: () => void;
  onProduct: (id: number) => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function advance(nextState: string) {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/marketplace/orders/${order.id}/status`, { next_state: nextState });
      onRefresh();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  const shipment = order.envios[0];
  return (
    <article className="form-card order-card">
      <p className="eyebrow">
        Pedido {order.id} · {LABELS[order.estado] ?? order.estado}
      </p>
      <ol className="order-states" aria-label="Estado del pedido">
        {STEPS.map((step, index) => (
          <li
            key={step}
            data-active={index <= STEPS.indexOf(order.estado)}
            aria-current={step === order.estado ? 'step' : undefined}
          >
            {LABELS[step]}
          </li>
        ))}
      </ol>
      <ul className="order-lines">
        {order.items.map((item) => (
          <li key={`${item.id_producto}-${item.variante}`}>
            <h3>{item.titulo}</h3>
            <p>
              {item.variante} · {item.cantidad} {item.cantidad === 1 ? 'unidad' : 'unidades'} ·{' '}
              {money((item.precio_unit_centimos * item.cantidad) / 100)}
            </p>
            <button className="btn btn-ghost" onClick={() => onProduct(item.id_producto)}>
              {order.estado === 'entregado' && kind === 'orders'
                ? 'Ver producto y reseñar'
                : 'Ver producto'}
            </button>
          </li>
        ))}
      </ul>
      <dl className="order-totals">
        <div>
          <dt>Artículos</dt>
          <dd>{money(order.subtotal_centimos / 100)}</dd>
        </div>
        {order.descuento_centimos > 0 && (
          <div>
            <dt>Descuentos</dt>
            <dd>−{money(order.descuento_centimos / 100)}</dd>
          </div>
        )}
        <div>
          <dt>Envío</dt>
          <dd>{money(order.envio_centimos / 100)}</dd>
        </div>
        <div>
          <dt>Total</dt>
          <dd>
            <strong>{money(order.total_centimos / 100)}</strong>
          </dd>
        </div>
      </dl>
      {order.pagos[0] && <p>Pago de demostración: {order.pagos[0].estado}.</p>}
      {shipment && (
        <div className="shipment-info">
          <h4>Seguimiento del envío</h4>
          <p>{shipment.courier}</p>
          {order.destino && (
            <p>
              {order.destino.distrito}, {order.destino.provincia}, {order.destino.departamento}
            </p>
          )}
          {shipment.fecha_estimada && (
            <p>
              Entrega estimada:{' '}
              {new Intl.DateTimeFormat('es-PE', {
                dateStyle: 'medium',
                timeZone: 'America/Lima',
              }).format(new Date(shipment.fecha_estimada + 'T12:00:00-05:00'))}
            </p>
          )}
          {shipment.fecha_envio && <p>Despachado: {dateTime(shipment.fecha_envio)}</p>}
          {shipment.fecha_entrega && <p>Recibido: {dateTime(shipment.fecha_entrega)}</p>}
        </div>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <div className="order-actions">
        {order.estado === 'pagado' && (
          <button
            className="btn btn-secondary"
            disabled={busy}
            onClick={() => void advance('enviado')}
          >
            {busy ? 'Actualizando…' : 'Simular despacho'}
          </button>
        )}
        {kind === 'orders' && order.estado === 'enviado' && (
          <button
            className="btn btn-primary"
            disabled={busy}
            onClick={() => void advance('entregado')}
          >
            {busy ? 'Actualizando…' : 'Confirmar recepción'}
          </button>
        )}
      </div>
      <small>Creado {dateTime(order.created_at)}. Los pagos y envíos son simulados.</small>
    </article>
  );
}

function OrderPage({
  kind,
  page,
  onPage,
  onProduct,
}: {
  kind: 'orders' | 'sales';
  page: number;
  onPage: (page: number) => void;
  onProduct: (id: number) => void;
}) {
  const { data, loading, error, refresh } = useResource<{ items: Order[]; pages: number }>(
    `/marketplace/${kind}?page=${page}`,
  );
  if (loading) return <p role="status">Cargando pedidos y envíos…</p>;
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
            : 'Todavía no hay ventas registradas.'}
        </p>
      )}
      <div className="marketplace-orders">
        {data?.items.map((order) => (
          <OrderCard
            key={order.id}
            order={order}
            kind={kind}
            onRefresh={refresh}
            onProduct={onProduct}
          />
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

export default function MySQLOrders({
  kind = 'orders',
  onProduct,
}: {
  kind?: 'orders' | 'sales';
  onProduct: (id: number) => void;
}) {
  const [page, setPage] = useState(1);
  return (
    <section>
      {kind === 'orders' ? <h1>Mis compras</h1> : <h2>Mis ventas</h2>}
      <p>
        Consulta los artículos, pagos y envíos de tus pedidos. La simulación permite recorrer
        pagado, enviado y entregado.
      </p>
      <OrderPage
        key={`${kind}-${page}`}
        kind={kind}
        page={page}
        onPage={setPage}
        onProduct={onProduct}
      />
    </section>
  );
}
