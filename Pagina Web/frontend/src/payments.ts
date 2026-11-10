export interface PaymentCapabilities {
  enabled: boolean;
  provider?: 'dlocal_go' | 'culqi';
  payouts_enabled?: boolean;
}
export type PaymentStatus =
  'PROCESSING' | 'UNKNOWN' | 'SUCCEEDED' | 'FAILED' | 'REFUNDED' | 'REFUND_PENDING';
export interface PaymentTransaction {
  transaction_id: string;
  ticket_id: string;
  status: PaymentStatus;
  provider: 'dlocal_go' | 'culqi';
}
export interface FeeTerms {
  payin_percent: string;
  payin_fixed: string;
  payout_percent: string;
  payout_fixed: string;
  tax_rate: string;
  hash: string;
}
export interface PayoutProfile {
  required: boolean;
  status:
    | 'NOT_CONFIGURED'
    | 'CREATING'
    | 'PENDING'
    | 'PROCESSING'
    | 'VERIFIED'
    | 'REJECTED'
    | 'EXPIRED'
    | 'BLOCKED'
    | 'UNKNOWN';
  bank_account_last4: string | null;
  validation_url: string | null;
  can_sell: boolean;
  fee_terms_accepted: boolean;
  fee_terms: FeeTerms | null;
  error: string | null;
}

function externalUrl(value: unknown, hosts: string[]): string | null {
  if (typeof value !== 'string' || /[\s\\]/.test(value)) return null;
  const authority = value.match(/^https:\/\/([^/?#]+)(?:[/?#]|$)/)?.[1];
  // Validate the original authority: URL.port normalizes an explicit :443 away.
  if (!authority || !hosts.includes(authority)) return null;
  try {
    const url = new URL(value);
    return url.protocol === 'https:' &&
      !url.username &&
      !url.password &&
      !url.port &&
      hosts.includes(url.hostname)
      ? url.href
      : null;
  } catch {
    return null;
  }
}
export const safeCheckoutUrl = (value: unknown) =>
  externalUrl(value, ['checkout.dlocalgo.com', 'checkout-sbx.dlocalgo.com']);
export const safeValidationUrl = (value: unknown) => externalUrl(value, ['verify.legaltalent.ai']);

export function paymentTransaction(search: string): string | null {
  const values = new URLSearchParams(search).getAll('payment_transaction');
  return values.length === 1 &&
    /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(values[0])
    ? values[0]
    : null;
}
export function verifyTransaction(value: PaymentTransaction, id: string): PaymentTransaction {
  if (
    !value ||
    value.transaction_id !== id ||
    !['dlocal_go', 'culqi'].includes(value.provider) ||
    !['PROCESSING', 'UNKNOWN', 'SUCCEEDED', 'FAILED', 'REFUNDED', 'REFUND_PENDING'].includes(
      value.status,
    )
  )
    throw new Error('No pudimos verificar el estado de esta operación.');
  return value;
}
function wait(delay: number, signal: AbortSignal): Promise<void> {
  return new Promise((resolve, reject) => {
    const abort = () => {
      clearTimeout(timer);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(() => {
      signal.removeEventListener('abort', abort);
      resolve();
    }, delay);
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
  });
}
export async function watchPayment<T extends { status: string }>(
  load: () => Promise<T>,
  publish: (value: T) => void,
  signal: AbortSignal,
  pause = wait,
) {
  const delays = [0, 1500, 3000, 6000, 10000, 15000];
  for (let attempt = 0; attempt < delays.length; attempt++) {
    if (signal.aborted) return;
    if (delays[attempt]) await pause(delays[attempt], signal);
    if (signal.aborted) return;
    const value = await load();
    if (signal.aborted) return;
    publish(value);
    if (!['PROCESSING', 'UNKNOWN'].includes(value.status)) return;
  }
}

export function payoutPayload(form: FormData, feeTermsHash: string) {
  const text = (name: string) => String(form.get(name) ?? '').trim();
  if (!feeTermsHash || form.get('accept_fees') !== 'on')
    throw new Error('Debes aceptar los costos informados para continuar.');
  const documentType = text('document_type');
  const document = text('document');
  const bankCode = text('bank_code');
  const account = text('account_number');
  if (
    !['DNI', 'RUC'].includes(documentType) ||
    !(documentType === 'DNI' ? /^\d{8}$/ : /^\d{11}$/).test(document)
  )
    throw new Error('Revisa el tipo y número de documento.');
  if (!/^\d{3}$/.test(bankCode) || !/^\d{20}$/.test(account) || account.slice(0, 3) !== bankCode)
    throw new Error('El CCI debe tener 20 dígitos y comenzar con el código del banco.');
  if (!text('first_name') || !text('last_name'))
    throw new Error('Completa tus nombres y apellidos.');
  const accountType = text('account_type');
  if (!['SAVINGS', 'CHECKING'].includes(accountType))
    throw new Error('Selecciona el tipo de cuenta.');
  return {
    first_name: text('first_name'),
    last_name: text('last_name'),
    document_type: documentType,
    document,
    bank_code: bankCode,
    account_number: account,
    account_type: accountType,
    ...(text('bank_branch') ? { bank_branch: text('bank_branch') } : {}),
    accept_fees: true,
    fee_terms_hash: feeTermsHash,
  };
}
export function settlementLabel(state?: string | null, decision?: string | null): string {
  if (decision === 'LEGACY_PAYOUT') return 'Liberación registrada en una versión anterior.';
  if (decision === 'LEGACY_REFUND') return 'Reembolso registrado en una versión anterior.';
  const labels: Record<string, string> = {
    NONE: 'En revisión; abono aún no solicitado.',
    QUEUED: 'Abono o devolución pendiente de ejecución.',
    BLOCKED: 'Operación pendiente: requiere revisión.',
    PROCESSING: 'Operación financiera en proceso.',
    UNKNOWN: 'Estamos verificando la operación financiera.',
    SUCCEEDED: 'Operación financiera confirmada.',
  };
  return labels[state ?? ''] ?? 'Consulta el estado de la liquidación.';
}
