-- manifest_hash: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
-- manifest_hash_wave2e1: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
-- ctxfw.mcp_guard :: SQLite WAL Schema (Wave 1 Block A + Wave 2 Block E.1 #04)
-- Absorbs #05 (MCP Tool Poisoning Firewall) + #03 (MCP Capability Laundering Guard)
-- Excludes out-of-scope red-team HTTP telemetry tables.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS mcp_tool_pins (
    pin_id             TEXT PRIMARY KEY,
    server_id          TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name          TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    description_length INTEGER NOT NULL CHECK (description_length BETWEEN 0 AND 16384),
    pin_sha256         TEXT NOT NULL CHECK (length(pin_sha256) = 64),
    surface            TEXT NOT NULL,
    status             TEXT NOT NULL CHECK (status IN (
        'UNVERIFIED',
        'PINNED',
        'INSPECTION_PASSED',
        'EXECUTED_CLEAN',
        'INTENT_FLAGGED',
        'CONFINED_DENY',
        'EXFIL_DETECTED',
        'RUG_PULL_BLOCKED',
        'QUARANTINED'
    )),
    pinned_at_utc      TEXT NOT NULL,
    UNIQUE (server_id, tool_name)
);

CREATE TABLE IF NOT EXISTS poison_scan_findings (
    finding_id                 TEXT PRIMARY KEY,
    server_id                  TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name                  TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    vector                     TEXT NOT NULL CHECK (vector GLOB 'P*'),
    surface                    TEXT NOT NULL,
    imperative_risk_score      REAL NOT NULL CHECK (imperative_risk_score >= 0.0 AND imperative_risk_score <= 1.0),
    invisible_unicode_detected INTEGER NOT NULL CHECK (invisible_unicode_detected IN (0, 1)),
    quarantine_triggered       INTEGER NOT NULL CHECK (quarantine_triggered IN (0, 1)),
    matched_signals_json       TEXT NOT NULL,
    summary                    TEXT NOT NULL,
    detected_at_utc            TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS param_binding_audits (
    audit_id         TEXT PRIMARY KEY,
    server_id        TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name        TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    binding_verdict  TEXT NOT NULL CHECK (binding_verdict IN (
        'PASS',
        'UNKNOWN_KEY_REJECTED',
        'MISSING_REQUIRED',
        'TYPE_VIOLATION'
    )),
    unknown_keys_json TEXT NOT NULL,
    missing_keys_json TEXT NOT NULL,
    audited_at_utc    TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS mcp_tool_contracts (
    contract_id              TEXT PRIMARY KEY,
    server_id                TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name                TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    authorized_roots_json    TEXT NOT NULL,
    allow_unsandboxed_fallback INTEGER NOT NULL DEFAULT 0 CHECK (allow_unsandboxed_fallback = 0),
    follow_symlinks          INTEGER NOT NULL DEFAULT 0 CHECK (follow_symlinks IN (0, 1)),
    registered_at_utc        TEXT NOT NULL,
    UNIQUE (server_id, tool_name)
);

CREATE TABLE IF NOT EXISTS inferred_sandbox_boundaries (
    boundary_id           TEXT PRIMARY KEY,
    server_id             TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    authorized_roots_json TEXT NOT NULL,
    canary_tokens_json    TEXT NOT NULL,
    verified_disjoint     INTEGER NOT NULL DEFAULT 1 CHECK (verified_disjoint = 1),
    created_at_utc        TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS confinement_audit_logs (
    log_id          TEXT PRIMARY KEY,
    server_id       TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name       TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    verdict         TEXT NOT NULL CHECK (verdict IN (
        'ALLOW',
        'DENY_TRAVERSAL',
        'DENY_SIBLING_PREFIX',
        'DENY_SYMLINK_ESCAPE',
        'DENY_URI_SCHEME',
        'DENY_UNSANDBOXED_FALLBACK',
        'DENY_PIN_MISMATCH',
        'DENY_POISON_DESCRIPTION',
        'DENY_PARAM_INJECTION'
    )),
    sarif_rule_id   TEXT,
    raw_path_sha256 TEXT NOT NULL CHECK (length(raw_path_sha256) = 64),
    reason          TEXT NOT NULL,
    logged_at_utc   TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS poisoning_quarantine (
    quarantine_id  TEXT PRIMARY KEY,
    server_id      TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name      TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    terminal_state TEXT NOT NULL CHECK (terminal_state IN (
        'CONFINED_DENY',
        'EXFIL_DETECTED',
        'RUG_PULL_BLOCKED',
        'QUARANTINED'
    )),
    vector         TEXT NOT NULL CHECK (vector GLOB 'P*' OR vector GLOB 'PT-*'),
    evidence_sha256 TEXT NOT NULL CHECK (length(evidence_sha256) = 64),
    reason         TEXT NOT NULL,
    quarantined_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS occ_version_ledger (
    occ_seq        INTEGER PRIMARY KEY AUTOINCREMENT,
    server_id      TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name      TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    pin_sha256     TEXT NOT NULL CHECK (length(pin_sha256) = 64),
    event_kind     TEXT NOT NULL,
    state_after    TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_mcp_pins_tool ON mcp_tool_pins(tool_name, server_id);
CREATE INDEX IF NOT EXISTS idx_poison_findings_tool ON poison_scan_findings(server_id, tool_name);
CREATE INDEX IF NOT EXISTS idx_quarantine_tool ON poisoning_quarantine(server_id, tool_name);
CREATE INDEX IF NOT EXISTS idx_confinement_logs_verdict ON confinement_audit_logs(verdict, logged_at_utc);

-- Immutability triggers (Invariant #7)
CREATE TRIGGER IF NOT EXISTS trg_pins_immutable_update
BEFORE UPDATE ON mcp_tool_pins
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_01: mcp_tool_pins rows are cryptographically immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_pins_immutable_delete
BEFORE DELETE ON mcp_tool_pins
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_01: mcp_tool_pins rows cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_findings_immutable_update
BEFORE UPDATE ON poison_scan_findings
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: poison_scan_findings is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_findings_immutable_delete
BEFORE DELETE ON poison_scan_findings
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: poison_scan_findings cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_contracts_no_unsandboxed_update
BEFORE UPDATE ON mcp_tool_contracts
WHEN NEW.allow_unsandboxed_fallback <> 0
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_04: allow_unsandboxed_fallback shall never be enabled');
END;

CREATE TRIGGER IF NOT EXISTS trg_confinement_immutable_update
BEFORE UPDATE ON confinement_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: confinement_audit_logs is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_confinement_immutable_delete
BEFORE DELETE ON confinement_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: confinement_audit_logs cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_occ_immutable_update
BEFORE UPDATE ON occ_version_ledger
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: occ_version_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_occ_immutable_delete
BEFORE DELETE ON occ_version_ledger
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_07: occ_version_ledger cannot be deleted');
END;

-- Wave 2 Block E.1 (#04): Dynamic Paired Containment & Capability Laundering Audits

CREATE TABLE IF NOT EXISTS paired_containment_audits (
    audit_id             TEXT PRIMARY KEY,
    boundary_id          TEXT NOT NULL CHECK (boundary_id GLOB 'BND-*'),
    server_id            TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name            TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    poc1_disclosed       INTEGER NOT NULL CHECK (poc1_disclosed IN (0, 1)),
    poc2_benign_denied   INTEGER NOT NULL CHECK (poc2_benign_denied IN (0, 1)),
    poc3_disclosed       INTEGER NOT NULL CHECK (poc3_disclosed IN (0, 1)),
    canary_overlap_count INTEGER NOT NULL CHECK (canary_overlap_count >= 0),
    verdict              TEXT NOT NULL CHECK (verdict IN (
        'CONTAINED_PASS',
        'INERT_POC1',
        'DENIED_BENIGN_POC2',
        'LAUNDERING_EXPOSED_POC3',
        'CANARY_OVERLAP_REJECTED'
    )),
    allowed              INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    reason               TEXT NOT NULL,
    attestation_sha256   TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    audited_at_utc       TEXT NOT NULL,
    CHECK (
        (
            verdict = 'CONTAINED_PASS'
            AND poc1_disclosed = 1
            AND poc2_benign_denied = 0
            AND poc3_disclosed = 0
            AND canary_overlap_count = 0
            AND allowed = 1
        )
        OR (
            verdict <> 'CONTAINED_PASS'
            AND allowed = 0
        )
    )
);

CREATE TABLE IF NOT EXISTS capability_laundering_audits (
    audit_id            TEXT PRIMARY KEY,
    server_id           TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    tool_name           TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    declared_readonly   INTEGER NOT NULL CHECK (declared_readonly IN (0, 1)),
    allowed             INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    laundering_detected INTEGER NOT NULL CHECK (laundering_detected IN (0, 1)),
    terminal_state      TEXT NOT NULL CHECK (terminal_state IN ('ALLOW', 'CONFINED_DENY', 'QUARANTINED')),
    violations_json     TEXT NOT NULL,
    reason              TEXT NOT NULL,
    attestation_sha256  TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    audited_at_utc      TEXT NOT NULL,
    CHECK (
        (allowed = 1 AND laundering_detected = 0 AND terminal_state = 'ALLOW')
        OR (allowed = 0 AND laundering_detected = 1 AND terminal_state <> 'ALLOW')
    )
);

CREATE TRIGGER IF NOT EXISTS trg_paired_containment_immutable_update
BEFORE UPDATE ON paired_containment_audits
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_08: paired_containment_audits is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_paired_containment_immutable_delete
BEFORE DELETE ON paired_containment_audits
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_08: paired_containment_audits cannot be deleted');
END;

CREATE TRIGGER IF NOT EXISTS trg_cap_laundering_immutable_update
BEFORE UPDATE ON capability_laundering_audits
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_09: capability_laundering_audits is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_cap_laundering_immutable_delete
BEFORE DELETE ON capability_laundering_audits
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_09: capability_laundering_audits cannot be deleted');
END;

CREATE TABLE IF NOT EXISTS rate_limit_audit_logs (
    audit_id            TEXT PRIMARY KEY,
    server_id           TEXT NOT NULL CHECK (length(server_id) BETWEEN 1 AND 128),
    client_key_hash     TEXT NOT NULL CHECK (length(client_key_hash) = 64),
    tool_name           TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    state               TEXT NOT NULL CHECK (state IN ('THROTTLED')),
    error_class         TEXT NOT NULL CHECK (error_class IN ('BUSINESS')),
    error_code          TEXT NOT NULL CHECK (error_code IN ('ERR_RATE_LIMIT_EXCEEDED')),
    remaining_tokens_q4 TEXT NOT NULL,
    retry_after_ms      INTEGER NOT NULL CHECK (retry_after_ms >= 0 AND retry_after_ms <= 3600000),
    clock_regressed     INTEGER NOT NULL CHECK (clock_regressed IN (0, 1)),
    reason              TEXT NOT NULL,
    evaluated_at_ms     INTEGER NOT NULL CHECK (evaluated_at_ms >= 0),
    audited_at_utc      TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_rate_limit_audits_client
    ON rate_limit_audit_logs (client_key_hash, evaluated_at_ms);

CREATE TRIGGER IF NOT EXISTS trg_rate_limit_audits_immutable_update
BEFORE UPDATE ON rate_limit_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_10: rate_limit_audit_logs is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_rate_limit_audits_immutable_delete
BEFORE DELETE ON rate_limit_audit_logs
BEGIN
    SELECT RAISE(ABORT, 'MCG_INV_10: rate_limit_audit_logs cannot be deleted');
END;
