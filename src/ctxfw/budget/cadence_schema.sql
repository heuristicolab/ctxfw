-- manifest_hash: 34ae93e3f71bcaab59019e9e0139a4b24b69b82c2005b25e5049329f84b1aa2c
-- Wave 2 Block D.2 :: Cadence Strategic Agent Guidance Schema (#19)
-- Isolated SQLite WAL tables including cadence_occ_ledger (never colliding with occ_version_ledger).

CREATE TABLE IF NOT EXISTS cadence_runs (
    run_id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL,
    scaffold_type TEXT NOT NULL CHECK(length(scaffold_type) BETWEEN 2 AND 64),
    i_base INTEGER NOT NULL CHECK(i_base BETWEEN 1 AND 20),
    delta_step INTEGER NOT NULL CHECK(delta_step BETWEEN 1 AND 10),
    i_max INTEGER NOT NULL CHECK(i_max BETWEEN 2 AND 50 AND i_base <= i_max),
    current_interval INTEGER NOT NULL CHECK(current_interval BETWEEN 1 AND 50),
    current_step_index INTEGER NOT NULL DEFAULT 0 CHECK(current_step_index >= 0),
    last_inspection_step INTEGER NOT NULL DEFAULT -1 CHECK(last_inspection_step >= -1),
    state TEXT NOT NULL CHECK(state IN (
        'EXECUTING_AUTONOMOUS', 'CADENCE_DUE', 'EVALUATING_DETERMINISTIC',
        'ADVISORY_APPLIED', 'REPLACEMENT_VETOED', 'ROLLED_BACK', 'COMPLETED', 'QUARANTINED'
    )),
    occ_version INTEGER NOT NULL DEFAULT 0 CHECK(occ_version >= 0),
    created_at_utc TEXT NOT NULL,
    updated_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cadence_step_verdicts (
    verdict_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES cadence_runs(run_id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL CHECK(step_index >= 0),
    inspection_triggered INTEGER NOT NULL CHECK(inspection_triggered IN (0, 1)),
    verdict TEXT NOT NULL CHECK(verdict IN ('ADVISORY', 'REPLACEMENT')),
    category TEXT NOT NULL CHECK(category IN (
        'NONE', 'GOAL_DRIFT', 'REPEATED_EDIT_STALL',
        'CONTEXT_BLOAT_SPIKE', 'CONSECUTIVE_TOOL_FAILURE', 'BREAKER_TRIP'
    )),
    action_executed INTEGER NOT NULL CHECK(
        (verdict != 'REPLACEMENT' OR action_executed = 0)
        AND (verdict != 'ADVISORY' OR action_executed = 1)
    ),
    next_interval INTEGER NOT NULL CHECK(next_interval BETWEEN 1 AND 50),
    guidance_note TEXT NOT NULL,
    rollback_triggered INTEGER NOT NULL DEFAULT 0 CHECK(rollback_triggered IN (0, 1)),
    rollback_target_epoch INTEGER,
    cadence_seal_sha256 TEXT NOT NULL CHECK(length(cadence_seal_sha256) = 64),
    created_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cadence_token_leverage (
    telemetry_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL REFERENCES cadence_runs(run_id) ON DELETE CASCADE,
    step_index INTEGER NOT NULL CHECK(step_index >= 0),
    tokens_without_guidance INTEGER NOT NULL CHECK(tokens_without_guidance >= 0),
    tokens_with_guidance INTEGER NOT NULL CHECK(tokens_with_guidance >= 0),
    token_leverage_ratio REAL NOT NULL CHECK(token_leverage_ratio >= 0.0),
    recorded_at_utc TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS cadence_occ_ledger (
    ledger_id INTEGER PRIMARY KEY AUTOINCREMENT,
    run_id TEXT NOT NULL REFERENCES cadence_runs(run_id) ON DELETE CASCADE,
    session_id TEXT NOT NULL,
    occ_version INTEGER NOT NULL CHECK(occ_version >= 1),
    verdict_seal_sha256 TEXT NOT NULL CHECK(length(verdict_seal_sha256) = 64),
    manifest_hash TEXT NOT NULL CHECK(length(manifest_hash) = 64),
    recorded_at_utc TEXT NOT NULL,
    UNIQUE(run_id, occ_version)
);

CREATE TRIGGER IF NOT EXISTS cadence_occ_ledger_no_update
BEFORE UPDATE ON cadence_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'cadence_occ_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS cadence_occ_ledger_no_delete
BEFORE DELETE ON cadence_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'cadence_occ_ledger is immutable');
END;

CREATE TABLE IF NOT EXISTS cadence_quarantine (
    quarantine_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    session_id TEXT NOT NULL,
    error_class TEXT NOT NULL CHECK(error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    reason TEXT NOT NULL,
    recorded_at_utc TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS idx_cadence_verdicts_run_step
    ON cadence_step_verdicts (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_cadence_leverage_run_step
    ON cadence_token_leverage (run_id, step_index);
CREATE INDEX IF NOT EXISTS idx_cadence_quarantine_run
    ON cadence_quarantine (run_id, recorded_at_utc);
