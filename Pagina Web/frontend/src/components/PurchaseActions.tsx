import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { eventDate } from '../types';
import type { Purchase } from '../types';

import { purchaseStatus } from '../purchaseStatus';

export default function PurchaseActions({
  purchase,
  onUpdate,
}: {
  purchase: Purchase;
  onUpdate: () => void;
}) {
  const [reporting, setReporting] = useState(false);
  const [error, setError] = useState('');
  const [busy, setBusy] = useState(false);
  async function confirm() {
    if (
      !window.confirm(
        'Confirmar autoriza el abono al vendedor y cierra el reclamo de esta compra, aunque el concierto todavía no haya ocurrido. ¿Confirmas que todo está bien?',
      )
    )
      return;
    setBusy(true);
    setError('');
    try {
      await api.post(`/purchases/${purchase.purchase_id}/confirm`);
      onUpdate();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  async function report(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    const form = new FormData(event.currentTarget);
    const file = form.get('file');
    if (
      !(file instanceof File) ||
      !file.size ||
      file.size > 5 * 1024 * 1024 ||
      !['image/png', 'image/jpeg'].includes(file.type)
    ) {
      setError('Adjunta evidencia PNG o JPG de hasta 5 MB.');
      return;
    }
    setBusy(true);
    setError('');
    try {
      await api.post(`/purchases/${purchase.purchase_id}/dispute`, form);
      onUpdate();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <div className="purchase-actions">
      <p className="notice" role="status">
        {purchaseStatus(purchase)}
      </p>
      {purchase.review_state === 'HELD' &&
        (purchase.closes_at ? (
          <p className="muted">
            El plazo de revisión finaliza el {eventDate(purchase.closes_at)} (Perú), 24 horas
            después del final del evento.
          </p>
        ) : (
          <p className="muted">
            La hora de finalización requiere revisión. El dinero no se liberará automáticamente.
          </p>
        ))}
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      {purchase.can_confirm && (
        <button
          className="btn btn-primary full-width"
          disabled={busy}
          onClick={() => void confirm()}
        >
          {busy ? 'Registrando…' : 'Todo bien con mi entrada'}
        </button>
      )}
      {purchase.can_report && (
        <button
          className="btn btn-secondary full-width"
          disabled={busy}
          onClick={() => setReporting((value) => !value)}
        >
          Reportar un problema
        </button>
      )}
      {reporting && purchase.can_report && (
        <form onSubmit={(event) => void report(event)}>
          <div className="input-group">
            <label htmlFor={`description-${purchase.purchase_id}`}>Describe el problema</label>
            <textarea
              id={`description-${purchase.purchase_id}`}
              name="description"
              className="input-field"
              minLength={10}
              maxLength={4000}
              required
            />
          </div>
          <div className="input-group">
            <label htmlFor={`evidence-${purchase.purchase_id}`}>Evidencia del problema</label>
            <input
              id={`evidence-${purchase.purchase_id}`}
              name="file"
              type="file"
              className="input-field"
              accept="image/png,image/jpeg"
              required
            />
            <small>
              Captura o fotografía PNG/JPG de hasta 5 MB. Solo tú y administración pueden verla.
            </small>
          </div>
          <p>
            El dinero quedará congelado hasta la resolución. Si la evidencia es concluyente,
            recibirás un reembolso y tu rating subirá 0,25. Si no es concluyente, se abonará al
            vendedor y tu rating bajará 0,25.
          </p>
          <button className="btn btn-primary" disabled={busy} type="submit">
            {busy ? 'Enviando evidencia…' : 'Presentar reclamo'}
          </button>
        </form>
      )}
    </div>
  );
}
