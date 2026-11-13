import { useState } from 'react';
import type { Referrals } from '../promotions';
import { inviteUrl, percent, validRate } from '../promotions';
import RewardChoice from './RewardChoice';
import { eventDate } from '../types';

const messages = {
  NOT_EARNED: 'Aún no tienes un descuento por referidos.',
  RESERVED:
    'Tu descuento está reservado para una compra en curso. Si el pago es incierto, espera su confirmación.',
  USED: 'Ya usaste tu descuento por referidos. Nuevas invitaciones no generan otro beneficio.',
  REVOKED: 'Este beneficio fue revocado. No está disponible para nuevas operaciones.',
};
export default function ReferralPanel({
  data,
  error,
  refresh,
}: {
  data: Referrals | null;
  error: string;
  refresh: () => void;
}) {
  const [copied, setCopied] = useState('');
  if (!data && !error) return null;
  const url = data ? inviteUrl(window.location.origin, data.referral_code) : '';
  return (
    <aside className="form-card" aria-labelledby="referrals-title">
      <h2 id="referrals-title">Invita y recibe un descuento</h2>
      <p>
        Comparte tu enlace durante una campaña activa. Los beneficios ganados no caducan y no se
        acumulan: cada cuenta puede usar un único beneficio. Tickia financia el descuento de compra.
      </p>
      {data?.campaign?.active && (
        <p>
          Campaña actual: {percent(data.campaign.referral_discount_rate)} % por un registro válido.
          Si la persona invitada publica una entrada válida, puedes obtener{' '}
          {percent(data.campaign.seller_referral_discount_rate)} % para comprar
          {validRate(data.campaign.seller_referral_commission_rate) && (
            <>
              {' '}
              o {percent(data.campaign.seller_referral_commission_rate)} % de comisión Tickia en tu
              próxima venta
            </>
          )}
          .
        </p>
      )}
      {data?.campaign?.active && data.campaign.starts_at && data.campaign.ends_at && (
        <p>
          Campaña desde {eventDate(data.campaign.starts_at)} hasta{' '}
          {eventDate(data.campaign.ends_at)} (final no incluido, hora de Perú).
        </p>
      )}
      {data && (
        <>
          <p>
            {data.reward_status === 'AVAILABLE'
              ? data.choice === 'BUY'
                ? `Tienes un ${percent(data.discount_rate)} % de descuento disponible para tu próxima compra elegible, sin caducidad.`
                : data.choice === 'SELL' && validRate(data.seller_commission_rate)
                  ? `Tu próxima venta elegible tendrá ${percent(data.seller_commission_rate)} % de comisión Tickia. Los cargos de la pasarela siguen a tu cargo.`
                  : 'Tienes un beneficio disponible para elegir entre compra y venta.'
              : messages[data.reward_status]}
          </p>
          {data.pending_upgrade && (
            <p className="notice">
              Hay una mejora pendiente. El pago en curso conserva su precio; si se confirma, consume
              tu beneficio único. Un rechazo definitivo permite aplicar la mejora.
            </p>
          )}
          <RewardChoice reward={data} refresh={refresh} />
          <p>Registros válidos: {data.qualifying_referral_count}.</p>
          <p>Vendedores referidos válidos: {data.qualifying_seller_count ?? 0}.</p>
          {url && (
            <>
              <label htmlFor="referral-link">Tu enlace de invitación</label>
              <input
                id="referral-link"
                className="input-field"
                type="text"
                readOnly
                value={url}
                onFocus={(event) => event.target.select()}
              />
              <p>
                Tu código: <strong>{data.referral_code}</strong>
              </p>
              <button
                className="btn btn-secondary"
                onClick={() => {
                  void navigator.clipboard
                    ?.writeText(url)
                    .then(() => setCopied('Enlace copiado.'))
                    .catch(() => setCopied('Selecciona y copia el enlace del campo.'));
                  if (!navigator.clipboard) setCopied('Selecciona y copia el enlace del campo.');
                }}
              >
                Copiar invitación
              </button>
            </>
          )}
        </>
      )}
      {error && (
        <p className="error-message" role="alert">
          {error}
        </p>
      )}
      {copied && <p role="status">{copied}</p>}
      <button className="btn btn-ghost" onClick={refresh}>
        Actualizar beneficio
      </button>
    </aside>
  );
}
