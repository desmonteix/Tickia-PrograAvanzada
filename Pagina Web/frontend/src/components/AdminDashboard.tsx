import { useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';
import AdminClaims from './AdminClaims';
import GoOperations from './GoOperations';
import AdminControlPanel from './AdminControlPanel';
interface Metrics {
  total_users: number;
  total_tickets: number;
  total_transactions: number;
  total_revenue: number;
  total_buyer_discounts?: number;
  platform_after_discounts?: number;
}
interface AdminUser {
  id: string;
  email: string;
  trust_score: number;
  rating?: number;
  warning_count?: number;
  is_suspended: boolean;
  banned_until: string | null;
  is_admin: boolean;
}
export default function AdminDashboard({
  onConfigurationChanged = () => undefined,
}: {
  onConfigurationChanged?: () => void;
}) {
  const metrics = useResource<Metrics>('/admin/metrics');
  const users = useResource<AdminUser[]>('/admin/users');
  const [error, setError] = useState('');
  const [busy, setBusy] = useState('');
  async function ban(user: AdminUser) {
    if (!window.confirm(`¿Suspender a ${user.email} durante 7 días?`)) return;
    setBusy(user.id);
    setError('');
    try {
      await api.post(`/admin/users/${user.id}/ban`, null, { params: { days: 7 } });
      users.refresh();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy('');
    }
  }
  const failure = error || metrics.error || users.error;
  return (
    <section>
      <h1>Administración</h1>
      {failure && (
        <p role="alert" className="error-message">
          {failure}
          <button
            className="btn btn-secondary"
            onClick={() => {
              metrics.refresh();
              users.refresh();
            }}
          >
            Reintentar
          </button>
        </p>
      )}
      {metrics.loading || users.loading ? (
        <p role="status">Cargando administración…</p>
      ) : (
        <>
          {metrics.data && (
            <dl className="metrics-grid">
              {[
                ['Usuarios', metrics.data.total_users],
                ['Entradas', metrics.data.total_tickets],
                ['Transacciones', metrics.data.total_transactions],
                ['Comisiones', money(metrics.data.total_revenue)],
                [
                  'Descuentos financiados',
                  metrics.data.total_buyer_discounts == null
                    ? 'Pendiente de información'
                    : money(metrics.data.total_buyer_discounts),
                ],
                [
                  'Comisiones menos descuentos',
                  metrics.data.platform_after_discounts == null
                    ? 'Pendiente de información'
                    : money(metrics.data.platform_after_discounts),
                ],
              ].map(([label, value]) => (
                <div className="form-card" key={label}>
                  <dt>{label}</dt>
                  <dd>{value}</dd>
                </div>
              ))}
            </dl>
          )}
          <AdminClaims />
          <GoOperations />
          <AdminControlPanel onChanged={onConfigurationChanged} />
          <h2>Gestión de usuarios</h2>
          <div
            className="table-scroll"
            role="region"
            aria-label="Usuarios registrados"
            tabIndex={0}
          >
            <table>
              <caption className="sr-only">Estado y acciones de los usuarios</caption>
              <thead>
                <tr>
                  <th scope="col">Correo</th>
                  <th scope="col">Rating / Advertencias</th>
                  <th scope="col">Estado</th>
                  <th scope="col">Acciones</th>
                </tr>
              </thead>
              <tbody>
                {users.data?.map((user) => (
                  <tr key={user.id}>
                    <td>
                      {user.email}
                      {user.is_admin && ' · Admin'}
                    </td>
                    <td>
                      {typeof user.rating === 'number' ? `${user.rating.toFixed(2)} / 5` : '—'} ·{' '}
                      {user.warning_count ?? 0} advertencias
                    </td>
                    <td>
                      {user.is_suspended ||
                      (user.banned_until && new Date(user.banned_until) > new Date())
                        ? 'Suspendido'
                        : 'Activo'}
                    </td>
                    <td>
                      {!user.is_admin && (
                        <button
                          className="btn btn-secondary"
                          disabled={!!busy}
                          onClick={() => void ban(user)}
                        >
                          {busy === user.id ? 'Procesando…' : 'Suspender 7 días'}
                        </button>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}
    </section>
  );
}
