import { useEffect, useMemo, useRef, useState } from 'react';
import Fuse from 'fuse.js';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { eventDate, money } from '../types';
import type { Ticket } from '../types';

interface Checkout {
  token?: { id: string };
  error?: { user_message?: string };
  culqi: () => void;
  open: () => void;
  close: () => void;
}
interface CheckoutConfig {
  settings: { title: string; currency: string; amount: number };
  options: {
    lang: string;
    modal: boolean;
    installments: boolean;
    paymentMethods: {
      tarjeta: boolean;
      yape: boolean;
      billetera: boolean;
      bancaMovil: boolean;
      agente: boolean;
      cuotealo: boolean;
    };
  };
}
declare global {
  interface Window {
    CulqiCheckout?: new (key: string, config: CheckoutConfig) => Checkout;
  }
}

async function loadCheckout() {
  if (window.CulqiCheckout) return window.CulqiCheckout;
  await new Promise<void>((resolve, reject) => {
    const script = document.createElement('script');
    const timer = window.setTimeout(() => {
      script.remove();
      reject(new Error('El formulario de pago no está disponible. Inténtalo más tarde.'));
    }, 5000);
    script.src = 'https://js.culqi.com/checkout-js';
    script.async = true;
    script.onload = () => {
      window.clearTimeout(timer);
      resolve();
    };
    script.onerror = () => {
      window.clearTimeout(timer);
      script.remove();
      reject(new Error('No pudimos cargar el formulario de pago. Inténtalo más tarde.'));
    };
    document.body.appendChild(script);
  });
  if (!window.CulqiCheckout)
    throw new Error('El formulario de pago no está disponible. Inténtalo más tarde.');
  return window.CulqiCheckout;
}

export default function BuyerFlow({
  onRequireLogin,
  searchQuery = '',
}: {
  onRequireLogin?: () => void;
  searchQuery?: string;
}) {
  const { data, loading, error: loadError, refresh } = useResource<Ticket[]>('/tickets');
  const tickets = useMemo(() => data ?? [], [data]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<Ticket | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const selected = useRef<Ticket | null>(null);
  const checkout = useRef<Checkout | null>(null);
  const reservationExpiresAt = useRef(0);
  const charging = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const filtered = useMemo(
    () =>
      !searchQuery.trim()
        ? tickets
        : new Fuse(tickets, { keys: ['event_name', 'zone'], threshold: 0.4 })
            .search(searchQuery)
            .map((result) => result.item)
            .sort((a, b) => (b.seller_rating ?? 4) - (a.seller_rating ?? 4)),
    [searchQuery, tickets],
  );

  useEffect(
    () => () => {
      checkout.current?.close();
      checkout.current = null;
      selected.current = null;
    },
    [],
  );

  async function charge(instance: Checkout, ticket: Ticket) {
    if (checkout.current !== instance || charging.current) return;
    if (Date.now() >= reservationExpiresAt.current) {
      instance.close();
      checkout.current = null;
      selected.current = null;
      setError('La reserva venció. Elige una entrada disponible para continuar.');
      refresh();
      return;
    }
    const token = instance.token?.id;
    if (!token) {
      setError(
        instance.error?.user_message ||
          'El pago no se completó. Puedes volver a abrir el formulario.',
      );
      return;
    }
    charging.current = true;
    setBusy(true);
    instance.close();
    try {
      await api.post('/payments/charge', { ticket_id: ticket.id, culqi_token: token });
      setNotice('Pago confirmado. Puedes consultar tu compra en Mis compras.');
      selected.current = null;
      checkout.current = null;
      setPending(null);
      refresh();
    } catch (failure) {
      const status = (failure as { response?: { status?: number } }).response?.status;
      if (!status || status >= 500 || status === 409) {
        checkout.current = null;
        selected.current = null;
        setUncertain(true);
        setError(
          'Estamos verificando el pago. No vuelvas a pagar; revisa Mis compras y solicita atención si aún no aparece.',
        );
      } else {
        setError(errorMessage(failure));
      }
    } finally {
      charging.current = false;
      setBusy(false);
    }
  }

  async function pay() {
    if (!pending || busy || charging.current || uncertain) return;
    if (checkout.current && Date.now() >= reservationExpiresAt.current) {
      checkout.current.close();
      checkout.current = null;
      selected.current = null;
    }
    if (checkout.current && selected.current?.id === pending.id) {
      dialog.current?.close();
      checkout.current.open();
      return;
    }
    setError('');
    setBusy(true);
    const key = import.meta.env.VITE_CULQI_PUBLIC_KEY as string | undefined;
    try {
      const status = await api.get<{ enabled: boolean }>('/payments/status');
      if (!status.data.enabled || !key)
        throw new Error('Los pagos no están disponibles en este momento. Inténtalo más tarde.');
      const CheckoutClass = await loadCheckout();
      const reservation = await api.post<{ amount_total_cents: number; reserved_until: string }>(
        `/tickets/${pending.id}/buy`,
      );
      if (
        !Number.isInteger(reservation.data.amount_total_cents) ||
        reservation.data.amount_total_cents !== Math.round(pending.price * 100)
      )
        throw new Error('El precio cambió. Actualiza el catálogo antes de comprar.');
      const expiresAt = Date.parse(reservation.data.reserved_until);
      if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        refresh();
        throw new Error('La reserva venció. Elige una entrada disponible para continuar.');
      }
      const ticket = pending;
      const instance = new CheckoutClass(key, {
        settings: { title: 'Tickia', currency: 'PEN', amount: reservation.data.amount_total_cents },
        options: {
          lang: 'es',
          modal: true,
          installments: false,
          paymentMethods: {
            tarjeta: true,
            yape: true,
            billetera: false,
            bancaMovil: false,
            agente: false,
            cuotealo: false,
          },
        },
      });
      selected.current = ticket;
      reservationExpiresAt.current = expiresAt;
      checkout.current = instance;
      instance.culqi = () => {
        void charge(instance, ticket);
      };
      dialog.current?.close();
      setBusy(false);
      instance.open();
    } catch (failure) {
      setError(errorMessage(failure));
      setBusy(false);
      const status = (failure as { response?: { status?: number } }).response?.status;
      if (status === 404 || status === 409) refresh();
      if ((failure as { response?: { status?: number } }).response?.status === 401) {
        dialog.current?.close();
        onRequireLogin?.();
      }
    }
  }

  function choose(ticket: Ticket) {
    if (selected.current && selected.current.id !== ticket.id) {
      checkout.current?.close();
      checkout.current = null;
      selected.current = null;
    }
    setError('');
    setPending(ticket);
    dialog.current?.showModal();
  }
  if (loading) return <p role="status">Cargando entradas…</p>;
  return (
    <div>
      {(loadError || error) && (
        <div className="error-message" role="alert">
          {loadError || error}
          {loadError && (
            <button className="btn btn-secondary" onClick={refresh}>
              Reintentar
            </button>
          )}
        </div>
      )}
      {notice && (
        <p className="notice" role="status">
          {notice}
        </p>
      )}
      {!loadError && (
        <div className="ticket-grid">
          {filtered.length === 0 ? (
            <div className="empty-state">
              <h3>
                {searchQuery.trim()
                  ? 'No encontramos entradas para esa búsqueda'
                  : 'Todavía no hay entradas disponibles'}
              </h3>
              <p>
                {searchQuery.trim()
                  ? 'Prueba con otro evento o zona.'
                  : 'Cuando alguien publique su entrada, aparecerá aquí.'}
              </p>
            </div>
          ) : (
            filtered.map((ticket) => (
              <article key={ticket.id} className="ticket-card">
                <div className="ticket-art" aria-hidden="true">
                  <span>ENTRADAS ENTRE PERSONAS</span>
                  <img src="/brand/tickia-symbol.png" alt="" />
                </div>
                <div className="ticket-info">
                  <p className="eyebrow">{eventDate(ticket.event_date)}</p>
                  <h3>{ticket.event_name}</h3>
                  <p>{ticket.zone}</p>
                  {typeof ticket.seller_rating === 'number' && (
                    <p className="seller-rating">
                      Rating del vendedor: {ticket.seller_rating.toFixed(2)} / 5
                    </p>
                  )}
                  <p className="ticket-type">
                    {ticket.ticket_type === 'nominada'
                      ? `Nominada · ${ticket.is_renominated ? 'renominada' : 'requiere renominación'}`
                      : 'No nominada'}
                  </p>
                  <div className="ticket-footer">
                    <strong className="price-tag">{money(ticket.price)}</strong>
                    <button
                      className="btn btn-primary"
                      disabled={busy || uncertain}
                      onClick={() => choose(ticket)}
                      aria-label={`Comprar entrada para ${ticket.event_name}`}
                    >
                      Comprar
                    </button>
                  </div>
                </div>
              </article>
            ))
          )}
        </div>
      )}
      <dialog
        ref={dialog}
        className="checkout-dialog"
        aria-label="Revisa tu compra"
        onCancel={(event) => {
          if (busy) event.preventDefault();
          else {
            selected.current = null;
          }
        }}
      >
        {pending && (
          <>
            <h2>Revisa tu compra</h2>
            <h3>{pending.event_name}</h3>
            <p>
              {pending.zone} · {eventDate(pending.event_date)}
            </p>
            <p>
              Precio total: <strong>{money(pending.price)}</strong>
            </p>
            <p>
              Tickia cobra una comisión del 10 % a quien vende. El comprador no paga sobrecostos.
            </p>
            <p className="muted">
              Tickia no es la tiquetera oficial. La lectura del QR no garantiza el ingreso al
              evento. Revisa las condiciones de transferencia de la tiquetera antes de pagar.
            </p>
            {error && (
              <p role="alert" className="error-message">
                {error}
              </p>
            )}
            <div className="actions">
              <button
                className="btn btn-primary"
                disabled={busy || uncertain}
                onClick={() => void pay()}
              >
                {busy ? 'Procesando…' : 'Continuar al pago'}
              </button>
              <button
                className="btn btn-secondary"
                disabled={busy}
                onClick={() => {
                  dialog.current?.close();
                  setBusy(false);
                }}
              >
                Volver
              </button>
            </div>
          </>
        )}
      </dialog>
    </div>
  );
}
