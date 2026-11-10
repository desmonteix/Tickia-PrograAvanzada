import { useRef, useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { money } from '../types';
import type { Ticket } from '../types';
import type { PayoutProfile } from '../payments';
import { settlementLabel } from '../payments';
import PayoutProfilePanel from './PayoutProfilePanel';

function validFile(file: File): string {
  if (!['image/png', 'image/jpeg'].includes(file.type)) return 'Selecciona una imagen PNG o JPG.';
  if (file.size > 5 * 1024 * 1024) return 'La imagen debe pesar como máximo 5 MB.';
  return '';
}
interface Sale extends Ticket {
  buyer?: { full_name: string; dni: string };
  renomination_deadline?: string;
  estimated_seller_amount?: number;
  seller_net_amount?: number | null;
  settlement_state?: string | null;
  settlement_error?: string | null;
  settlement_reference?: string | null;
  provider_fee?: number | null;
  total?: number;
}
function Sales() {
  const { data, loading, error, refresh } = useResource<Sale[]>('/tickets/my-sales');
  const [notice, setNotice] = useState('');
  const [failure, setFailure] = useState('');
  const [busy, setBusy] = useState('');
  async function renominate(ticket: Ticket, file?: File) {
    if (!file) return;
    const validation = validFile(file);
    if (validation) {
      setFailure(validation);
      return;
    }
    setFailure('');
    setBusy(ticket.id);
    const form = new FormData();
    form.append('file', file);
    try {
      await api.post(`/tickets/${ticket.id}/renominate`, form);
      setNotice('Archivo de renominación actualizado.');
      refresh();
    } catch (err) {
      setFailure(errorMessage(err));
    } finally {
      setBusy('');
    }
  }
  async function share(ticket: Ticket) {
    const url = new URL(window.location.origin);
    url.searchParams.set('ref_ticket', ticket.id);
    try {
      if (navigator.share)
        await navigator.share({
          title: ticket.event_name,
          text: `Mi entrada para ${ticket.event_name} está en Tickia.`,
          url: url.toString(),
        });
      else if (navigator.clipboard) {
        await navigator.clipboard.writeText(url.toString());
        setNotice('Copiaste el enlace de tu entrada.');
      } else setNotice(`Enlace de tu entrada: ${url}`);
    } catch (err) {
      if (!(err instanceof DOMException && err.name === 'AbortError'))
        setFailure('No pudimos compartir el enlace. Inténtalo otra vez.');
    }
  }
  if (loading) return <p role="status">Cargando tus ventas…</p>;
  return (
    <>
      {(error || failure) && (
        <p role="alert" className="error-message">
          {error || failure}
          {error && (
            <button className="btn btn-secondary" onClick={refresh}>
              Reintentar
            </button>
          )}
        </p>
      )}
      {notice && (
        <p role="status" className="notice">
          {notice}
        </p>
      )}
      {!error && (
        <div className="ticket-grid">
          {!data?.length ? (
            <p className="empty-state">Todavía no publicaste entradas.</p>
          ) : (
            data.map((ticket) => (
              <article className="form-card" key={ticket.id}>
                <h2>{ticket.event_name}</h2>
                <p>
                  {ticket.zone} · {money(ticket.price)}
                </p>
                <p className="badge">{ticket.estado.replaceAll('_', ' ')}</p>
                {ticket.settlement_state && (
                  <>
                    <p>
                      {ticket.settlement_state === 'SUCCEEDED' && !ticket.settlement_reference
                        ? 'Liquidación registrada; sin referencia bancaria disponible en esta vista.'
                        : settlementLabel(ticket.settlement_state)}
                    </p>
                    {ticket.estado === 'REEMBOLSADA' ? (
                      <p>
                        Reembolso registrado para esta entrada; no corresponde un abono al vendedor.
                      </p>
                    ) : ticket.seller_net_amount != null ? (
                      <p>
                        Neto calculado: <strong>{money(Number(ticket.seller_net_amount))}</strong>.
                        El estado mostrado indica si corresponde y se ejecutó el abono.
                      </p>
                    ) : (
                      <p>
                        Estimado después de la comisión Tickia:{' '}
                        {money(ticket.estimated_seller_amount ?? ticket.price * 0.9)}. Falta
                        conciliar los cargos del proveedor.
                      </p>
                    )}
                    {ticket.provider_fee != null && (
                      <p>Cargos del proveedor: {money(Number(ticket.provider_fee))}.</p>
                    )}
                    {ticket.settlement_error && (
                      <p className="error-message">{ticket.settlement_error}</p>
                    )}
                    {ticket.settlement_reference && (
                      <p>Referencia financiera: {ticket.settlement_reference}</p>
                    )}
                  </>
                )}
                {ticket.estado === 'PENDIENTE_RENOMINACION' && (
                  <div className="input-group">
                    <p>
                      Completa el cambio de titular en la tiquetera antes de subir el nuevo archivo.
                    </p>
                    {ticket.buyer && (
                      <p>
                        Titular: {ticket.buyer.full_name} · Documento: {ticket.buyer.dni}
                      </p>
                    )}
                    <label htmlFor={`renominate-${ticket.id}`}>Subir entrada renominada</label>
                    <input
                      id={`renominate-${ticket.id}`}
                      type="file"
                      accept="image/png,image/jpeg"
                      disabled={!!busy}
                      onChange={(event) => void renominate(ticket, event.target.files?.[0])}
                    />
                    <small>Renomina primero en la tiquetera oficial. PNG o JPG, máximo 5 MB.</small>
                  </div>
                )}
                {ticket.estado === 'DISPONIBLE' && (
                  <button className="btn btn-secondary" onClick={() => void share(ticket)}>
                    Compartir entrada
                  </button>
                )}
              </article>
            ))
          )}
        </div>
      )}
    </>
  );
}

export default function SellerFlow() {
  const payoutProfile = useResource<PayoutProfile>('/payments/payout-profile');
  const canPublish =
    !payoutProfile.loading &&
    !payoutProfile.error &&
    !!payoutProfile.data &&
    (!payoutProfile.data.required || payoutProfile.data.can_sell);
  const [tab, setTab] = useState<'upload' | 'sales'>('upload');
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [busy, setBusy] = useState(false);
  const [nominated, setNominated] = useState(false);
  const formRef = useRef<HTMLFormElement>(null);
  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || !canPublish) return;
    const form = new FormData(event.currentTarget);
    const file = form.get('file');
    if (!(file instanceof File) || !file.size) {
      setError('Selecciona una imagen de tu entrada.');
      return;
    }
    const validation = validFile(file);
    if (validation) {
      setError(validation);
      return;
    }
    form.set('is_nominated', String(nominated));
    form.set('is_renominated', String(form.get('is_renominated') === 'on'));
    form.set('event_date', new Date(`${form.get('event_date')}:00-05:00`).toISOString());
    form.set('event_end_date', new Date(`${form.get('event_end_date')}:00-05:00`).toISOString());
    setError('');
    setSuccess('');
    setBusy(true);
    try {
      await api.post('/tickets/upload', form);
      setSuccess('Publicaste tu entrada. Ya puedes verla en el catálogo.');
      formRef.current?.reset();
      setNominated(false);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  return (
    <section aria-labelledby="seller-title">
      <p className="eyebrow">Si tú no vas, que vaya alguien</p>
      <h1 id="seller-title">Vende tu entrada</h1>
      <div className="actions">
        <button
          className={`btn ${tab === 'upload' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setTab('upload')}
        >
          Publicar entrada
        </button>
        <button
          className={`btn ${tab === 'sales' ? 'btn-primary' : 'btn-secondary'}`}
          onClick={() => setTab('sales')}
        >
          Mis ventas
        </button>
      </div>
      <PayoutProfilePanel
        profile={payoutProfile.data}
        loading={payoutProfile.loading}
        error={payoutProfile.error}
        refresh={payoutProfile.refresh}
      />
      {tab === 'sales' ? (
        <Sales />
      ) : (
        <div className="form-card medium">
          <h2>Cuéntanos sobre tu entrada</h2>
          <p>
            Usa los datos del evento y el archivo original. La lectura del QR no certifica su
            validez ante la tiquetera.
          </p>
          {error && (
            <p role="alert" className="error-message">
              {error}
            </p>
          )}
          {success && (
            <p role="status" className="notice">
              {success}
            </p>
          )}
          <form ref={formRef} onSubmit={(event) => void submit(event)}>
            <fieldset className="payment-fields" disabled={busy || !canPublish}>
              <legend>Datos de la entrada</legend>
              <div className="input-group">
                <label htmlFor="event-name">Nombre del evento</label>
                <input
                  id="event-name"
                  className="input-field"
                  name="event_name"
                  required
                  minLength={3}
                  maxLength={200}
                />
              </div>
              <div className="input-group">
                <label htmlFor="event-end-date">Finalización del evento (Perú)</label>
                <input
                  id="event-end-date"
                  className="input-field"
                  type="datetime-local"
                  name="event_end_date"
                  required
                />
                <small>El plazo de reclamo cierra 24 horas después de esta fecha y hora.</small>
              </div>
              <div className="form-row">
                <div className="input-group">
                  <label htmlFor="event-date">Fecha y hora del evento (Perú)</label>
                  <input
                    id="event-date"
                    className="input-field"
                    type="datetime-local"
                    name="event_date"
                    required
                  />
                </div>
                <div className="input-group">
                  <label htmlFor="event-zone">Zona</label>
                  <input
                    id="event-zone"
                    className="input-field"
                    name="zone"
                    required
                    maxLength={100}
                  />
                </div>
              </div>
              <div className="form-row">
                <div className="input-group">
                  <label htmlFor="event-company">Tiquetera</label>
                  <select
                    id="event-company"
                    className="input-field"
                    name="ticketing_company"
                    required
                  >
                    <option value="">Selecciona la tiquetera</option>
                    <option value="teleticket">Teleticket</option>
                    <option value="joinnus">Joinnus</option>
                  </select>
                </div>
                <div className="input-group">
                  <label htmlFor="event-price">Precio de venta (S/)</label>
                  <input
                    id="event-price"
                    className="input-field"
                    type="number"
                    name="price"
                    required
                    min="3"
                    max="5000"
                    step="0.01"
                  />
                </div>
              </div>
              <p className="notice">
                Tickia cobra una comisión del 10 % con IGV incluido a quien vende. Los cargos de la
                pasarela también son del vendedor. El comprador paga el precio publicado sin
                sobrecostos.
              </p>
              <div className="input-group">
                <label htmlFor="event-type">Tipo de entrada</label>
                <select
                  id="event-type"
                  className="input-field"
                  value={nominated ? 'nominada' : 'no_nominada'}
                  onChange={(event) => setNominated(event.target.value === 'nominada')}
                >
                  <option value="no_nominada">No nominada</option>
                  <option value="nominada">Nominada</option>
                </select>
              </div>
              {nominated && (
                <div className="input-group">
                  <label className="checkbox-label">
                    <input type="checkbox" name="is_renominated" /> La entrada ya está renominada en
                    la tiquetera
                  </label>
                  <p className="muted">
                    Si requiere cambio de titular, deberá completarse mediante el proceso oficial de
                    la tiquetera.
                  </p>
                </div>
              )}
              <div className="input-group">
                <label htmlFor="event-file">Imagen original de la entrada</label>
                <input
                  id="event-file"
                  className="input-field"
                  name="file"
                  type="file"
                  accept="image/png,image/jpeg"
                  required
                />
                <small>PNG o JPG, máximo 5 MB. El QR debe verse completo.</small>
              </div>
              <button
                className="btn btn-primary full-width"
                type="submit"
                disabled={busy || !canPublish}
              >
                {busy ? 'Publicando…' : 'Publicar mi entrada'}
              </button>
            </fieldset>
          </form>
        </div>
      )}
    </section>
  );
}
