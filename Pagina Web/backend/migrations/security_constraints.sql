-- ============================================================
-- Script de Seguridad: Restricciones únicas en Base de Datos
-- Ejecutar en: Supabase → SQL Editor
-- ============================================================

-- 1. Impedir que el mismo cargo de Culqi se procese dos veces
--    (Doble capa de protección: aplicación + base de datos)
ALTER TABLE transactions
    ADD CONSTRAINT uq_transaction_culqi_charge_id
    UNIQUE (culqi_charge_id);

-- 2. Asegurar que una entrada VENDIDA no pueda tener buyer_id nulo
--    (Integridad referencial: si alguien vende, debe haber un comprador)
ALTER TABLE tickets
    ADD CONSTRAINT chk_vendida_tiene_buyer
    CHECK (
        NOT (estado = 'VENDIDA' AND buyer_id IS NULL)
    );

-- 3. Asegurar que el precio de cualquier entrada sea siempre positivo
--    (Defensa en profundidad junto a la validación en Python)
ALTER TABLE tickets
    ADD CONSTRAINT chk_price_positive
    CHECK (price > 0);

-- 4. Asegurar que los montos de transacción sean siempre positivos
ALTER TABLE transactions
    ADD CONSTRAINT chk_amounts_positive
    CHECK (
        amount_total > 0
        AND commission_platform >= 0
        AND amount_seller >= 0
    );
