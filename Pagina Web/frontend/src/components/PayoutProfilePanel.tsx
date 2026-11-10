import { useState } from 'react';
import type { FormEvent } from 'react';
import api, { errorMessage } from '../api';
import { payoutPayload, safeValidationUrl } from '../payments';
import type { PayoutProfile } from '../payments';
import { money } from '../types';
import './PaymentForms.css';

const statusText: Record<PayoutProfile['status'], string> = {
  NOT_CONFIGURED: 'Completa tus datos y cuenta bancaria para vender.',
  CREATING: 'Estamos creando tu perfil. Consulta su estado antes de reenviar datos.',
  PENDING: 'Tu identidad está pendiente de verificación.',
  PROCESSING: 'El proveedor está revisando tu identidad.',
  VERIFIED: 'El proveedor verificó tu identidad.',
  REJECTED: 'La verificación fue rechazada. Revisa las indicaciones del proveedor.',
  EXPIRED: 'La verificación venció. Consulta las opciones de verificación disponibles.',
  BLOCKED: 'El proveedor bloqueó este perfil. Solicita atención.',
  UNKNOWN: 'Estamos comprobando el registro. No vuelvas a enviar el formulario.',
};

export default function PayoutProfilePanel({
  profile,
  loading,
  error,
  refresh,
}: {
  profile: PayoutProfile | null;
  loading: boolean;
  error: string;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [failure, setFailure] = useState('');
  const [submitted, setSubmitted] = useState(false);
  const [accepted, setAccepted] = useState(false);
  async function create(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (busy || submitted || !profile?.fee_terms) return;
    setFailure('');
    let payload;
    try {
      payload = payoutPayload(new FormData(event.currentTarget), profile.fee_terms.hash);
    } catch (err) {
      setFailure(errorMessage(err));
      return;
    }
    setBusy(true);
    setSubmitted(true);
    try {
      await api.post('/payments/payout-profile', payload);
      refresh();
    } catch (err) {
      const status = (err as { response?: { status?: number } }).response?.status;
      if (status && status < 500) setSubmitted(false);
      if (status === 409) refresh();
      setFailure(errorMessage(err));
    } finally {
      setBusy(false);
    }
  }
  async function acceptFees() {
    if (!accepted || busy || !profile?.fee_terms) return;
    setBusy(true);
    setFailure('');
    try {
      await api.post('/payments/payout-profile/accept-fees', {
        accept_fees: true,
        fee_terms_hash: profile.fee_terms.hash,
      });
      refresh();
    } catch (err) {
      setFailure(errorMessage(err));
      setAccepted(false);
      if ((err as { response?: { status?: number } }).response?.status === 409) refresh();
    } finally {
      setBusy(false);
    }
  }
  if (!loading && !error && profile && !profile.required) return null;
  const validation = safeValidationUrl(profile?.validation_url);
  const terms = profile?.fee_terms;
  return (
    <article
      className="form-card medium"
      aria-labelledby="payout-profile-title"
      aria-busy={loading || busy}
    >
      <h2 id="payout-profile-title">Identidad y cuenta para recibir abonos</h2>
      {loading && <p role="status">Consultando tu perfil de vendedor…</p>}
      {(error || failure) && (
        <p role="alert" className="error-message">
          {error || failure}
        </p>
      )}
      {profile && (
        <>
          <p role="status">{statusText[profile.status]}</p>
          {profile.bank_account_last4 && (
            <p>Cuenta registrada terminada en {profile.bank_account_last4}.</p>
          )}
          {profile.error && <p className="error-message">{profile.error}</p>}
          <p>
            El abono se tramita después de la confirmación del comprador o del cierre a las 24 horas
            del final del evento, con entrega y sin reclamos abiertos. Requiere saldo disponible y
            confirmación del proveedor; no es instantáneo.
          </p>
          {terms ? (
            <div className="notice">
              <p>
                Comisión Tickia: 10 % del precio, con IGV incluido. Todos los cargos son del
                vendedor; el comprador paga el precio publicado.
              </p>
              <p>
                Procesamiento: {terms.payin_percent} % + {money(Number(terms.payin_fixed))}.
                Desembolso: {terms.payout_percent} % + {money(Number(terms.payout_fixed))}.
              </p>
              <p>
                {Number(terms.tax_rate) > 0
                  ? `A los cargos del proveedor se añade ${terms.tax_rate} % de impuesto.`
                  : 'Los cargos del proveedor no añaden un impuesto adicional a lo informado.'}{' '}
                El neto final se confirma al conciliar los cargos.
              </p>
            </div>
          ) : (
            <p className="notice">
              Los costos del proveedor todavía no están configurados. No puedes completar la
              aceptación ni publicar hasta que se informen.
            </p>
          )}
          {validation && (
            <a
              className="btn btn-primary"
              href={validation}
              target="_blank"
              rel="noopener noreferrer"
            >
              Verificar mi identidad
            </a>
          )}
          {profile.validation_url && !validation && (
            <p role="alert" className="error-message">
              El enlace de verificación no coincide con el proveedor autorizado. Solicita atención.
            </p>
          )}
          {profile.status === 'NOT_CONFIGURED' && !submitted && terms && (
            <form onSubmit={(event) => void create(event)}>
              <fieldset className="payment-fields" disabled={busy || loading || !!error}>
                <legend>Datos del titular de la cuenta</legend>
                <div className="form-row">
                  <div className="input-group">
                    <label htmlFor="payout-first-name">Nombres</label>
                    <input
                      id="payout-first-name"
                      name="first_name"
                      className="input-field"
                      required
                      maxLength={100}
                      autoComplete="given-name"
                    />
                  </div>
                  <div className="input-group">
                    <label htmlFor="payout-last-name">Apellidos</label>
                    <input
                      id="payout-last-name"
                      name="last_name"
                      className="input-field"
                      required
                      maxLength={100}
                      autoComplete="family-name"
                    />
                  </div>
                </div>
                <div className="form-row">
                  <div className="input-group">
                    <label htmlFor="payout-document-type">Tipo de documento</label>
                    <select id="payout-document-type" name="document_type" className="input-field">
                      <option value="DNI">DNI</option>
                      <option value="RUC">RUC</option>
                    </select>
                  </div>
                  <div className="input-group">
                    <label htmlFor="payout-document">Número de documento</label>
                    <input
                      id="payout-document"
                      name="document"
                      className="input-field"
                      required
                      inputMode="numeric"
                      pattern="[0-9]{8}|[0-9]{11}"
                      maxLength={11}
                    />
                  </div>
                </div>
                <div className="input-group">
                  <label htmlFor="payout-bank-code">Código del banco (3 dígitos)</label>
                  <input
                    id="payout-bank-code"
                    name="bank_code"
                    className="input-field"
                    required
                    inputMode="numeric"
                    pattern="[0-9]{3}"
                    maxLength={3}
                  />
                  <small>Usa los primeros tres dígitos de tu CCI.</small>
                </div>
                <div className="input-group">
                  <label htmlFor="payout-account">CCI de tu cuenta en soles (20 dígitos)</label>
                  <input
                    id="payout-account"
                    name="account_number"
                    className="input-field"
                    required
                    inputMode="numeric"
                    pattern="[0-9]{20}"
                    maxLength={20}
                  />
                  <small>La cuenta debe corresponder al titular del documento.</small>
                </div>
                <div className="input-group">
                  <label htmlFor="payout-account-type">Tipo de cuenta</label>
                  <select id="payout-account-type" name="account_type" className="input-field">
                    <option value="SAVINGS">Ahorros</option>
                    <option value="CHECKING">Corriente</option>
                  </select>
                </div>
                <div className="input-group">
                  <label htmlFor="payout-branch">Código de agencia (solo si te lo indicaron)</label>
                  <input
                    id="payout-branch"
                    name="bank_branch"
                    className="input-field"
                    maxLength={20}
                  />
                </div>
                <label className="checkbox-label">
                  <input type="checkbox" name="accept_fees" required /> Acepto la comisión y los
                  cargos del proveedor informados arriba, a mi cargo como vendedor.
                </label>
                <button type="submit" className="btn btn-primary" disabled={busy}>
                  {busy ? 'Registrando…' : 'Registrar cuenta y comenzar verificación'}
                </button>
              </fieldset>
            </form>
          )}
          {submitted && profile.status === 'NOT_CONFIGURED' && (
            <p role="status">
              Solicitud enviada o pendiente de comprobación. Consulta el estado antes de volver a
              registrarte.
            </p>
          )}
          {profile.status !== 'NOT_CONFIGURED' && !profile.fee_terms_accepted && terms && (
            <div className="input-group">
              <label className="checkbox-label">
                <input
                  type="checkbox"
                  checked={accepted}
                  onChange={(event) => setAccepted(event.target.checked)}
                  disabled={busy}
                />{' '}
                Acepto los costos actuales informados arriba.
              </label>
              <button
                className="btn btn-primary"
                disabled={!accepted || busy || loading}
                onClick={() => void acceptFees()}
              >
                Confirmar costos actuales
              </button>
            </div>
          )}
          {!profile.can_sell && (
            <p className="muted">
              La publicación se habilitará cuando el proveedor confirme la verificación y los costos
              estén aceptados. El cambio de cuenta bancaria requiere atención; esta pantalla solo
              permite el registro inicial.
            </p>
          )}
        </>
      )}
      <button className="btn btn-secondary" disabled={busy || loading} onClick={refresh}>
        Consultar verificación
      </button>
    </article>
  );
}
