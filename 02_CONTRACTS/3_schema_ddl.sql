-- =========================================================================
-- Relational Schema SQL DDL (SQLite WAL / PostgreSQL Enterprise Compatible)
-- Complete Self-Contained Parent & Child Relational Hierarchy
-- =========================================================================
CREATE TABLE IF NOT EXISTS clients (
    client_id VARCHAR(64) PRIMARY KEY NOT NULL,
    name VARCHAR(255) NOT NULL,
    corporate_email VARCHAR(255) UNIQUE NOT NULL,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL
);

CREATE TABLE IF NOT EXISTS orders (
    order_id VARCHAR(64) PRIMARY KEY NOT NULL,
    client_id VARCHAR(64) NOT NULL,
    service_tier VARCHAR(64) NOT NULL DEFAULT 'ENTERPRISE_BLUEPRINT',
    amount_usd NUMERIC(18, 4) NOT NULL DEFAULT 4500.0000,
    fsm_state VARCHAR(32) NOT NULL DEFAULT 'ACTIVE',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (client_id) REFERENCES clients(client_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesized_domain_records (
    record_id VARCHAR(64) PRIMARY KEY NOT NULL,
    order_id VARCHAR(64) NOT NULL,
    brief_summary TEXT NOT NULL,
    processing_status VARCHAR(32) NOT NULL DEFAULT 'ACTIVE' CHECK (processing_status IN ('PENDING', 'ACTIVE', 'COMPLETED', 'QUARANTINED')),
    payload_json TEXT NOT NULL,
    latency_ms REAL NOT NULL DEFAULT 0.0,
    tokens_saved INTEGER NOT NULL DEFAULT 42500,
    version INTEGER NOT NULL DEFAULT 1,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (order_id) REFERENCES orders(order_id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS synthesized_security_audits (
    audit_id VARCHAR(64) PRIMARY KEY NOT NULL,
    record_id VARCHAR(64) NOT NULL,
    session_id VARCHAR(64) NOT NULL,
    risk_score REAL NOT NULL DEFAULT 0.0,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP NOT NULL,
    FOREIGN KEY (record_id) REFERENCES synthesized_domain_records(record_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS idx_synth_order ON synthesized_domain_records(order_id);
CREATE INDEX IF NOT EXISTS idx_synth_status_active ON synthesized_domain_records(processing_status) WHERE processing_status = 'ACTIVE';
CREATE INDEX IF NOT EXISTS idx_synth_audit_record ON synthesized_security_audits(record_id);
CREATE INDEX IF NOT EXISTS idx_synth_audit_session ON synthesized_security_audits(session_id);