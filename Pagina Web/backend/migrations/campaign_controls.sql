-- Apply AFTER launch_promotions.sql, with a verified backup and staging rehearsal.
-- Additive and repeatable. Campaign deletion is archival, never deletion of grants.
BEGIN;
CREATE TABLE IF NOT EXISTS promotion_campaigns (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    name VARCHAR(120) NOT NULL,
    starts_at TIMESTAMPTZ NOT NULL,
    ends_at TIMESTAMPTZ NOT NULL,
    enabled BOOLEAN NOT NULL DEFAULT TRUE,
    archived BOOLEAN NOT NULL DEFAULT FALSE,
    listing_commission_rate NUMERIC(5,4) NOT NULL,
    registration_discount_rate NUMERIC(5,4) NOT NULL,
    seller_buyer_discount_rate NUMERIC(5,4) NOT NULL,
    seller_commission_rate NUMERIC(5,4) NOT NULL,
    CONSTRAINT chk_campaign_dates CHECK (ends_at > starts_at),
    CONSTRAINT chk_campaign_rates CHECK (
        listing_commission_rate >= 0 AND listing_commission_rate < 1 AND
        registration_discount_rate >= 0 AND registration_discount_rate <= 0.5 AND
        seller_buyer_discount_rate >= 0 AND seller_buyer_discount_rate <= 0.5 AND
        seller_commission_rate >= 0 AND seller_commission_rate < 1)
);
CREATE TABLE IF NOT EXISTS site_settings (
    id INTEGER PRIMARY KEY DEFAULT 1,
    registrations_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    publications_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    purchases_enabled BOOLEAN NOT NULL DEFAULT TRUE,
    maintenance_mode BOOLEAN NOT NULL DEFAULT FALSE,
    announcement VARCHAR(500) NOT NULL DEFAULT '',
    CONSTRAINT chk_settings_singleton CHECK (id = 1)
);
-- Explicit values also support tables previously created by the ORM, whose
-- client-side defaults are not PostgreSQL DEFAULT expressions.
INSERT INTO site_settings(id,registrations_enabled,publications_enabled,purchases_enabled,maintenance_mode,announcement)
VALUES(1,TRUE,TRUE,TRUE,FALSE,'') ON CONFLICT DO NOTHING;
INSERT INTO promotion_campaigns(id,name,starts_at,ends_at,enabled,archived,listing_commission_rate,
    registration_discount_rate,seller_buyer_discount_rate,seller_commission_rate)
VALUES('aa000000-0000-4000-8000-000000000001','Lanzamiento Tickia 2026',
    '2026-11-13T00:00:00-05:00','2026-12-13T00:00:00-05:00',TRUE,FALSE,0.05,0.05,0.10,0)
ON CONFLICT DO NOTHING; -- Never re-enable or overwrite a campaign edited by an admin.

ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_discount_rate NUMERIC(5,4);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_commission_rate NUMERIC(5,4);
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS reservation_seller_reward_id UUID REFERENCES users(id);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS buyer_discount_rate NUMERIC(5,4) NOT NULL DEFAULT 0;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS seller_referral_reward_user_id UUID REFERENCES users(id);
-- Backfill ONLY the previous release's 5% quotes. New snapshots remain untouched.
UPDATE tickets SET reservation_discount_rate = CASE WHEN reservation_discount > 0 THEN 0.05 ELSE 0 END,
    reservation_commission_rate = commission_rate
WHERE reservation_id IS NOT NULL AND reservation_discount_rate IS NULL;
UPDATE transactions SET buyer_discount_rate = 0.05
WHERE listed_amount IS NOT NULL AND buyer_discount > 0 AND buyer_discount_rate = 0;
ALTER TABLE tickets DROP CONSTRAINT IF EXISTS chk_ticket_commission_rate;
ALTER TABLE tickets ADD CONSTRAINT chk_ticket_commission_rate CHECK (commission_rate >= 0 AND commission_rate <= 1);
ALTER TABLE transactions DROP CONSTRAINT IF EXISTS chk_transaction_promotion_amounts;
ALTER TABLE transactions ADD CONSTRAINT chk_transaction_promotion_amounts CHECK (
    buyer_discount >= 0 AND ((listed_amount IS NULL AND buyer_discount = 0) OR
    (listed_amount IS NOT NULL AND commission_rate IS NOT NULL AND commission_rate >= 0 AND commission_rate <= 1
    AND round(listed_amount * 100,0) = round(amount_total * 100,0) + round(buyer_discount * 100,0)
    AND round(listed_amount * 100,0) = round(commission_platform * 100,0) + round(amount_seller * 100,0)
    AND round(commission_platform * 100,0) = round(listed_amount * commission_rate * 100,0)
    AND buyer_discount_rate >= 0 AND buyer_discount_rate < 1
    AND round(buyer_discount * 100,0) = round(listed_amount * buyer_discount_rate * 100,0))));

ALTER TABLE referrals ADD COLUMN IF NOT EXISTS seller_qualified_at TIMESTAMPTZ;
ALTER TABLE referrals ADD COLUMN IF NOT EXISTS seller_ticket_id UUID REFERENCES tickets(id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_referral_seller_ticket ON referrals(seller_ticket_id);
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS campaign_id UUID;
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS reward_kind VARCHAR NOT NULL DEFAULT 'REGISTRATION';
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS buyer_discount_rate NUMERIC(5,4) NOT NULL DEFAULT 0.05;
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS seller_commission_rate NUMERIC(5,4);
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS choice VARCHAR DEFAULT 'BUY';
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS pending_upgrade TEXT;
ALTER TABLE referral_rewards ADD COLUMN IF NOT EXISTS revoked_at TIMESTAMPTZ;
-- Two DIFFERENT users may use buyer and seller benefits on the same transaction.
-- The user PK still enforces one lifetime reward per person.
DO $$
DECLARE constraint_row RECORD;
BEGIN
    FOR constraint_row IN
        SELECT c.conname FROM pg_constraint c JOIN pg_attribute a
        ON a.attrelid=c.conrelid AND a.attnum=c.conkey[1]
        WHERE c.conrelid='referral_rewards'::regclass AND c.contype='u'
        AND cardinality(c.conkey)=1 AND a.attname IN ('reserved_ticket_id','reserved_transaction_id','used_transaction_id')
    LOOP
        EXECUTE format('ALTER TABLE referral_rewards DROP CONSTRAINT %I', constraint_row.conname);
    END LOOP;
    IF NOT EXISTS (SELECT 1 FROM pg_constraint WHERE conrelid='referral_rewards'::regclass AND conname='chk_reward_rates') THEN
        ALTER TABLE referral_rewards ADD CONSTRAINT chk_reward_rates CHECK (
            buyer_discount_rate >= 0 AND buyer_discount_rate < 1 AND
            (seller_commission_rate IS NULL OR (seller_commission_rate >= 0 AND seller_commission_rate <= 1)));
        ALTER TABLE referral_rewards ADD CONSTRAINT chk_reward_choice CHECK (choice IS NULL OR choice IN ('BUY','SELL'));
    END IF;
END $$;
CREATE INDEX IF NOT EXISTS ix_referral_rewards_reserved_ticket_id ON referral_rewards(reserved_ticket_id);
CREATE INDEX IF NOT EXISTS ix_referral_rewards_reserved_transaction_id ON referral_rewards(reserved_transaction_id);
ALTER TABLE promotion_campaigns ENABLE ROW LEVEL SECURITY;
ALTER TABLE site_settings ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE promotion_campaigns,site_settings FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='anon') THEN
        REVOKE ALL ON TABLE promotion_campaigns,site_settings FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname='authenticated') THEN
        REVOKE ALL ON TABLE promotion_campaigns,site_settings FROM authenticated;
    END IF;
END $$;
COMMIT;
