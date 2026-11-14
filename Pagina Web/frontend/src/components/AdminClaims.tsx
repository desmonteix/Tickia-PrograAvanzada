import { useEffect, useRef, useState } from 'react';
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
  const [search, setSearch] = useState(''),
    [filter, setFilter] = useState('all');
  const [preview, setPreview] = useState<string | null>(null),
    [evidenceBusy, setEvidenceBusy] = useState('');
  const dialog = useRef<HTMLDialogElement>(null);
  const filtered = (data ?? []).filter(
    (item) =>
      (filter === 'all' ||
        (filter === 'disputed'
          ? item.review_state === 'DISPUTED'
          : item.review_state === 'RESOLVED')) &&
      [item.event_name, item.description]
        .join(' ')
        .toLocaleLowerCase()
        .includes(search.trim().toLocaleLowerCase()),
  );
  useEffect(() => {
    if (preview) dialog.current?.showModal();
    return () => {
      if (preview) URL.revokeObjectURL(preview);
    };
  }, [preview]);
  async function download(id: string, show = false) {
    if (evidenceBusy) return;
    setEvidenceBusy(id);
    setFailure('');
    try {
      const response = await api.get<Blob>(`/purchases/evidence/${id}`, { responseType: 'blob' });
      if (!['image/png', 'image/jpeg'].includes(response.data.type))
        throw new Error('Formato no válido');
      const url = URL.createObjectURL(response.data);
      if (show) {
        setPreview(url);
        return;
      }
      const link = document.createElement('a');
      link.href = url;
      link.download = 'evidencia.' + (response.data.type === 'image/png' ? 'png' : 'jpg');
      link.click();
      window.setTimeout(() => URL.revokeObjectURL(url), 30000);
    } catch {
      setFailure('No pudimos descargar la evidencia.');
    } finally {
      setEvidenceBusy('');
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
      <p>Se muestran hasta 100 casos. Los filtros se aplican a los casos cargados.</p>
      <div className="form-row">
        <label>
          Buscar reclamos
          <input
            className="input-field"
            type="search"
            value={search}
            onChange={(event) => setSearch(event.target.value)}
          />
        </label>
        <div className="input-group">
          <label htmlFor="claim-state-filter">Estado del caso</label>
          <select
            id="claim-state-filter"
            className="input-field"
            value={filter}
            onChange={(event) => setFilter(event.target.value)}
          >
            <option value="all">Todos los casos</option>
            <option value="disputed">Reclamos abiertos</option>
            <option value="settlement">Liquidaciones pendientes</option>
          </select>
        </div>
      </div>
      <button className="btn btn-secondary" onClick={refresh}>
        Actualizar casos
      </button>
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
      ) : !filtered.length ? (
        <p>
          {data?.length
            ? 'No hay casos que coincidan con estos filtros.'
            : 'No hay reclamos ni liquidaciones pendientes.'}
        </p>
      ) : (
        <div className="ticket-grid">
          {filtered.map((claim) => (
            <article className="form-card" key={claim.purchase_id}>
              <h3>{claim.event_name}</h3>
              <p>{claim.description || 'Operación pendiente de ejecución financiera.'}</p>
              <p>{purchaseStatus(claim)}</p>
              {claim.settlement_error && <p className="muted">{claim.settlement_error}</p>}
              {claim.evidence.map((item, index) => (
                <div className="actions" key={item.id}>
                  <button
                    className="btn btn-secondary"
                    disabled={!!evidenceBusy}
                    onClick={() => void download(item.id, true)}
                  >
                    Ver evidencia {index + 1}
                  </button>
                  <button
                    className="btn btn-secondary"
                    key={item.id}
                    disabled={!!evidenceBusy}
                    onClick={() => void download(item.id)}
                  >
                    Descargar evidencia {index + 1}
                  </button>
                </div>
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
      <dialog
        ref={dialog}
        className="evidence-preview"
        aria-label="Vista de evidencia"
        onCancel={() => setPreview(null)}
      >
        <h3>Evidencia adjunta</h3>
        {preview && <img src={preview} alt="Imagen aportada como evidencia del reclamo" />}
        <button
          className="btn btn-secondary"
          onClick={() => {
            dialog.current?.close();
            setPreview(null);
          }}
        >
          Cerrar evidencia
        </button>
      </dialog>
    </section>
  );
}
