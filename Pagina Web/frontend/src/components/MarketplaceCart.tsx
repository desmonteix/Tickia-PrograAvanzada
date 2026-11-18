import { useEffect, useRef, useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';
import type { CartLine } from '../cart';
import type { User } from '../types';

interface Bill {
  subtotal_centimos: number;
  total_centimos: number;
  envio_centimos: number;
  descuentos: { nombre: string; centimos: number }[];
}

function Checkout({
  body,
  user,
  onLogin,
  onComplete,
  onBusy,
}: {
  body: string;
  user: User | null;
  onLogin: () => void;
  onComplete: (id: string) => void;
  onBusy: (busy: boolean) => void;
}) {
  const [quote, setQuote] = useState<Bill | null>(null);
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [revision, setRevision] = useState(0);
  const request = useRef<string | null>(null);
  const sending = useRef(false);
  useEffect(() => {
    const controller = new AbortController();
    api
      .post<Bill>('/marketplace/quote', JSON.parse(body), { signal: controller.signal })
      .then((response) => {
        if (!controller.signal.aborted) {
          setQuote(response.data);
          setError('');
        }
      })
      .catch((failure) => {
        if (!controller.signal.aborted) setError(errorMessage(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setLoading(false);
      });
    return () => controller.abort();
  }, [body, revision]);
  async function confirm() {
    if (!user) {
      onLogin();
      return;
    }
    if (!quote || sending.current) return;
    sending.current = true;
    setBusy(true);
    onBusy(true);
    setError('');
    let unresolved = false;
    request.current ??= crypto.randomUUID();
    try {
      const response = await api.post<{ id: string }>('/marketplace/orders', {
        ...JSON.parse(body),
        request_id: request.current,
        expected_total_centimos: quote.total_centimos,
      });
      onComplete(response.data.id);
    } catch (failure) {
      const status = (failure as { response?: { status?: number } }).response?.status;
      unresolved = !status || status >= 500;
      setUncertain(unresolved);
      setError(
        unresolved
          ? 'No pudimos verificar la respuesta. Reintenta la misma confirmación o revisa Mis compras antes de crear otro pedido.'
          : errorMessage(failure),
      );
      if (!unresolved) request.current = null;
    } finally {
      sending.current = false;
      setBusy(false);
      onBusy(unresolved);
    }
  }
  return (
    <section className="form-card cart-summary" aria-labelledby="cart-total-title">
      <h2 id="cart-total-title">Resumen de tu pedido</h2>
      {loading && <p role="status">Calculando precios, descuentos y envío…</p>}
      {quote && (
        <dl>
          <div>
            <dt>Artículos</dt>
            <dd>{money(quote.subtotal_centimos / 100)}</dd>
          </div>
          {quote.descuentos.map((discount) => (
            <div key={discount.nombre}>
              <dt>{discount.nombre}</dt>
              <dd>−{money(discount.centimos / 100)}</dd>
            </div>
          ))}
          <div>
            <dt>Envío</dt>
            <dd>{money(quote.envio_centimos / 100)}</dd>
          </div>
          <div className="cart-total">
            <dt>Total</dt>
            <dd>{money(quote.total_centimos / 100)}</dd>
          </div>
        </dl>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {!quote && !loading && (
        <button
          className="btn btn-secondary"
          onClick={() => {
            setLoading(true);
            setRevision((value) => value + 1);
          }}
        >
          Reintentar cotización
        </button>
      )}
      <p className="notice">
        Pago de demostración. Se registra el pedido y se descuenta el stock; no se cobra dinero
        real.
      </p>
      <button
        className="btn btn-primary"
        disabled={busy || loading || !quote}
        onClick={() => void confirm()}
      >
        {busy
          ? 'Confirmando…'
          : !user
            ? 'Ingresar para confirmar'
            : uncertain
              ? 'Reintentar confirmación'
              : 'Confirmar pedido y pago de demostración'}
      </button>
      {uncertain && <a href="#wallet">Revisar Mis compras</a>}
    </section>
  );
}

export default function MarketplaceCart({
  items,
  user,
  onQuantity,
  onRemove,
  onLogin,
  onComplete,
}: {
  items: CartLine[];
  user: User | null;
  onQuantity: (id: number, quantity: number) => void;
  onRemove: (id: number) => void;
  onLogin: () => void;
  onComplete: (id: string) => void;
}) {
  const couriers =
    useResource<{ id_courier: number; nombre: string; estrategia: string }[]>(
      '/marketplace/couriers',
    );
  const districts =
    useResource<{ id_distrito: number; nombre: string; provincia: string; departamento: string }[]>(
      '/marketplace/districts',
    );
  const coupons =
    useResource<{ id_cupon: number; codigo: string; descuento_pct: number }[]>(
      '/marketplace/coupons',
    );
  const [courier, setCourier] = useState(1);
  const [district, setDistrict] = useState(1);
  const [couponDraft, setCouponDraft] = useState('');
  const [coupon, setCoupon] = useState('');
  const [payment, setPayment] = useState('yape_demo');
  const [locked, setLocked] = useState(false);
  const valid = items.every(
    (item) => Number.isInteger(item.quantity) && item.quantity >= 1 && item.quantity <= 100,
  );
  const body = JSON.stringify({
    items: items.map((item) => ({ variant_id: item.variant_id, quantity: item.quantity })),
    coupon_code: coupon || null,
    courier_id: courier,
    district_id: district,
    payment_method: payment,
  });
  return (
    <section>
      <p className="eyebrow">Un pedido, varios artículos</p>
      <h1>Tu carrito</h1>
      {!items.length ? (
        <div className="empty-state">
          <p>Tu carrito está vacío.</p>
          <a href="#catalog" className="btn btn-primary">
            Explorar productos
          </a>
        </div>
      ) : (
        <div className="cart-layout">
          <div>
            <div className="cart-lines">
              {items.map((item) => (
                <article className="form-card" key={item.variant_id}>
                  <h3>{item.title}</h3>
                  <p>
                    {item.variant} · {money(item.unit_cents / 100)} por unidad
                  </p>
                  <label htmlFor={`cart-quantity-${item.variant_id}`}>
                    Cantidad de {item.title}
                  </label>
                  <input
                    id={`cart-quantity-${item.variant_id}`}
                    className="input-field"
                    type="number"
                    min="1"
                    max="100"
                    value={item.quantity}
                    disabled={locked}
                    onChange={(event) => onQuantity(item.variant_id, Number(event.target.value))}
                  />
                  <button
                    className="btn btn-ghost"
                    disabled={locked}
                    onClick={() => onRemove(item.variant_id)}
                  >
                    Quitar {item.title}
                  </button>
                </article>
              ))}
            </div>
            <section className="form-card">
              <h2>Entrega y pago</h2>
              {(couriers.error || districts.error) && (
                <p role="alert" className="error-message">
                  {couriers.error || districts.error}
                </p>
              )}
              <fieldset className="marketplace-fieldset" disabled={locked}>
                <div className="input-group">
                  <label htmlFor="cart-courier">Courier</label>
                  <select
                    id="cart-courier"
                    className="input-field"
                    value={courier}
                    onChange={(event) => setCourier(Number(event.target.value))}
                  >
                    {couriers.data?.map((value) => (
                      <option key={value.id_courier} value={value.id_courier}>
                        {value.nombre} · {value.estrategia}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="input-group">
                  <label htmlFor="cart-district">Distrito de entrega</label>
                  <select
                    id="cart-district"
                    className="input-field"
                    value={district}
                    onChange={(event) => setDistrict(Number(event.target.value))}
                  >
                    {districts.data?.map((value) => (
                      <option key={value.id_distrito} value={value.id_distrito}>
                        {value.nombre}, {value.provincia}, {value.departamento}
                      </option>
                    ))}
                  </select>
                </div>
                <div className="input-group">
                  <label htmlFor="cart-coupon">Código de cupón (opcional)</label>
                  <div className="coupon-field">
                    <input
                      id="cart-coupon"
                      className="input-field"
                      list="cart-coupons"
                      value={couponDraft}
                      maxLength={80}
                      onChange={(event) => setCouponDraft(event.target.value)}
                    />
                    <button
                      className="btn btn-secondary"
                      type="button"
                      onClick={() => setCoupon(couponDraft.trim())}
                    >
                      Aplicar cupón
                    </button>
                  </div>
                  <datalist id="cart-coupons">
                    {coupons.data?.map((value) => (
                      <option key={value.id_cupon} value={value.codigo}>
                        {value.descuento_pct}%
                      </option>
                    ))}
                  </datalist>
                  <small>
                    Con 3 unidades o más se aplica 3% por volumen, acumulable con el cupón.
                  </small>
                </div>
                <div className="input-group">
                  <label htmlFor="cart-payment">Método de pago de demostración</label>
                  <select
                    id="cart-payment"
                    className="input-field"
                    value={payment}
                    onChange={(event) => setPayment(event.target.value)}
                  >
                    <option value="yape_demo">Yape simulado</option>
                    <option value="tarjeta_demo">Tarjeta simulada</option>
                    <option value="transferencia_demo">Transferencia simulada</option>
                  </select>
                </div>
              </fieldset>
            </section>
          </div>
          {valid ? (
            <Checkout
              key={body}
              body={body}
              user={user}
              onLogin={onLogin}
              onComplete={onComplete}
              onBusy={setLocked}
            />
          ) : (
            <p role="alert">Usa cantidades enteras entre 1 y 100.</p>
          )}
        </div>
      )}
    </section>
  );
}
