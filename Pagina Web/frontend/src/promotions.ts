export interface Campaign {
  starts_at: string | null;
  ends_at: string | null;
  timezone: string;
  active: boolean;
  current_commission_rate: number;
  regular_commission_rate: number;
  launch_commission_rate: number | null;
  referral_discount_rate: number;
  seller_referral_discount_rate: number;
  seller_referral_commission_rate: number | null;
  settings: OperationSettings;
  referral_reward_expires: false;
}
export interface Referrals {
  referral_code: string;
  invite_path: string;
  qualifying_referral_count: number;
  reward_status: 'NOT_EARNED' | 'AVAILABLE' | 'RESERVED' | 'USED' | 'REVOKED';
  discount_rate: number;
  reward_kind: 'REGISTRATION' | 'SELLER_REFERRAL' | 'MANUAL' | null;
  choice: 'BUY' | 'SELL' | null;
  seller_commission_rate: number | null;
  qualifying_seller_count: number;
  pending_upgrade: boolean;
  reserved_ticket_id: string | null;
  reserved_until: string | null;
  campaign: Campaign;
}
export interface ReservationQuote {
  reservation_id: string;
  listed_amount: number;
  buyer_discount: number;
  buyer_discount_rate: number;
  amount_total: number;
  amount_total_cents: number;
  commission_rate: number;
  reserved_until: string;
}
export interface OperationSettings {
  registrations_enabled: boolean;
  publications_enabled: boolean;
  purchases_enabled: boolean;
  maintenance_mode: boolean;
  announcement: string;
}
export const validRate = (value: unknown): value is number =>
  typeof value === 'number' && Number.isFinite(value) && value >= 0 && value < 1;
export const percent = (rate: number) =>
  new Intl.NumberFormat('es-PE', { maximumFractionDigits: 2 }).format(rate * 100);
export function operationAllowed(
  settings: OperationSettings | undefined,
  operation: 'registrations' | 'publications' | 'purchases',
) {
  return !settings?.maintenance_mode && settings?.[`${operation}_enabled`] !== false;
}
function discountedCents(amount: number, rate: number) {
  // API rates have at most four decimals; integer arithmetic preserves HALF_UP.
  const units = Math.round(rate * 10000);
  return Math.floor((amount * units + 5000) / 10000);
}
const KEY = 'tickia:referral-code';
export const referralCode = (value: unknown): string =>
  typeof value === 'string' && /^[A-Za-z0-9_-]{6,64}$/.test(value) ? value : '';
export function rememberReferral(
  search: string,
  storage: Pick<Storage, 'getItem' | 'setItem'>,
): string {
  let saved = '';
  try {
    saved = referralCode(storage.getItem(KEY));
  } catch {
    /* Storage may be disabled. */
  }
  const values = new URLSearchParams(search).getAll('ref');
  const code = saved || (values.length === 1 ? referralCode(values[0]) : '');
  if (code)
    try {
      storage.setItem(KEY, code);
    } catch {
      /* Keep attribution in memory. */
    }
  return code;
}
export function clearReferral(storage: Pick<Storage, 'removeItem'>) {
  try {
    storage.removeItem(KEY);
  } catch {
    /* Registration already committed. */
  }
}
export function previewAmount(
  price: number,
  reward: Pick<Referrals, 'reward_status' | 'discount_rate' | 'choice'> | null,
): number {
  const cents = Math.round(price * 100);
  return (
    cents -
    (reward?.reward_status === 'AVAILABLE' &&
    reward.choice === 'BUY' &&
    validRate(reward.discount_rate)
      ? discountedCents(cents, reward.discount_rate)
      : 0)
  );
}
function cents(value: unknown): number {
  if (
    typeof value !== 'number' ||
    !Number.isFinite(value) ||
    value < 0 ||
    Math.abs(value * 100 - Math.round(value * 100)) > 0.000001
  )
    throw new Error('No pudimos verificar el importe de la reserva.');
  return Math.round(value * 100);
}
export function verifyQuote(value: ReservationQuote, price: number): ReservationQuote {
  if (
    !value ||
    !/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(value.reservation_id) ||
    !validRate(value.commission_rate) ||
    !validRate(value.buyer_discount_rate)
  )
    throw new Error('No pudimos verificar la reserva. Actualiza el catálogo.');
  const listed = cents(value.listed_amount),
    discount = cents(value.buyer_discount),
    total = cents(value.amount_total);
  if (
    listed !== cents(price) ||
    total <= 0 ||
    listed - discount !== total ||
    !Number.isSafeInteger(value.amount_total_cents) ||
    value.amount_total_cents !== total ||
    discount !== discountedCents(listed, value.buyer_discount_rate)
  )
    throw new Error(
      'La cotización cambió o no coincide con el precio. Actualiza el catálogo antes de comprar.',
    );
  return value;
}
export function inviteUrl(origin: string, code: string): string {
  if (!referralCode(code)) return '';
  const url = new URL('/', origin);
  url.searchParams.set('ref', code);
  url.hash = 'login';
  return url.href;
}
export function reservationReleased(failure: unknown): boolean {
  if (!failure || typeof failure !== 'object') return false;
  const response = (
    failure as { response?: { status?: number; data?: { reservation_released?: unknown } } }
  ).response;
  return response?.status === 402 && response.data?.reservation_released === true;
}
