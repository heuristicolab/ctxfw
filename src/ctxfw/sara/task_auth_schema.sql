-- manifest_hash: ece9d70e52f09f3e80d8cadfd432c4b07a094ca40618ff12aa72a6f1cc92052a
-- Wave 2 Block D.1 :: Task-Scoped Paired-Replay Authorization Schema (#07)
-- Isolated SQLite WAL tables including auth_occ_ledger (never colliding with occ_version_ledger).

CREATE TABLE IF NOT EXISTS task_auth_policies (
    policy_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    allowed_domains_json TEXT NOT NULL CHECK(length(allowed_domains_json) >= 2),
    allowed_verbs_json TEXT NOT NULL CHECK(length(allowed_verbs_json) >= 2),
    allowed_scopes_json TEXT NOT NULL,
    max_multiplicity_k INTEGER NOT NULL CHECK(max_multiplicity_k BETWEEN 1 AND 100),
    policy_condition TEXT NOT NULL CHECK(policy_condition IN ('BROAD_BEARER', 'SCOPED_JWT', 'DPOP', 'OPA', 'LOCAL_DETERMINISTIC')),
    require_dpop INTEGER NOT NULL CHECK(require_dpop IN (0, 1)),
    require_local_opa INTEGER NOT NULL CHECK(require_local_opa IN (0, 1)),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_auth_session_state (
    session_id TEXT PRIMARY KEY,
    latest_state_sha256 TEXT NOT NULL CHECK(length(latest_state_sha256) = 64),
    occ_version INTEGER NOT NULL DEFAULT 0 CHECK(occ_version >= 0),
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_auth_dpop_nonces (
    dpop_jti TEXT PRIMARY KEY CHECK(length(dpop_jti) BETWEEN 16 AND 128),
    session_id TEXT NOT NULL,
    pre_state_sha256 TEXT NOT NULL CHECK(length(pre_state_sha256) = 64),
    post_state_sha256 TEXT NOT NULL CHECK(length(post_state_sha256) = 64),
    htm TEXT NOT NULL,
    htu TEXT NOT NULL,
    consumed_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_auth_tool_decisions (
    decision_id TEXT PRIMARY KEY,
    call_id TEXT NOT NULL,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    domain_name TEXT NOT NULL CHECK(length(domain_name) BETWEEN 1 AND 64),
    verb TEXT NOT NULL,
    tool_name TEXT NOT NULL,
    state TEXT NOT NULL CHECK(state IN ('TASK_ISSUED', 'CONTEXT_EXPOSED', 'SCOPE_CHECKED', 'EXECUTED', 'DENIED', 'QUARANTINED')),
    error_class TEXT CHECK(error_class IS NULL OR error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    allowed INTEGER NOT NULL CHECK(allowed IN (0, 1)),
    decision_seal_sha256 TEXT NOT NULL CHECK(length(decision_seal_sha256) = 64),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS task_auth_paired_replays (
    receipt_id TEXT PRIMARY KEY,
    task_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    domain_name TEXT NOT NULL CHECK(length(domain_name) BETWEEN 1 AND 64),
    attack_goal TEXT NOT NULL,
    policy_condition TEXT NOT NULL,
    compromise_c INTEGER NOT NULL CHECK(compromise_c IN (0, 1)),
    executed_y INTEGER NOT NULL CHECK(executed_y IN (0, 1)),
    harmful_execution_h INTEGER NOT NULL CHECK(harmful_execution_h = compromise_c * executed_y),
    decision_seal_sha256 TEXT NOT NULL CHECK(length(decision_seal_sha256) = 64),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS auth_occ_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL,
    occ_version INTEGER NOT NULL CHECK(occ_version >= 1),
    decision_seal_sha256 TEXT NOT NULL CHECK(length(decision_seal_sha256) = 64),
    manifest_hash TEXT NOT NULL CHECK(length(manifest_hash) = 64),
    recorded_at_utc TEXT NOT NULL,
    UNIQUE(session_id, occ_version)
);

CREATE TRIGGER IF NOT EXISTS auth_occ_ledger_no_update
BEFORE UPDATE ON auth_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'auth_occ_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS auth_occ_ledger_no_delete
BEFORE DELETE ON auth_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'auth_occ_ledger is immutable');
END;

CREATE TABLE IF NOT EXISTS task_auth_quarantine (
    quarantine_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    call_id TEXT NOT NULL,
    error_class TEXT NOT NULL CHECK(error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    reason TEXT NOT NULL,
    dpop_jti TEXT,
    payload_digest_sha256 TEXT NOT NULL CHECK(length(payload_digest_sha256) = 64),
    recorded_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_task_auth_decisions_session
    ON task_auth_tool_decisions (session_id, created_at_utc);
CREATE INDEX IF NOT EXISTS idx_task_auth_dpop_session
    ON task_auth_dpop_nonces (session_id, consumed_at_utc);
CREATE INDEX IF NOT EXISTS idx_task_auth_quarantine_session
    ON task_auth_quarantine (session_id, recorded_at_utc);
