-- Run after production_readiness.sql, in staging first with a verified backup.
BEGIN;
ALTER TABLE users ADD COLUMN IF NOT EXISTS rating NUMERIC(3,2) NOT NULL DEFAULT 4.00;
ALTER TABLE users ADD COLUMN IF NOT EXISTS warning_count INTEGER NOT NULL DEFAULT 0;
ALTER TABLE tickets ADD COLUMN IF NOT EXISTS event_end_date TIMESTAMPTZ;
DO $$ BEGIN
    ALTER TABLE users ADD CONSTRAINT chk_user_rating CHECK (rating >= 0 AND rating <= 5);
EXCEPTION WHEN duplicate_object THEN NULL; END $$;
CREATE TABLE IF NOT EXISTS purchase_reviews (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    transaction_id UUID NOT NULL UNIQUE REFERENCES transactions(id),
    ticket_id UUID NOT NULL UNIQUE REFERENCES tickets(id),
    delivered_at TIMESTAMPTZ,
    closes_at TIMESTAMPTZ,
    review_state VARCHAR NOT NULL DEFAULT 'HELD',
    decision VARCHAR,
    dispute_text TEXT,
    reported_at TIMESTAMPTZ,
    decided_by UUID REFERENCES users(id),
    decision_reason TEXT,
    settlement_state VARCHAR NOT NULL DEFAULT 'NONE',
    settlement_reference VARCHAR UNIQUE,
    settlement_error VARCHAR,
    reputation_applied BOOLEAN NOT NULL DEFAULT FALSE,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT chk_review_state CHECK (review_state IN ('HELD','DISPUTED','RESOLVED')),
    CONSTRAINT chk_review_settlement CHECK (settlement_state IN ('NONE','QUEUED','BLOCKED','PROCESSING','UNKNOWN','SUCCEEDED'))
);
CREATE TABLE IF NOT EXISTS dispute_evidence (
    id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    review_id UUID NOT NULL REFERENCES purchase_reviews(id),
    storage_path VARCHAR NOT NULL,
    media_type VARCHAR NOT NULL,
    created_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS ix_dispute_evidence_review_id ON dispute_evidence(review_id);
-- Preserve terminal history without inventing a new provider confirmation.
-- LEGACY_* records never replay payouts/refunds or retroactive reputation:
-- reputation_applied=TRUE is a no-replay marker, not a new rating award/penalty.
-- This migration does not change existing users.rating or warning_count.
-- Pending historical refunds need reconciliation, not a second blind POST.
-- Delivered, unfinished purchases with unknown event end remain on hold.
INSERT INTO purchase_reviews (
    id, created_at, transaction_id, ticket_id, delivered_at, closes_at, review_state,
    decision, decision_reason, settlement_state, settlement_error, reputation_applied
)
SELECT gen_random_uuid(), CURRENT_TIMESTAMP, tx.id, t.id,
    CASE WHEN t.estado IN ('VENDIDA','LIBERADA') THEN tx.created_at END,
    CASE WHEN t.event_end_date IS NOT NULL
              AND t.event_end_date < TIMESTAMPTZ '9999-12-31 00:00:00+00'
         THEN t.event_end_date + INTERVAL '24 hours' END,
    CASE WHEN tx.status IN ('REFUNDED','REFUND_PENDING') OR t.estado IN ('LIBERADA','REEMBOLSADA')
         THEN 'RESOLVED' ELSE 'HELD' END,
    CASE WHEN tx.status = 'REFUNDED' OR t.estado = 'REEMBOLSADA' THEN 'LEGACY_REFUND'
         WHEN t.estado = 'LIBERADA' THEN 'LEGACY_PAYOUT'
         WHEN tx.status = 'REFUND_PENDING' THEN 'VALID_CLAIM' END,
    CASE WHEN tx.status = 'REFUNDED' OR t.estado IN ('LIBERADA','REEMBOLSADA')
         THEN 'Histórico terminado antes de esta versión; no ejecutar pagos ni recalcular reputación.'
         WHEN tx.status = 'REFUND_PENDING'
         THEN 'Reembolso pendiente histórico: verificar la pasarela antes de reenviar.' END,
    CASE WHEN tx.status = 'REFUNDED' OR t.estado IN ('LIBERADA','REEMBOLSADA') THEN 'SUCCEEDED'
         WHEN tx.status = 'REFUND_PENDING' THEN 'UNKNOWN' ELSE 'NONE' END,
    CASE WHEN tx.status = 'REFUND_PENDING' AND t.estado NOT IN ('LIBERADA','REEMBOLSADA')
         THEN 'Reembolso pendiente histórico: conciliar con la pasarela antes de reenviar.' END,
    (tx.status = 'REFUNDED' OR t.estado IN ('LIBERADA','REEMBOLSADA'))
FROM transactions tx JOIN tickets t ON t.id = tx.ticket_id
WHERE tx.status IN ('REFUNDED','REFUND_PENDING')
   OR (tx.status = 'SUCCEEDED' AND t.estado IN ('VENDIDA','PENDIENTE_RENOMINACION','LIBERADA','REEMBOLSADA'))
ON CONFLICT DO NOTHING;
COMMIT;
