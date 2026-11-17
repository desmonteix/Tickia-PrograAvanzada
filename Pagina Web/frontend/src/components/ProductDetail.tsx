import { useEffect, useRef, useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';
import type { User } from '../types';
import type { Product } from './ProductCatalog';

interface Detail extends Product {
  variantes: { id_variante: number; talla: string | null; color: string | null; stock: number }[];
  resenas: {
    id_resena: number;
    estrellas: number;
    comentario: string | null;
    fecha: string;
    autor: string;
  }[];
  preguntas: { id_pregunta: number; texto: string; respuesta: string | null; autor: string }[];
}

export default function ProductDetail({
  id,
  onClose,
  user,
  onRequireLogin,
  onPurchased,
}: {
  id: number;
  onClose: () => void;
  user: User | null;
  onRequireLogin: () => void;
  onPurchased: () => void;
}) {
  const dialog = useRef<HTMLDialogElement>(null);
  const { data, loading, error, refresh } = useResource<Detail>(`/marketplace/products/${id}`);
  const [selectedVariant, setSelectedVariant] = useState<number | null>(null);
  const [quantity, setQuantity] = useState(1);
  const [busy, setBusy] = useState(false);
  const [purchaseError, setPurchaseError] = useState('');
  const [confirmed, setConfirmed] = useState<string | null>(null);
  const [uncertain, setUncertain] = useState(false);
  const attempt = useRef<{ variant_id: number; quantity: number; request_id: string } | null>(null);
  const sending = useRef(false);
  const variant =
    data?.variantes.find((value) => value.id_variante === selectedVariant) ??
    data?.variantes.find((value) => value.stock > 0) ??
    data?.variantes[0];
  async function buy() {
    if (sending.current || confirmed || !variant || !data) return;
    if (!user) {
      onRequireLogin();
      return;
    }
    sending.current = true;
    setBusy(true);
    setPurchaseError('');
    if (!attempt.current)
      attempt.current = {
        variant_id: variant.id_variante,
        quantity,
        request_id: crypto.randomUUID(),
      };
    try {
      const response = await api.post<{ id: string }>('/marketplace/orders', attempt.current);
      setConfirmed(response.data.id);
      setUncertain(false);
      onPurchased();
      refresh();
    } catch (failure) {
      const status = (failure as { response?: { status?: number } }).response?.status;
      if (!status || status >= 500) {
        setUncertain(true);
        setPurchaseError(
          'No pudimos confirmar la respuesta. Reintenta para consultar la misma compra o revisa Mis compras.',
        );
      } else {
        attempt.current = null;
        setUncertain(false);
        setPurchaseError(errorMessage(failure));
        if (status === 409) refresh();
      }
    } finally {
      sending.current = false;
      setBusy(false);
    }
  }
  useEffect(() => {
    dialog.current?.showModal();
  }, []);
  return (
    <dialog
      ref={dialog}
      className="checkout-dialog product-dialog"
      aria-labelledby="product-title"
      onClose={onClose}
      onCancel={(event) => {
        if (busy) event.preventDefault();
      }}
    >
      <div className="product-dialog-heading">
        <p className="eyebrow">Detalle del producto</p>
        <button
          className="btn btn-secondary"
          onClick={() => dialog.current?.close()}
          aria-label="Cerrar detalle"
          disabled={busy}
        >
          Cerrar ×
        </button>
      </div>
      <h2 id="product-title">{data?.titulo ?? 'Consultando producto'}</h2>
      {loading && <p role="status">Cargando detalle…</p>}
      {error && (
        <p className="error-message" role="alert">
          {error}{' '}
          <button className="btn btn-secondary" onClick={refresh}>
            Reintentar
          </button>
        </p>
      )}
      {data && (
        <>
          <p>
            {data.categoria}
            {data.distrito && ` · ${data.distrito}, ${data.provincia}`}
          </p>
          <p className="price-tag">{money(data.precio)}</p>
          <p>
            {data.vendedor} · Reputación: {data.reputacion.toFixed(2)} / 5
          </p>
          <p className="notice">
            Compra de demostración: se registra tu pedido y se descuenta stock. No se realizan
            cobros reales.
          </p>
          {data.imagen && (
            <img
              className="product-detail-photo"
              src={`/api/marketplace/images/${data.imagen}`}
              alt={data.titulo}
            />
          )}
          {data.descripcion && <p>{data.descripcion}</p>}
          {confirmed ? (
            <div className="notice" role="status">
              <strong>Compra confirmada</strong>
              <p>Pedido {confirmed}. Puedes consultarlo en Mis compras.</p>
              <a className="btn btn-primary" href="#wallet" onClick={() => dialog.current?.close()}>
                Ver mis compras
              </a>
            </div>
          ) : data.owner_id === user?.id ? (
            <p className="notice">Este producto es tuyo. Puedes consultar sus ventas en Vender.</p>
          ) : (
            <div className="product-checkout">
              <h3>Comprar este producto</h3>
              <label htmlFor="purchase-variant">Variante</label>
              <select
                id="purchase-variant"
                className="input-field"
                value={variant?.id_variante ?? ''}
                disabled={busy || uncertain || !variant}
                onChange={(event) => {
                  setSelectedVariant(Number(event.target.value));
                  setQuantity(1);
                  attempt.current = null;
                }}
              >
                {data.variantes.map((value) => (
                  <option
                    key={value.id_variante}
                    value={value.id_variante}
                    disabled={value.stock === 0}
                  >
                    {[value.talla, value.color].filter(Boolean).join(' · ')} — {value.stock}{' '}
                    disponibles
                  </option>
                ))}
              </select>
              <label htmlFor="purchase-quantity">Cantidad</label>
              <input
                id="purchase-quantity"
                className="input-field"
                type="number"
                min="1"
                max={Math.min(100, variant?.stock ?? 0)}
                value={quantity}
                disabled={busy || uncertain || !variant?.stock}
                onChange={(event) => {
                  setQuantity(Number(event.target.value));
                  attempt.current = null;
                }}
              />
              <p>
                Total: <strong>{money((Math.round(data.precio * 100) * quantity) / 100)}</strong>
              </p>
              {purchaseError && (
                <p className="error-message" role="alert">
                  {purchaseError}
                </p>
              )}
              <button
                className="btn btn-primary"
                disabled={
                  busy ||
                  (!uncertain &&
                    (!variant?.stock ||
                      !Number.isInteger(quantity) ||
                      quantity < 1 ||
                      quantity > Math.min(100, variant.stock)))
                }
                onClick={() => void buy()}
              >
                {busy
                  ? 'Confirmando…'
                  : !user
                    ? 'Ingresar para comprar'
                    : uncertain
                      ? 'Reintentar confirmación'
                      : variant?.stock
                        ? 'Confirmar compra'
                        : 'Sin stock'}
              </button>
            </div>
          )}
          <h3>Variantes y disponibilidad</h3>
          <div className="product-table-scroll">
            <table>
              <thead>
                <tr>
                  <th scope="col">Talla</th>
                  <th scope="col">Color</th>
                  <th scope="col">Stock</th>
                </tr>
              </thead>
              <tbody>
                {data.variantes.map((variant) => (
                  <tr key={variant.id_variante}>
                    <td>{variant.talla ?? 'No especificada'}</td>
                    <td>{variant.color ?? 'No especificado'}</td>
                    <td>{variant.stock}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {data.variantes.length === 0 && <p>No hay variantes registradas.</p>}
          <h3>
            Reseñas{' '}
            {data.estrellas !== null &&
              `· ${data.estrellas.toFixed(2)} / 5 (${data.total_resenas})`}
          </h3>
          {data.resenas.length === 0 && <p>Aún no hay reseñas para este producto.</p>}
          {data.total_resenas > 10 && <p className="muted">Las 10 reseñas más recientes.</p>}
          <ul className="product-comments">
            {data.resenas.map((review) => (
              <li key={review.id_resena}>
                <strong>
                  {review.autor} · {review.estrellas} / 5
                </strong>
                <p>{review.comentario ?? 'Sin comentario.'}</p>
                <small>{review.fecha}</small>
              </li>
            ))}
          </ul>
          <h3>Preguntas recientes</h3>
          {data.preguntas.length === 0 && <p>No hay preguntas registradas.</p>}
          <ul className="product-comments">
            {data.preguntas.map((question) => (
              <li key={question.id_pregunta}>
                <strong>{question.autor}</strong>
                <p>{question.texto}</p>
                <p className="muted">{question.respuesta ?? 'Sin respuesta todavía.'}</p>
              </li>
            ))}
          </ul>
        </>
      )}
    </dialog>
  );
}
