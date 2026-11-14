import { useState } from 'react';
import { useResource } from '../useResource';
import { eventDate } from '../types';

interface AuditEntry {
  id: string;
  action: string;
  entity_type: string;
  entity_id: string;
  reason: string | null;
  timestamp: string;
}
export default function AdminAudit() {
  const [skip, setSkip] = useState(0),
    [search, setSearch] = useState('');
  const resource = useResource<AuditEntry[]>(`/admin/audit?skip=${skip}&limit=50`);
  const rows = resource.data?.filter((item) =>
    [item.action, item.entity_type, item.entity_id, item.reason]
      .join(' ')
      .toLocaleLowerCase()
      .includes(search.trim().toLocaleLowerCase()),
  );
  return (
    <section aria-label="Auditoría administrativa">
      <h3>Historial de cambios</h3>
      <p>Registros de auditoría de esta página. El filtro busca en los registros cargados.</p>
      <label>
        Filtrar auditoría
        <input
          className="input-field"
          type="search"
          value={search}
          onChange={(event) => setSearch(event.target.value)}
        />
      </label>
      {resource.error && (
        <p role="alert" className="error-message">
          {resource.error}
        </p>
      )}
      {resource.loading ? (
        <p role="status">Consultando auditoría…</p>
      ) : (
        <div
          className="table-scroll"
          role="region"
          aria-label="Registros de auditoría"
          tabIndex={0}
        >
          <table>
            <caption className="sr-only">Cambios administrativos registrados</caption>
            <thead>
              <tr>
                <th scope="col">Fecha (Perú)</th>
                <th scope="col">Acción</th>
                <th scope="col">Entidad</th>
                <th scope="col">Motivo</th>
              </tr>
            </thead>
            <tbody>
              {rows?.map((item) => (
                <tr key={item.id}>
                  <td>{eventDate(item.timestamp)}</td>
                  <td>{item.action}</td>
                  <td>
                    {item.entity_type}
                    <br />
                    {item.entity_id}
                  </td>
                  <td className="admin-reason">{item.reason || 'Sin motivo registrado'}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!resource.loading && rows?.length === 0 && (
        <p>No hay registros que coincidan en esta página.</p>
      )}
      <div className="actions">
        <button
          className="btn btn-secondary"
          disabled={resource.loading || skip === 0}
          onClick={() => setSkip((value) => Math.max(0, value - 50))}
        >
          Auditoría anterior
        </button>
        <button
          className="btn btn-secondary"
          disabled={resource.loading || !resource.data || resource.data.length < 50}
          onClick={() => setSkip((value) => value + 50)}
        >
          Auditoría siguiente
        </button>
        <button className="btn btn-ghost" onClick={resource.refresh}>
          Actualizar auditoría
        </button>
      </div>
    </section>
  );
}
