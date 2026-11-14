import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import type { OperationSettings } from '../promotions';
import { settingsPayload } from '../adminConfig';

function SettingsEditor({ initial, saved }: { initial: OperationSettings; saved: () => void }) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError('');
    try {
      const payload = settingsPayload(new FormData(event.currentTarget));
      setBusy(true);
      await api.patch('/admin/settings', payload);
      saved();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form onSubmit={(event) => void submit(event)} className="form-card admin-config-form">
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <fieldset className="payment-fields" disabled={busy}>
        <legend>Nuevas operaciones permitidas</legend>
        {(
          [
            ['registrations_enabled', 'Permitir nuevos registros'],
            ['publications_enabled', 'Permitir nuevas publicaciones'],
            ['purchases_enabled', 'Permitir nuevas compras'],
            ['maintenance_mode', 'Activar mantenimiento'],
          ] as const
        ).map(([key, label]) => (
          <label className="checkbox-label" key={key}>
            <input name={key} type="checkbox" defaultChecked={initial[key]} />
            {label}
          </label>
        ))}
        <p>
          El mantenimiento pausa nuevas operaciones. El ingreso, compras existentes, reclamos y
          conciliación de pagos siguen disponibles. Permitir compras no activa el proveedor
          financiero.
        </p>
        <div className="input-group">
          <label htmlFor="admin-public-announcement">Aviso público</label>
          <textarea
            id="admin-public-announcement"
            className="input-field"
            name="announcement"
            maxLength={500}
            defaultValue={initial.announcement}
          />
        </div>
        <label>
          Motivo de los ajustes
          <textarea className="input-field" name="reason" required minLength={8} maxLength={500} />
        </label>
        <button className="btn btn-primary" disabled={busy}>
          {busy ? 'Guardando…' : 'Guardar ajustes operativos'}
        </button>
      </fieldset>
    </form>
  );
}
export default function AdminSettings({ onChanged }: { onChanged: () => void }) {
  const resource = useResource<OperationSettings>('/admin/settings');
  const [notice, setNotice] = useState('');
  return (
    <section aria-label="Ajustes operativos">
      <h3>Operación y avisos</h3>
      <button className="btn btn-secondary" onClick={resource.refresh}>
        Consultar ajustes
      </button>
      {notice && <p role="status">{notice}</p>}
      {resource.error && (
        <p role="alert" className="error-message">
          {resource.error}
        </p>
      )}
      {resource.loading ? (
        <p role="status">Consultando ajustes…</p>
      ) : (
        resource.data &&
        !resource.error && (
          <SettingsEditor
            key={JSON.stringify(resource.data)}
            initial={resource.data}
            saved={() => {
              setNotice('Ajustes guardados.');
              resource.refresh();
              onChanged();
            }}
          />
        )
      )}
    </section>
  );
}
