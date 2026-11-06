-- Tickia production readiness. Run in staging first, with a verified backup.
-- Transactional and repeatable. Duplicates make index creation fail: investigate
-- them instead of discarding data. Existing numeric values round to cents.
BEGIN;

ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_token_hash VARCHAR;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS provider_fee NUMERIC(12,2);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS seller_net_amount NUMERIC(12,2);
CREATE UNIQUE INDEX IF NOT EXISTS uq_payment_token_hash
    ON transactions (payment_token_hash) WHERE payment_token_hash IS NOT NULL;
CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_active_qr
    ON tickets (qr_hash_sha256) WHERE hash_estado = 'ACTIVO';
CREATE UNIQUE INDEX IF NOT EXISTS uq_ticket_settlement
    ON transactions (ticket_id)
    WHERE status IN ('PROCESSING','UNKNOWN','SUCCEEDED','REFUND_PENDING','REFUNDED');
CREATE UNIQUE INDEX IF NOT EXISTS uq_transaction_culqi_charge_id_index
    ON transactions (culqi_charge_id) WHERE culqi_charge_id IS NOT NULL;

ALTER TABLE tickets ALTER COLUMN price TYPE NUMERIC(12,2) USING ROUND(price::numeric,2);
ALTER TABLE transactions ALTER COLUMN amount_total TYPE NUMERIC(12,2) USING ROUND(amount_total::numeric,2);
ALTER TABLE transactions ALTER COLUMN commission_platform TYPE NUMERIC(12,2) USING ROUND(commission_platform::numeric,2);
ALTER TABLE transactions ALTER COLUMN amount_seller TYPE NUMERIC(12,2) USING ROUND(amount_seller::numeric,2);

-- Existing event dates were generated on upload: verify/correct them with each
-- seller before listing. Do not guess event dates or silently reinterpret them.
-- Access and referral columns remain for compatibility; the API has no waitlist.
UPDATE users SET has_access = TRUE;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ticket_price_minimum_3' AND conrelid = 'tickets'::regclass) THEN
        ALTER TABLE tickets ADD CONSTRAINT chk_ticket_price_minimum_3 CHECK (price >= 3 AND price <= 5000);
    END IF;
END $$;

COMMIT;
