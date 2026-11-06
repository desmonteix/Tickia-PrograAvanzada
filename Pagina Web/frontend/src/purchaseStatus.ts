import type { Purchase } from './types';

export function purchaseStatus(purchase: Purchase): string {
  if (purchase.decision === 'LEGACY_REFUND') return 'Reembolso registrado antes de esta versión';
  if (purchase.decision === 'LEGACY_PAYOUT') return 'Liberación registrada antes de esta versión';
  if (purchase.review_state === 'DISPUTED') return 'Reclamo en investigación · dinero congelado';
  if (purchase.settlement_state === 'SUCCEEDED')
    return purchase.decision === 'VALID_CLAIM'
      ? 'Reembolso confirmado'
      : 'Abono al vendedor confirmado';
  if (purchase.settlement_state === 'UNKNOWN')
    return 'Operación en conciliación · no repitas la solicitud';
  if (purchase.review_state === 'RESOLVED')
    return purchase.decision === 'VALID_CLAIM'
      ? 'Reembolso pendiente de confirmación'
      : 'Abono al vendedor pendiente de confirmación';
  return purchase.delivered_at ? 'Dinero retenido' : 'Pendiente de entrega · dinero retenido';
}
