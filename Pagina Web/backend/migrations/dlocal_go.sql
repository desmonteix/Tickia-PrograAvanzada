-- Additive, repeatable PostgreSQL migration. Apply after purchase_reviews.sql.
-- Take a verified backup and apply in staging before deploying the new code.
BEGIN;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payment_provider VARCHAR NOT NULL DEFAULT 'culqi';
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS provider_payment_id VARCHAR;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS checkout_url TEXT;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS approved_at TIMESTAMPTZ;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS available_after TIMESTAMPTZ;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payin_fee NUMERIC(12,2);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payout_fee NUMERIC(12,2);
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS fee_terms_hash VARCHAR;
ALTER TABLE transactions ADD COLUMN IF NOT EXISTS payout_terms TEXT;
CREATE UNIQUE INDEX IF NOT EXISTS uq_transaction_provider_payment
    ON transactions(payment_provider, provider_payment_id);
ALTER TABLE purchase_reviews ADD COLUMN IF NOT EXISTS settlement_check_at TIMESTAMPTZ;
CREATE TABLE IF NOT EXISTS payout_profiles (
    user_id UUID PRIMARY KEY REFERENCES users(id),
    beneficiary_id VARCHAR UNIQUE,
    bank_account_id INTEGER UNIQUE,
    status VARCHAR NOT NULL DEFAULT 'CREATING',
    account_last4 VARCHAR(4) NOT NULL,
    identity_hash VARCHAR(64) NOT NULL UNIQUE,
    account_hash VARCHAR(64) NOT NULL,
    request_encrypted TEXT,
    fee_terms_hash VARCHAR(64) NOT NULL,
    error VARCHAR,
    updated_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE TABLE IF NOT EXISTS financial_operations (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES purchase_reviews(id),
    kind VARCHAR NOT NULL,
    amount NUMERIC(12,2) NOT NULL,
    bank_account_id INTEGER,
    provider_id VARCHAR UNIQUE,
    status VARCHAR NOT NULL DEFAULT 'READY',
    payload TEXT,
    error VARCHAR,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    next_check_at TIMESTAMPTZ,
    CONSTRAINT chk_financial_kind CHECK (kind IN ('PAYOUT','REFUND')),
    CONSTRAINT chk_financial_amount CHECK (amount > 0),
    CONSTRAINT chk_financial_status CHECK (status IN ('READY','SENDING','PENDING','UNKNOWN','SUCCEEDED','REJECTED'))
);
CREATE INDEX IF NOT EXISTS ix_financial_operations_review_id ON financial_operations(review_id);
CREATE UNIQUE INDEX IF NOT EXISTS uq_financial_active_review ON financial_operations(review_id) WHERE status != 'REJECTED';
-- Financial data is server-only. Supabase's public REST roles must never
-- inherit access from default grants. The migration/table owner used by the
-- backend bypasses RLS; a separate backend role needs explicit privileges.
ALTER TABLE payout_profiles ENABLE ROW LEVEL SECURITY;
ALTER TABLE financial_operations ENABLE ROW LEVEL SECURITY;
REVOKE ALL ON TABLE payout_profiles, financial_operations FROM PUBLIC;
DO $$
BEGIN
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'anon') THEN
        REVOKE ALL ON TABLE payout_profiles, financial_operations FROM anon;
    END IF;
    IF EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'authenticated') THEN
        REVOKE ALL ON TABLE payout_profiles, financial_operations FROM authenticated;
    END IF;
END $$;
-- Legacy Culqi references and pending operations are intentionally preserved.
COMMIT;
