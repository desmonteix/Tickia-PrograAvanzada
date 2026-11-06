export interface User {
  id: string;
  email: string;
  is_admin: boolean;
  rating?: number;
  warning_count?: number;
}
export interface Ticket {
  id: string;
  price: number;
  estado: string;
  event_name: string;
  event_date: string;
  event_end_date?: string | null;
  seller_rating?: number;
  zone: string;
  ticket_type: 'nominada' | 'no_nominada';
  is_renominated: boolean;
  boosted_until?: string;
  buyer_name?: string;
  buyer_dni?: string;
  download_token?: string;
  download_token_used?: boolean;
}
export interface Purchase extends Ticket {
  purchase_id: string;
  delivered_at: string | null;
  closes_at: string | null;
  review_state: 'HELD' | 'DISPUTED' | 'RESOLVED';
  decision: string | null;
  settlement_state: 'NONE' | 'QUEUED' | 'BLOCKED' | 'PROCESSING' | 'UNKNOWN' | 'SUCCEEDED';
  settlement_error?: string | null;
  can_confirm: boolean;
  can_report: boolean;
}
export const money = (value: number) =>
  new Intl.NumberFormat('es-PE', { style: 'currency', currency: 'PEN' }).format(value);
export const eventDate = (value: string) =>
  new Intl.DateTimeFormat('es-PE', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'America/Lima',
  }).format(new Date(/(Z|[+-]\d{2}:\d{2})$/.test(value) ? value : `${value}Z`));
