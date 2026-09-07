-- =========================================================================
-- Heurístico Lab :: Local SQLite WAL Semantic Cache DDL (v3.4.0)
-- Invariant: WAL Mode, Sub-millisecond lookup, Inviolable Audit
-- =========================================================================
CREATE TABLE IF NOT EXISTS tokens_cache (
    cache_key VARCHAR(64) PRIMARY KEY NOT NULL,
    pruned_code TEXT NOT NULL,
    pruning_depth VARCHAR(16) NOT NULL DEFAULT 'interface',
    original_chars INTEGER NOT NULL,
    pruned_chars INTEGER NOT NULL,
    estimated_tokens_saved INTEGER NOT NULL,
    savings_percentage REAL NOT NULL,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_tokens_depth ON tokens_cache(pruning_depth);
CREATE INDEX IF NOT EXISTS idx_tokens_savings ON tokens_cache(savings_percentage);

CREATE TABLE IF NOT EXISTS telemetry_ledger (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    dev_uuid TEXT NOT NULL,
    timestamp_utc TEXT NOT NULL,
    model_target TEXT NOT NULL,
    tokens_orig INTEGER NOT NULL,
    tokens_pruned INTEGER NOT NULL,
    usd_avoided REAL NOT NULL,
    team TEXT NOT NULL DEFAULT 'Engineering',
    synced INTEGER NOT NULL DEFAULT 0
);

CREATE INDEX IF NOT EXISTS idx_telemetry_synced ON telemetry_ledger(synced);
CREATE INDEX IF NOT EXISTS idx_telemetry_timestamp ON telemetry_ledger(timestamp_utc);
