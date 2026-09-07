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
