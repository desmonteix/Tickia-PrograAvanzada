import { useEffect, useState } from 'react';
import api, { errorMessage } from '../api';
import { paymentTransaction, verifyTransaction, watchPayment } from '../payments';
import type { PaymentTransaction } from '../payments';

const messages = {
  PROCESSING: 'El pago sigue en proceso. No vuelvas a pagar esta compra.',
  UNKNOWN:
    'Estamos verificando el pago. No vuelvas a pagarlo; puedes consultar nuevamente su estado.',
  SUCCEEDED: 'Pago confirmado por el proveedor. Consulta tu entrada en Mis compras.',
  FAILED: 'El proveedor informa que el pago no se completó.',
  REFUNDED: 'Reembolso confirmado por el proveedor.',
  REFUND_PENDING: 'La devolución está pendiente de confirmación.',
};

export default function PaymentReturn({ onUpdate }: { onUpdate: () => void }) {
  const [id, setId] = useState(() => paymentTransaction(window.location.search));
  const [transaction, setTransaction] = useState<PaymentTransaction | null>(null);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(!!id);
  const [revision, setRevision] = useState(0);
  useEffect(() => {
    if (!id) return;
    const controller = new AbortController();
    void watchPayment(
      async () => {
        const response = await api.get<PaymentTransaction>(`/payments/transactions/${id}`, {
          signal: controller.signal,
        });
        return verifyTransaction(response.data, id);
      },
      (value) => {
        setTransaction(value);
        if (value.status === 'SUCCEEDED' || value.status === 'FAILED') onUpdate();
      },
      controller.signal,
    )
      .catch((failure) => {
        if (!controller.signal.aborted) setError(errorMessage(failure));
      })
      .finally(() => {
        if (!controller.signal.aborted) setBusy(false);
      });
    return () => controller.abort();
  }, [id, revision, onUpdate]);
  if (!id) return null;
  return (
    <article className="form-card" aria-labelledby="payment-return-title" aria-busy={busy}>
      <h2 id="payment-return-title">Estado de tu pago</h2>
      <p role="status">
        {transaction
          ? messages[transaction.status]
          : 'Consultando el estado del pago. Volver del checkout no confirma el cobro.'}
      </p>
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      <div className="actions">
        <button
          className="btn btn-secondary"
          disabled={busy}
          onClick={() => {
            setBusy(true);
            setError('');
            setRevision((value) => value + 1);
          }}
        >
          {busy ? 'Consultando…' : 'Consultar estado'}
        </button>
        {transaction && !['PROCESSING', 'UNKNOWN'].includes(transaction.status) && (
          <button
            className="btn btn-ghost"
            onClick={() => {
              const url = new URL(window.location.href);
              url.searchParams.delete('payment_transaction');
              window.history.replaceState({}, '', url);
              setId(null);
            }}
          >
            Cerrar seguimiento
          </button>
        )}
      </div>
    </article>
  );
}
