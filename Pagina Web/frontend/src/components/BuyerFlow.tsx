import { useEffect, useMemo, useRef, useState } from 'react';
import Fuse from 'fuse.js';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { eventDate, money } from '../types';
import type { Ticket } from '../types';
import { paymentTransaction, safeCheckoutUrl } from '../payments';
import type { PaymentCapabilities } from '../payments';
import {
  operationAllowed,
  percent,
  previewAmount,
  reservationReleased,
  verifyQuote,
} from '../promotions';
import type { OperationSettings, Referrals, ReservationQuote } from '../promotions';

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
  referrals = null,
  onPaymentUpdated,
  settings,
}: {
  onRequireLogin?: () => void;
  searchQuery?: string;
  referrals?: Referrals | null;
  onPaymentUpdated?: () => void;
  settings?: OperationSettings;
}) {
  const { data, loading, error: loadError, refresh } = useResource<Ticket[]>('/tickets');
  const tickets = useMemo(() => data ?? [], [data]);
  const [error, setError] = useState('');
  const [notice, setNotice] = useState('');
  const [pending, setPending] = useState<Ticket | null>(null);
  const [busy, setBusy] = useState(false);
  const [uncertain, setUncertain] = useState(false);
  const [quote, setQuote] = useState<ReservationQuote | null>(null);
  const [quoteChanged, setQuoteChanged] = useState(false);
  const reservation = useRef<{ ticketId: string; quote: ReservationQuote } | null>(null);
  const selected = useRef<Ticket | null>(null);
  const checkout = useRef<Checkout | null>(null);
  const reservationExpiresAt = useRef(0);
  const charging = useRef(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const displayedCents = pending
    ? (quote?.amount_total_cents ?? previewAmount(pending.price, referrals))
    : 0;
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
      await api.post('/payments/charge', {
        ticket_id: ticket.id,
        culqi_token: token,
        reservation_id: reservation.current?.quote.reservation_id,
      });
      setNotice('Pago confirmado. Puedes consultar tu compra en Mis compras.');
      onPaymentUpdated?.();
      selected.current = null;
      checkout.current = null;
      setPending(null);
      refresh();
    } catch (failure) {
      const status = (failure as { response?: { status?: number } }).response?.status;
      if (reservationReleased(failure)) {
        clearReleasedReservation();
        setError(errorMessage(failure));
        return;
      }
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

  function clearReleasedReservation() {
    checkout.current?.close();
    checkout.current = null;
    selected.current = null;
    reservation.current = null;
    reservationExpiresAt.current = 0;
    setQuote(null);
    setQuoteChanged(false);
    setPending(null);
    setUncertain(false);
    dialog.current?.close();
    setNotice(
      'La reserva anterior se cerró. Revisa tu beneficio y vuelve a seleccionar la entrada para cotizarla.',
    );
    refresh();
    onPaymentUpdated?.();
  }

  async function pay() {
    if (!pending || busy || charging.current || uncertain) return;
    if (!operationAllowed(settings, 'purchases')) {
      setError(
        'Las nuevas compras están pausadas. Tus compras anteriores siguen disponibles en Mis compras.',
      );
      return;
    }
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
    let creatingGoCheckout = false;
    try {
      const status = await api.get<PaymentCapabilities>('/payments/status');
      const go = status.data.provider === 'dlocal_go';
      if (!status.data.enabled || (go && !status.data.payouts_enabled) || (!go && !key))
        throw new Error('Los pagos no están disponibles en este momento. Inténtalo más tarde.');
      const CheckoutClass = go ? null : await loadCheckout();
      let reserved =
        reservation.current?.ticketId === pending.id ? reservation.current.quote : null;
      if (!reserved) {
        const response = await api.post<ReservationQuote>(`/tickets/${pending.id}/buy`);
        reserved = verifyQuote(response.data, pending.price);
        reservation.current = { ticketId: pending.id, quote: reserved };
      }
      const expiresAt = Date.parse(reserved.reserved_until);
      if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) {
        reservation.current = null;
        setQuote(null);
        refresh();
        throw new Error('La reserva venció. Elige una entrada disponible para continuar.');
      }
      setQuote(reserved);
      if (reserved.amount_total_cents !== displayedCents) {
        setQuoteChanged(true);
        setBusy(false);
        return;
      }
      if (go) {
        creatingGoCheckout = true;
        const response = await api.post<{
          transaction_id: string;
          redirect_url: string;
          status: string;
          amount_total: number;
        }>('/payments/checkout', {
          ticket_id: pending.id,
          reservation_id: reserved.reservation_id,
        });
        if (
          ['SUCCEEDED', 'FAILED', 'REFUNDED', 'REFUND_PENDING', 'UNKNOWN'].includes(
            response.data.status,
          ) ||
          (response.data.status === 'PROCESSING' && !response.data.redirect_url)
        ) {
          const id = paymentTransaction(
            `?payment_transaction=${encodeURIComponent(response.data.transaction_id)}`,
          );
          if (!id) throw new Error('No pudimos identificar la operación para consultar su estado.');
          const destination = new URL('/', window.location.origin);
          destination.searchParams.set('payment_transaction', id);
          destination.hash = 'wallet';
          window.location.assign(destination.href);
          return;
        }
        const redirect = safeCheckoutUrl(response.data.redirect_url);
        if (
          !redirect ||
          Math.round(Number(response.data.amount_total) * 100) !== reserved.amount_total_cents
        )
          throw new Error(
            'No pudimos verificar el enlace o el importe del checkout. Consulta el estado de la compra antes de continuar.',
          );
        window.location.assign(redirect);
        return;
      }
      const ticket = pending;
      if (!CheckoutClass || !key) throw new Error('El formulario de pago no está disponible.');
      const instance = new CheckoutClass(key, {
        settings: { title: 'Tickia', currency: 'PEN', amount: reserved.amount_total_cents },
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
      if (reservationReleased(failure)) {
        clearReleasedReservation();
        return;
      }
      const status = (failure as { response?: { status?: number } }).response?.status;
      if (creatingGoCheckout && (!status || status >= 500 || status === 409)) {
        setUncertain(true);
        setError(
          'No pudimos confirmar la apertura del pago. No vuelvas a pagar esta compra; consulta Mis compras o solicita atención.',
        );
      }
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
    const saved = reservation.current?.ticketId === ticket.id ? reservation.current.quote : null;
    setQuote(saved);
    setQuoteChanged(false);
    setPending(ticket);
    dialog.current?.showModal();
  }
  if (loading) return <p role="status">Cargando entradas…</p>;
  return (
    <div>
      {!operationAllowed(settings, 'purchases') && (
        <p className="notice" role="status">
          Las nuevas compras están pausadas. Puedes consultar tus compras anteriores y presentar
          reclamos en Mis compras.
        </p>
      )}
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
                      disabled={busy || uncertain || !operationAllowed(settings, 'purchases')}
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
            {referrals?.reward_status === 'AVAILABLE' && referrals.choice === null && (
              <p className="notice">
                Tienes un beneficio sin elegir. Cierra esta ventana y elige compra o venta en el
                panel «Invita y recibe un descuento» para usarlo.
              </p>
            )}
            <h3>{pending.event_name}</h3>
            <p>
              {pending.zone} · {eventDate(pending.event_date)}
            </p>
            <p>
              Precio publicado: <strong>{money(pending.price)}</strong>
            </p>
            {displayedCents < Math.round(pending.price * 100) && (
              <p>
                Descuento por referido (financiado por Tickia): −
                {money(pending.price - displayedCents / 100)}
              </p>
            )}
            <p>
              Total a pagar: <strong>{money(displayedCents / 100)}</strong>
            </p>
            {quoteChanged && (
              <p role="status">
                El importe cambió respecto al mostrado. Revisa el nuevo total y confírmalo antes de
                pagar.
              </p>
            )}
            <p>
              Comisión al vendedor:{' '}
              {percent(quote?.commission_rate ?? pending.commission_rate ?? 0.1)} % con IGV
              incluido. El comprador no paga sobrecostos.
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
                disabled={busy || uncertain || !operationAllowed(settings, 'purchases')}
                onClick={() => void pay()}
              >
                {busy
                  ? 'Procesando…'
                  : quoteChanged
                    ? `Confirmar y pagar ${money(displayedCents / 100)}`
                    : 'Continuar al pago'}
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
