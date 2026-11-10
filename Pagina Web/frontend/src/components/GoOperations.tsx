import { useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';

interface Operation {
  operation_id: string;
  event_name: string;
  kind: string;
  status: string;
  provider_id: string | null;
  amount: number;
  error: string | null;
  can_retry: boolean;
}

export default function GoOperations() {
  const resource = useResource<Operation[]>('/payments/admin/operations');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  async function retry(operation: Operation) {
    const reason = window.prompt(
      'Indica qué datos o saldo revisaste antes de autorizar otro intento (mínimo 10 caracteres).',
    );
    if (!reason) return;
    if (reason.trim().length < 10) {
      setError('Indica un motivo de al menos 10 caracteres.');
      return;
    }
    setBusy(operation.operation_id);
    setError('');
    try {
      await api.post(`/payments/admin/operations/${operation.operation_id}/retry`, { reason });
      resource.refresh();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy('');
    }
  }
  return (
    <section aria-label="Operaciones financieras de dLocal Go">
      <h2>Depósitos y devoluciones</h2>
      <p>
        Se muestran las últimas 100 operaciones. Los resultados pendientes se concilian
        automáticamente con dLocal Go.
      </p>
      <button className="btn btn-secondary" onClick={() => resource.refresh()}>
        Actualizar operaciones
      </button>
      {(error || resource.error) && (
        <p role="alert" className="error-message">
          {error || resource.error}
        </p>
      )}
      {resource.loading && <p role="status">Consultando operaciones…</p>}
      <div className="table-scroll" role="region" aria-label="Estado financiero" tabIndex={0}>
        <table>
          <caption className="sr-only">Depósitos y devoluciones de dLocal Go</caption>
          <thead>
            <tr>
              <th scope="col">Evento</th>
              <th scope="col">Operación</th>
              <th scope="col">Importe</th>
              <th scope="col">Estado / referencia</th>
              <th scope="col">Acción</th>
            </tr>
          </thead>
          <tbody>
            {resource.data?.map((operation) => (
              <tr key={operation.operation_id}>
                <td>{operation.event_name}</td>
                <td>{operation.kind === 'PAYOUT' ? 'Depósito' : 'Devolución'}</td>
                <td>{money(operation.amount)}</td>
                <td>
                  {operation.status}
                  <br />
                  {operation.provider_id || 'Referencia pendiente'}
                  {operation.error && <p>{operation.error}</p>}
                </td>
                <td>
                  {operation.can_retry && (
                    <button
                      className="btn btn-secondary"
                      disabled={!!busy}
                      onClick={() => retry(operation)}
                    >
                      Autorizar nuevo intento
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {!resource.loading && resource.data?.length === 0 && (
        <p>No hay operaciones financieras registradas.</p>
      )}
    </section>
  );
}
