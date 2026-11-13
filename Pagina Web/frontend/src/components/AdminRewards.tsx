import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { mutationReason, rewardPayload } from '../adminConfig';
import type { Referrals } from '../promotions';
import { percent, validRate } from '../promotions';

interface RewardRow extends Pick<
  Referrals,
  | 'reward_kind'
  | 'choice'
  | 'discount_rate'
  | 'seller_commission_rate'
  | 'reward_status'
  | 'pending_upgrade'
> {
  user_id: string;
  email: string;
}
export default function AdminRewards({ onChanged }: { onChanged: () => void }) {
  const [skip, setSkip] = useState(0),
    [userSkip, setUserSkip] = useState(0);
  const rows = useResource<RewardRow[]>(`/admin/rewards?skip=${skip}&limit=50`);
  const users = useResource<{ id: string; email: string }[]>(
    `/admin/users?skip=${userSkip}&limit=50`,
  );
  const [selected, setSelected] = useState(''),
    [revoking, setRevoking] = useState<RewardRow | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  const existing = rows.data?.find((row) => row.user_id === selected);
  const blocked = existing && ['USED', 'RESERVED', 'REVOKED'].includes(existing.reward_status);
  function changed(message: string) {
    setNotice(message);
    rows.refresh();
    onChanged();
  }
  async function grant(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || blocked) return;
    setError('');
    try {
      const payload = rewardPayload(new FormData(event.currentTarget));
      setBusy(true);
      await api.post('/admin/rewards', payload);
      changed('Beneficio guardado. Se conserva el historial de uso.');
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  async function revoke(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !revoking) return;
    setError('');
    try {
      const reason = mutationReason(new FormData(event.currentTarget));
      setBusy(true);
      await api.delete(`/admin/rewards/${encodeURIComponent(revoking.user_id)}`, {
        data: { reason },
      });
      setRevoking(null);
      changed('Beneficio revocado. El historial se conserva.');
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Beneficios de usuarios">
      <h3>Beneficios</h3>
      <p>
        Solo se crean o editan beneficios disponibles, sin reserva. Un beneficio usado, reservado o
        revocado no se reinicia. Los cambios no modifican pagos ya iniciados.
      </p>
      {(error || rows.error || users.error) && (
        <p role="alert" className="error-message">
          {error || rows.error || users.error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      <form onSubmit={(event) => void grant(event)} className="form-card admin-config-form">
        <fieldset className="payment-fields" disabled={busy || users.loading || !!users.error}>
          <legend>Conceder o editar un beneficio disponible</legend>
          <div className="input-group">
            <label htmlFor="admin-reward-user">Usuario beneficiario</label>
            <select
              id="admin-reward-user"
              className="input-field"
              name="user_id"
              required
              value={selected}
              onChange={(event) => setSelected(event.target.value)}
            >
              <option value="">Selecciona un usuario registrado</option>
              {users.data?.map((user) => (
                <option key={user.id} value={user.id}>
                  {user.email}
                </option>
              ))}
            </select>
          </div>
          <div className="actions">
            <button
              type="button"
              className="btn btn-ghost"
              disabled={userSkip === 0}
              onClick={() => {
                setSelected('');
                setUserSkip((value) => Math.max(0, value - 50));
              }}
            >
              Usuarios anteriores
            </button>
            <button
              type="button"
              className="btn btn-ghost"
              disabled={!users.data || users.data.length < 50}
              onClick={() => {
                setSelected('');
                setUserSkip((value) => value + 50);
              }}
            >
              Usuarios siguientes
            </button>
          </div>
          <label>
            Descuento de compra (%)
            <input
              className="input-field"
              name="buyer_discount_rate"
              type="number"
              min="0"
              max="50"
              step="0.01"
              required
            />
          </label>
          <label>
            Comisión para próxima venta (%) — opcional
            <input
              className="input-field"
              name="seller_commission_rate"
              type="number"
              min="0"
              max="99.99"
              step="0.01"
            />
          </label>
          <p>
            Deja la comisión vacía para no ofrecer la opción venta. El beneficio de venta no elimina
            los cargos del proveedor.
          </p>
          <label>
            Motivo del beneficio
            <textarea
              className="input-field"
              name="reason"
              minLength={8}
              maxLength={500}
              required
            />
          </label>
          {blocked && (
            <p>Este usuario tiene un beneficio {existing.reward_status}; no puede reemplazarse.</p>
          )}
          <button className="btn btn-primary" disabled={busy || !!blocked}>
            Guardar beneficio
          </button>
        </fieldset>
      </form>
      {revoking && (
        <form className="form-card" onSubmit={(event) => void revoke(event)}>
          <h4>Revocar beneficio de {revoking.email}</h4>
          <label>
            Motivo de la revocación
            <textarea
              className="input-field"
              name="reason"
              required
              minLength={8}
              maxLength={500}
            />
          </label>
          <div className="actions">
            <button className="btn btn-primary" disabled={busy}>
              Confirmar revocación
            </button>
            <button
              type="button"
              className="btn btn-secondary"
              disabled={busy}
              onClick={() => setRevoking(null)}
            >
              Cancelar revocación
            </button>
          </div>
        </form>
      )}
      {rows.loading ? (
        <p role="status">Consultando beneficios…</p>
      ) : (
        <div className="table-scroll" role="region" aria-label="Listado de beneficios" tabIndex={0}>
          <table>
            <caption className="sr-only">Beneficios y estados</caption>
            <thead>
              <tr>
                <th scope="col">Usuario</th>
                <th scope="col">Beneficio</th>
                <th scope="col">Estado</th>
                <th scope="col">Acción</th>
              </tr>
            </thead>
            <tbody>
              {rows.data?.map((row) => (
                <tr key={row.user_id}>
                  <td>{row.email}</td>
                  <td>
                    {row.reward_kind}
                    <br />
                    Compra: {percent(row.discount_rate)} %<br />
                    Venta:{' '}
                    {validRate(row.seller_commission_rate)
                      ? `${percent(row.seller_commission_rate)} %`
                      : 'No disponible'}
                    <br />
                    Elección: {row.choice ?? 'Sin elegir'}
                  </td>
                  <td>
                    {row.reward_status}
                    {row.pending_upgrade && ' · Mejora pendiente'}
                  </td>
                  <td>
                    {row.reward_status === 'AVAILABLE' && (
                      <button
                        className="btn btn-secondary"
                        disabled={busy}
                        onClick={() => setRevoking(row)}
                      >
                        Revocar {row.email}
                      </button>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!rows.loading && rows.data?.length === 0 && <p>No hay beneficios en esta página.</p>}
      <div className="actions">
        <button
          className="btn btn-secondary"
          disabled={skip === 0 || rows.loading}
          onClick={() => setSkip((value) => Math.max(0, value - 50))}
        >
          Beneficios anteriores
        </button>
        <button
          className="btn btn-secondary"
          disabled={rows.loading || !rows.data || rows.data.length < 50}
          onClick={() => setSkip((value) => value + 50)}
        >
          Beneficios siguientes
        </button>
        <button
          className="btn btn-ghost"
          onClick={() => {
            rows.refresh();
            users.refresh();
          }}
        >
          Actualizar beneficios
        </button>
      </div>
    </section>
  );
}
