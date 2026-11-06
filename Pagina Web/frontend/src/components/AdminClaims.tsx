import { useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import type { Purchase } from '../types';
import { purchaseStatus } from '../purchaseStatus';

interface Claim extends Purchase {
  description: string | null;
  evidence: { id: string; media_type: string }[];
}
export default function AdminClaims() {
  const { data, loading, error, refresh } = useResource<Claim[]>('/purchases/admin/cases');
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState('');
  async function download(id: string) {
    try {
      const response = await api.get<Blob>(`/purchases/evidence/${id}`, { responseType: 'blob' });
      const url = URL.createObjectURL(response.data);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'evidencia.' + (response.data.type === 'image/png' ? 'png' : 'jpg');
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch {
      setFailure('No pudimos descargar la evidencia.');
    }
  }
  async function resolve(purchase: Claim, valid: boolean) {
    const reason = window.prompt('Escribe la justificación de tu decisión (mínimo 10 caracteres).');
    if (!reason) return;
    if (reason.trim().length < 10) {
      setFailure('La justificación debe tener al menos 10 caracteres.');
      return;
    }
    if (
      !window.confirm(
        valid
          ? 'Aceptar enviará una orden de reembolso al comprador. ¿Confirmas la decisión?'
          : 'Rechazar enviará una orden de abono al vendedor y restará 0,25 al rating del comprador. ¿Confirmas?',
      )
    )
      return;
    setBusy(purchase.purchase_id);
    setFailure('');
    try {
      await api.post(`/purchases/admin/${purchase.purchase_id}/resolve`, { valid, reason });
      refresh();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy('');
    }
  }
  return (
    <section aria-labelledby="claims-title">
      <h2 id="claims-title">Reclamos y liquidaciones pendientes</h2>
      {(error || failure) && (
        <p role="alert" className="error-message">
          {error || failure}
          <button className="btn btn-secondary" onClick={refresh}>
            Reintentar reclamos
          </button>
        </p>
      )}
      {loading ? (
        <p role="status">Cargando reclamos…</p>
      ) : !data?.length ? (
        <p>No hay reclamos ni liquidaciones pendientes.</p>
      ) : (
        <div className="ticket-grid">
          {data.map((claim) => (
            <article className="form-card" key={claim.purchase_id}>
              <h3>{claim.event_name}</h3>
              <p>{claim.description || 'Operación pendiente de ejecución financiera.'}</p>
              <p>{purchaseStatus(claim)}</p>
              {claim.settlement_error && <p className="muted">{claim.settlement_error}</p>}
              {claim.evidence.map((item, index) => (
                <button
                  className="btn btn-secondary"
                  key={item.id}
                  onClick={() => void download(item.id)}
                >
                  Descargar evidencia {index + 1}
                </button>
              ))}
              {claim.review_state === 'DISPUTED' && (
                <div className="actions">
                  <button
                    className="btn btn-primary"
                    disabled={!!busy}
                    onClick={() => void resolve(claim, true)}
                  >
                    Evidencia concluyente · Reembolsar
                  </button>
                  <button
                    className="btn btn-secondary"
                    disabled={!!busy}
                    onClick={() => void resolve(claim, false)}
                  >
                    Evidencia no concluyente · Abonar al vendedor
                  </button>
                </div>
              )}
            </article>
          ))}
        </div>
      )}
    </section>
  );
}
