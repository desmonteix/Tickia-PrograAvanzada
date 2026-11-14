import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { campaignPayload, mutationReason, peruInput } from '../adminConfig';
import type { CampaignConfig } from '../adminConfig';
import { eventDate } from '../types';
import { percent } from '../promotions';

const rateFields = [
  ['listing_commission_rate', 'Comisión por publicación (%)', 99.99],
  ['registration_discount_rate', 'Descuento por registro referido (%)', 50],
  ['seller_buyer_discount_rate', 'Descuento por vendedor referido (%)', 50],
  ['seller_commission_rate', 'Comisión de la venta beneficiada (%)', 99.99],
] as const;
function CampaignEditor({
  initial,
  saved,
  cancel,
}: {
  initial: CampaignConfig | null;
  saved: () => void;
  cancel: () => void;
}) {
  const [busy, setBusy] = useState(false),
    [error, setError] = useState('');
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy) return;
    setError('');
    try {
      const payload = campaignPayload(new FormData(event.currentTarget));
      setBusy(true);
      if (initial) await api.patch(`/admin/campaigns/${encodeURIComponent(initial.id)}`, payload);
      else await api.post('/admin/campaigns', payload);
      saved();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <form className="form-card admin-config-form" onSubmit={(event) => void submit(event)}>
      <h3>{initial ? `Editar campaña: ${initial.name}` : 'Nueva campaña'}</h3>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
      <fieldset className="payment-fields" disabled={busy}>
        <legend>Condiciones de campaña</legend>
        <label>
          Nombre de campaña
          <input
            className="input-field"
            name="name"
            required
            minLength={3}
            maxLength={120}
            defaultValue={initial?.name ?? ''}
          />
        </label>
        <div className="form-row">
          <label>
            Inicio (hora de Perú)
            <input
              className="input-field"
              type="datetime-local"
              name="starts_at"
              required
              defaultValue={initial ? peruInput(initial.starts_at) : ''}
            />
          </label>
          <label>
            Final (hora de Perú)
            <input
              className="input-field"
              type="datetime-local"
              name="ends_at"
              required
              defaultValue={initial ? peruInput(initial.ends_at) : ''}
            />
          </label>
        </div>
        <p>
          El final no está incluido. Las campañas habilitadas no pueden superponerse. Los importes
          de pagos ya iniciados se conservan.
        </p>
        <div className="form-row">
          {rateFields.map(([key, label, max]) => (
            <label key={key}>
              {label}
              <input
                className="input-field"
                type="number"
                name={key}
                required
                min="0"
                max={max}
                step="0.01"
                defaultValue={initial ? initial[key] * 100 : ''}
              />
            </label>
          ))}
        </div>
        <label className="checkbox-label">
          <input type="checkbox" name="enabled" defaultChecked={initial?.enabled ?? false} />{' '}
          Campaña habilitada
        </label>
        <label>
          Motivo del cambio
          <textarea className="input-field" name="reason" required minLength={8} maxLength={500} />
        </label>
        <div className="actions">
          <button className="btn btn-primary" type="submit" disabled={busy}>
            {busy ? 'Guardando…' : 'Guardar campaña'}
          </button>
          <button className="btn btn-secondary" type="button" disabled={busy} onClick={cancel}>
            Cancelar edición
          </button>
        </div>
      </fieldset>
    </form>
  );
}
export default function AdminCampaigns({ onChanged }: { onChanged: () => void }) {
  const resource = useResource<CampaignConfig[]>('/admin/campaigns');
  const [editor, setEditor] = useState<CampaignConfig | 'new' | null>(null);
  const [archive, setArchive] = useState<CampaignConfig | null>(null);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(''),
    [notice, setNotice] = useState('');
  function saved() {
    setEditor(null);
    setNotice('Campaña guardada. Los pagos ya iniciados conservan su cotización.');
    resource.refresh();
    onChanged();
  }
  async function archiveCampaign(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!archive || busy) return;
    setError('');
    try {
      const reason = mutationReason(new FormData(event.currentTarget));
      setBusy(true);
      await api.delete(`/admin/campaigns/${encodeURIComponent(archive.id)}`, { data: { reason } });
      setArchive(null);
      setNotice('Campaña archivada. El historial se conserva.');
      resource.refresh();
      onChanged();
    } catch (failure) {
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-label="Campañas configurables">
      <h3>Campañas</h3>
      <p>
        Estas condiciones afectan nuevas operaciones. No habilitan una pasarela ni confirman
        movimientos bancarios.
      </p>
      <div className="actions">
        <button
          className="btn btn-primary"
          onClick={() => {
            setEditor('new');
            setArchive(null);
          }}
        >
          Crear campaña
        </button>
        <button className="btn btn-secondary" onClick={resource.refresh}>
          Actualizar campañas
        </button>
      </div>
      {(error || resource.error) && (
        <p role="alert" className="error-message">
          {error || resource.error}
        </p>
      )}
      {notice && <p role="status">{notice}</p>}
      {editor && (
        <CampaignEditor
          key={editor === 'new' ? 'new' : editor.id}
          initial={editor === 'new' ? null : editor}
          saved={saved}
          cancel={() => setEditor(null)}
        />
      )}
      {archive && (
        <form className="form-card" onSubmit={(event) => void archiveCampaign(event)}>
          <h4>Archivar {archive.name}</h4>
          <p>Se conservará el registro y dejará de ofrecerse esta campaña.</p>
          <label>
            Motivo del archivo
            <textarea
              name="reason"
              className="input-field"
              required
              minLength={8}
              maxLength={500}
            />
          </label>
          <div className="actions">
            <button className="btn btn-primary" disabled={busy}>
              Confirmar archivo
            </button>
            <button
              className="btn btn-secondary"
              type="button"
              disabled={busy}
              onClick={() => setArchive(null)}
            >
              Cancelar archivo
            </button>
          </div>
        </form>
      )}
      {resource.loading ? (
        <p role="status">Consultando campañas…</p>
      ) : resource.data?.length === 0 ? (
        <p>No hay campañas configuradas.</p>
      ) : (
        <div className="table-scroll" role="region" aria-label="Listado de campañas" tabIndex={0}>
          <table>
            <caption className="sr-only">Campañas y condiciones guardadas</caption>
            <thead>
              <tr>
                <th scope="col">Campaña</th>
                <th scope="col">Plazo (Perú)</th>
                <th scope="col">Condiciones</th>
                <th scope="col">Estado y acciones</th>
              </tr>
            </thead>
            <tbody>
              {resource.data?.map((item) => (
                <tr key={item.id}>
                  <td>{item.name}</td>
                  <td>
                    {eventDate(item.starts_at)}
                    <br />
                    Hasta {eventDate(item.ends_at)} (exclusivo)
                  </td>
                  <td>
                    Publicación: {percent(item.listing_commission_rate)} %<br />
                    Registro: {percent(item.registration_discount_rate)} %<br />
                    Vendedor referido: compra {percent(item.seller_buyer_discount_rate)} % / venta{' '}
                    {percent(item.seller_commission_rate)} %
                  </td>
                  <td>
                    {item.archived ? 'Archivada' : item.enabled ? 'Habilitada' : 'Deshabilitada'}
                    {!item.archived && (
                      <div className="actions">
                        <button
                          className="btn btn-secondary"
                          onClick={() => {
                            setEditor(item);
                            setArchive(null);
                          }}
                        >
                          Editar {item.name}
                        </button>
                        <button
                          className="btn btn-ghost"
                          onClick={() => {
                            setArchive(item);
                            setEditor(null);
                          }}
                        >
                          Archivar {item.name}
                        </button>
                      </div>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
