-- manifest_hash: 4b3c6d65f2aeffd4fcfd8ecf166c4983ef94b046d3c9b7fd5e391811d32a5d82
-- ctxfw.mcp_guard :: SQLite WAL Schema (Wave 1 Block A)
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
