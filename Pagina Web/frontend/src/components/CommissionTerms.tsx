import { percent, validRate } from '../promotions';
import type { Campaign } from '../promotions';
export default function CommissionTerms({ campaign }: { campaign?: Campaign | null }) {
  return (
    <p className="notice">
      {validRate(campaign?.current_commission_rate)
        ? `Comisión Tickia para nuevas publicaciones: ${percent(campaign.current_commission_rate)} % con IGV incluido. La tasa de publicación se conserva al vender después.`
        : 'Consulta la comisión Tickia en la cotización antes de publicar.'}{' '}
      Un beneficio elegido para vender se aplica a la próxima venta elegible, sin eliminar los
      cargos de la pasarela. El comprador no paga sobrecostos.
    </p>
  );
}
