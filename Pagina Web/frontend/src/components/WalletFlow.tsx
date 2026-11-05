import { useEffect, useState } from 'react';
import api, { errorMessage } from '../api';
import { useResource } from '../useResource';
import { eventDate } from '../types';
import type { Ticket, Purchase, User } from '../types';
import PurchaseActions from './PurchaseActions';

export default function WalletFlow() {
  const { data, loading, error, refresh } = useResource<Purchase[]>('/purchases');
  const profile = useResource<User>('/auth/me');
  const [active, setActive] = useState<{ ticket: Ticket; url: string } | null>(null);
  const [downloadError, setDownloadError] = useState('');
  const [busyId, setBusyId] = useState('');
  useEffect(
    () => () => {
      if (active) URL.revokeObjectURL(active.url);
    },
    [active],
  );
  async function show(ticket: Ticket) {
    setBusyId(ticket.id);
    setDownloadError('');
    try {
      const link = await api.get<{ qr_image_url: string }>(`/tickets/${ticket.id}/qr`);
      const token = link.data.qr_image_url.match(/^\/api\/download\/([A-Za-z0-9_-]+)$/)?.[1];
      if (!token) throw new Error('No pudimos recuperar un enlace de descarga válido.');
      const response = await api.get<Blob>(`/download/${token}`, { responseType: 'blob' });
      setActive({ ticket, url: URL.createObjectURL(response.data) });
    } catch (failure) {
      if (failure && typeof failure === 'object' && 'response' in failure) {
        const response = (failure as { response?: { data?: Blob } }).response;
        if (response?.data instanceof Blob) {
          try {
            const body = JSON.parse(await response.data.text());
            setDownloadError(
              typeof body.detail === 'string' ? body.detail : 'No pudimos recuperar tu entrada.',
            );
          } catch {
            setDownloadError('No pudimos recuperar tu entrada. Inténtalo otra vez.');
          }
        } else setDownloadError(errorMessage(failure));
      } else setDownloadError(errorMessage(failure));
    } finally {
      setBusyId('');
    }
  }
  return (
    <section aria-labelledby="wallet-title">
      <p className="eyebrow">Tus próximos planes</p>
      <h1 id="wallet-title">Mis compras</h1>
      {typeof profile.data?.rating === 'number' && (
        <p>
          Tu rating: {profile.data.rating.toFixed(2)} / 5
          {profile.data.warning_count ? ` · Advertencias: ${profile.data.warning_count}` : ''}
        </p>
      )}
      <p>Consulta el estado de tus compras y descarga la entrada cuando esté disponible.</p>
      {(error || downloadError) && (
        <p role="alert" className="error-message">
          {error || downloadError}
          {error && (
            <button className="btn btn-secondary" onClick={refresh}>
              Reintentar
            </button>
          )}
        </p>
      )}
      {active && (
        <article className="form-card digital-ticket">
          <h2>{active.ticket.event_name}</h2>
          <p>{active.ticket.zone}</p>
          <img
            className="qr-image"
            src={active.url}
            alt={`Entrada de ${active.ticket.event_name}`}
          />
          <p>Guarda este archivo. El enlace de descarga es de un solo uso.</p>
          <a
            className="btn btn-primary"
            href={active.url}
            download={`tickia-${active.ticket.id}.png`}
          >
            Guardar entrada
          </a>
          <button className="btn btn-secondary" onClick={() => setActive(null)}>
            Cerrar entrada
          </button>
        </article>
      )}
      {loading ? (
        <p role="status">Cargando tus entradas…</p>
      ) : (
        !error && (
          <div className="ticket-grid">
            {!data?.length ? (
              <p className="empty-state">
                Todavía no tienes compras. Explora los eventos para encontrar tu próximo plan.
              </p>
            ) : (
              data.map((ticket) => (
                <article className="form-card" key={ticket.id}>
                  <h2>{ticket.event_name}</h2>
                  <p>
                    {ticket.zone} · {eventDate(ticket.event_date)}
                  </p>
                  <p className="badge">{ticket.estado.replaceAll('_', ' ')}</p>
                  <button
                    className="btn btn-primary full-width"
                    disabled={!!busyId || !['VENDIDA', 'LIBERADA'].includes(ticket.estado)}
                    onClick={() => void show(ticket)}
                  >
                    {busyId === ticket.id
                      ? 'Recuperando entrada…'
                      : ['VENDIDA', 'LIBERADA'].includes(ticket.estado)
                        ? 'Mostrar entrada'
                        : ticket.estado === 'REEMBOLSADA'
                          ? 'Entrada reembolsada'
                          : 'Pendiente de entrega'}
                  </button>
                  <PurchaseActions purchase={ticket} onUpdate={refresh} />
                </article>
              ))
            )}
          </div>
        )
      )}
    </section>
  );
}
