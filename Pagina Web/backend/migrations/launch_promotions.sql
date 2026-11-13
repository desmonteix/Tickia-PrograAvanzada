-- Repeatable, additive PostgreSQL migration. Apply after dlocal_go.sql.
-- Back up and validate in staging before deploying the matching application.
BEGIN;

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(5,4);
-- Only initial backfill. Reapplying never changes a stored ticket commission.
UPDATE tickets SET commission_rate = CASE
    WHEN created_at >= TIMESTAMPTZ '2026-11-13 05:00:00+00'
     AND created_at < TIMESTAMPTZ '2026-12-13 05:00:00+00' THEN 0.05
    ELSE 0.10 END
WHERE commission_rate IS NULL;
ALTER TABLE tickets ALTER COLUMN commission_rate SET DEFAULT 0.10;
ALTER TABLE tickets ALTER COLUMN commission_rate SET NOT NULL;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_id UUID;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_total NUMERIC(12,2);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_discount NUMERIC(12,2);

-- NULL listed_amount/rate deliberately identifies historical operations.
-- Existing fees, seller amounts, financial results and statuses are untouched.
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS listed_amount NUMERIC(12,2);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS buyer_discount NUMERIC(12,2) NOT NULL DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS commission_rate NUMERIC(5,4);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS referral_reward_user_id UUID REFERENCES users(id);

CREATE TABLE IF NOT EXISTS referrals (
    referred_user_id UUID PRIMARY KEY REFERENCES users(id),
    referrer_id UUID NOT NULL REFERENCES users(id),
    qualified BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_referral_not_self CHECK (referrer_id != referred_user_id)
);
CREATE INDEX IF NOT EXISTS ix_referrals_referrer_id ON referrals(referrer_id);
CREATE TABLE IF NOT EXISTS referral_rewards (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    earned_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    reserved_ticket_id UUID UNIQUE REFERENCES tickets(id),
    reserved_until TIMESTAMPTZ,
    reserved_transaction_id UUID UNIQUE REFERENCES transactions(id),
    used_transaction_id UUID UNIQUE REFERENCES transactions(id),
    used_at TIMESTAMPTZ,
    CONSTRAINT chk_reward_used CHECK (
        (used_transaction_id IS NULL AND used_at IS NULL) OR
        (used_transaction_id IS NOT NULL AND used_at IS NOT NULL
         AND reserved_ticket_id IS NULL AND reserved_transaction_id IS NULL AND reserved_until IS NULL)
    ),
    CONSTRAINT chk_reward_transaction CHECK (reserved_transaction_id IS NULL OR reserved_ticket_id IS NOT NULL),
    CONSTRAINT chk_reward_empty_hold CHECK (reserved_ticket_id IS NOT NULL OR
        (reserved_transaction_id IS NULL AND reserved_until IS NULL)),
    CONSTRAINT chk_reward_hold_expiry CHECK (reserved_ticket_id IS NULL OR
        reserved_transaction_id IS NOT NULL OR reserved_until IS NOT NULL)
);
-- Do not manufacture rewards from the old waitlist/referral_count fields.

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ticket_commission_rate' AND conrelid = 'tickets'::regclass) THEN
        ALTER TABLE tickets ADD CONSTRAINT chk_ticket_commission_rate CHECK (commission_rate IN (0.05,0.10));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_ticket_quote' AND conrelid = 'tickets'::regclass) THEN
        ALTER TABLE tickets ADD CONSTRAINT chk_ticket_quote CHECK (
            (reservation_id IS NULL AND reservation_total IS NULL AND reservation_discount IS NULL) OR
            (reservation_id IS NOT NULL AND reservation_total IS NOT NULL AND reservation_discount IS NOT NULL
             AND reservation_total > 0 AND reservation_discount >= 0
             AND round(reservation_total * 100,0) + round(reservation_discount * 100,0) = round(price * 100,0)));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_transaction_promotion_amounts' AND conrelid = 'transactions'::regclass) THEN
        ALTER TABLE transactions ADD CONSTRAINT chk_transaction_promotion_amounts CHECK (
            buyer_discount >= 0 AND ((listed_amount IS NULL AND buyer_discount = 0) OR
            (listed_amount IS NOT NULL AND commission_rate IS NOT NULL AND commission_rate IN (0.05,0.10)
             AND round(listed_amount * 100,0) = round(amount_total * 100,0) + round(buyer_discount * 100,0)
             AND round(listed_amount * 100,0) = round(commission_platform * 100,0) + round(amount_seller * 100,0)
             AND round(commission_platform * 100,0) = round(listed_amount * commission_rate * 100,0)
             AND (buyer_discount = 0 OR round(buyer_discount * 100,0) = round(listed_amount * 0.05 * 100,0)))));
    END IF;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conname = 'chk_transaction_reward_owner' AND conrelid = 'transactions'::regclass) THEN
        ALTER TABLE transactions ADD CONSTRAINT chk_transaction_reward_owner CHECK (
            (buyer_discount = 0 AND referral_reward_user_id IS NULL) OR
            (buyer_discount > 0 AND referral_reward_user_id IS NOT NULL AND referral_reward_user_id = buyer_id));
    END IF;
END $$;

ALTER TABLE referrals ENABLE ROW LEVEL SECURITY;
ALTER TABLE referral_rewards ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE referrals, referral_rewards FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE referrals, referral_rewards FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE referrals, referral_rewards FROM authenticated;
    END IF;
END $$;
COMMIT;
