ALTER TABLE transactions
    ADD COLUMN IF NOT EXISTS operation_id TEXT;

CREATE UNIQUE INDEX IF NOT EXISTS idx_tx_service_operation_id
    ON transactions(service_id, operation_id)
    WHERE operation_id IS NOT NULL;