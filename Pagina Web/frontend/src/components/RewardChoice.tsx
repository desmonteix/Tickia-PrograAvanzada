import { useState } from 'react';
import api, { errorMessage } from '../api';
import { percent, validRate } from '../promotions';
import type { Referrals } from '../promotions';

export default function RewardChoice({
  reward,
  refresh,
}: {
  reward: Referrals;
  refresh: () => void;
}) {
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState('');
  async function choose(choice: 'BUY' | 'SELL') {
    if (busy) return;
    setBusy(true);
    setError('');
    try {
      await api.post('/referrals/choice', { choice });
      refresh();
    } catch (failure) {
      setError(errorMessage(failure));
      refresh();
    } finally {
      setBusy(false);
    }
  }
  if (reward.reward_status !== 'AVAILABLE')
    return error ? (
      <p role="alert" className="error-message">
        {error}
      </p>
    ) : null;
  return (
    <div aria-busy={busy}>
      <p>
        {reward.choice
          ? 'Puedes cambiar la elección mientras el beneficio siga disponible.'
          : 'Elige cómo usar tu beneficio antes de comprar o vender.'}
      </p>
      <div className="actions">
        <button
          className="btn btn-secondary"
          disabled={busy || reward.choice === 'BUY'}
          onClick={() => void choose('BUY')}
        >
          Usar {percent(reward.discount_rate)} % en mi próxima compra
        </button>
        {validRate(reward.seller_commission_rate) && (
          <button
            className="btn btn-secondary"
            disabled={busy || reward.choice === 'SELL'}
            onClick={() => void choose('SELL')}
          >
            Usar {percent(reward.seller_commission_rate)} % de comisión Tickia en mi próxima venta
          </button>
        )}
      </div>
      {error && (
        <p role="alert" className="error-message">
          {error}
        </p>
      )}
    </div>
  );
}
