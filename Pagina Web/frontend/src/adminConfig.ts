export interface CampaignConfig {
  id: string;
  name: string;
  starts_at: string;
  ends_at: string;
  enabled: boolean;
  archived: boolean;
  listing_commission_rate: number;
  registration_discount_rate: number;
  seller_buyer_discount_rate: number;
  seller_commission_rate: number;
}
export const text = (form: FormData, key: string) => String(form.get(key) ?? '').trim();
export function mutationReason(form: FormData) {
  const reason = text(form, 'reason');
  if (reason.length < 8 || reason.length > 500)
    throw new Error('Indica un motivo de entre 8 y 500 caracteres.');
  return reason;
}
function rate(form: FormData, key: string, max = 100) {
  const raw = text(form, key);
  if (!/^\d{1,3}(?:\.\d{1,2})?$/.test(raw))
    throw new Error('Revisa los porcentajes: usa hasta dos decimales.');
  const value = Number(raw);
  if (value < 0 || value > max || value >= 100)
    throw new Error('El porcentaje está fuera del rango permitido.');
  return value / 100;
}
function date(form: FormData, key: string) {
  const raw = text(form, key);
  if (
    !/^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}$/.test(raw) ||
    !Number.isFinite(Date.parse(raw + ':00-05:00'))
  )
    throw new Error('Completa las fechas y horas de Perú.');
  return raw + ':00-05:00';
}
export function peruInput(value: string) {
  const parts = new Intl.DateTimeFormat('en-CA', {
    timeZone: 'America/Lima',
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
  }).formatToParts(new Date(value));
  const part = (type: string) => parts.find((x) => x.type === type)?.value;
  return `${part('year')}-${part('month')}-${part('day')}T${part('hour')}:${part('minute')}`;
}
export function campaignPayload(form: FormData) {
  const name = text(form, 'name');
  if (name.length < 3 || name.length > 120)
    throw new Error('El nombre debe tener entre 3 y 120 caracteres.');
  const starts_at = date(form, 'starts_at'),
    ends_at = date(form, 'ends_at');
  if (Date.parse(ends_at) <= Date.parse(starts_at))
    throw new Error('El final debe ser posterior al inicio.');
  return {
    name,
    starts_at,
    ends_at,
    enabled: form.get('enabled') === 'on',
    listing_commission_rate: rate(form, 'listing_commission_rate'),
    registration_discount_rate: rate(form, 'registration_discount_rate', 50),
    seller_buyer_discount_rate: rate(form, 'seller_buyer_discount_rate', 50),
    seller_commission_rate: rate(form, 'seller_commission_rate'),
    reason: mutationReason(form),
  };
}
export function rewardPayload(form: FormData) {
  const user_id = text(form, 'user_id');
  if (!/^[0-9a-f]{8}(?:-[0-9a-f]{4}){3}-[0-9a-f]{12}$/i.test(user_id))
    throw new Error('Selecciona un usuario registrado.');
  return {
    user_id,
    buyer_discount_rate: rate(form, 'buyer_discount_rate', 50),
    seller_commission_rate: text(form, 'seller_commission_rate')
      ? rate(form, 'seller_commission_rate')
      : null,
    reason: mutationReason(form),
  };
}
export function settingsPayload(form: FormData) {
  const announcement = text(form, 'announcement');
  if (announcement.length > 500) throw new Error('El aviso admite hasta 500 caracteres.');
  return {
    registrations_enabled: form.get('registrations_enabled') === 'on',
    publications_enabled: form.get('publications_enabled') === 'on',
    purchases_enabled: form.get('purchases_enabled') === 'on',
    maintenance_mode: form.get('maintenance_mode') === 'on',
    announcement,
    reason: mutationReason(form),
  };
}
