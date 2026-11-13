-- src/ctxfw/storage/snapshot_schema.sql — Sandbox Snapshot Rollback & Go-Explore WAL DDL
-- manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
-- blueprint_manifest_hash: 7fb2c154c3f3e904d0e70445120a150a7d8d59cd7349cf13316421ffc816fc55

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS snapshot_runs (
    run_id TEXT PRIMARY KEY,
    project_root TEXT NOT NULL,
    project_id TEXT NOT NULL,
    total_token_budget INTEGER NOT NULL CHECK (total_token_budget BETWEEN 1 AND 1000000),
    max_children_per_root INTEGER NOT NULL CHECK (max_children_per_root BETWEEN 1 AND 4),
    manifest_hash TEXT NOT NULL,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_runs_immutable
BEFORE UPDATE ON snapshot_runs
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_runs rows are immutable');
END;

CREATE TABLE IF NOT EXISTS snapshot_archive_cells (
    cell_record_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    project_root TEXT NOT NULL,
    parent_snapshot_id TEXT,
    step_index INTEGER NOT NULL CHECK (step_index >= 0),
    depth INTEGER NOT NULL CHECK (depth >= 0 AND depth <= 128),
    git_commit_sha TEXT,
    working_tree_digest TEXT NOT NULL,
    pass_rate REAL NOT NULL CHECK (pass_rate >= 0.0 AND pass_rate <= 1.0),
    failing_tests INTEGER NOT NULL CHECK (failing_tests >= 0),
    tokens_used_to_reach INTEGER NOT NULL CHECK (tokens_used_to_reach >= 0),
    handoff_tokens INTEGER NOT NULL CHECK (handoff_tokens >= 0),
    max_children_per_root INTEGER NOT NULL CHECK (max_children_per_root BETWEEN 1 AND 4),
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN (
            'CREATED',
            'CHECKPOINTED',
            'BRANCH_EXPANDED',
            'ATTRACTOR_DETECTED',
            'ROLLBACK_PENDING',
            'RESTORED_INVALIDATED',
            'COMMITTED_TERMINAL',
            'QUARANTINED_TERMINAL'
        )
    ),
    rollback_epoch INTEGER NOT NULL CHECK (rollback_epoch >= 0),
    manifest_hash TEXT NOT NULL,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_cells_immutable
BEFORE UPDATE ON snapshot_archive_cells
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_archive_cells rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_cells_run
ON snapshot_archive_cells(run_id, snapshot_id, created_seq);

CREATE TABLE IF NOT EXISTS snapshot_non_git_artifacts (
    record_id TEXT PRIMARY KEY,
    snapshot_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    artifact_id TEXT NOT NULL,
    kind TEXT NOT NULL CHECK (
        kind IN ('SQLITE_DB', 'BACKGROUND_DAEMON', 'MIGRATION_JOURNAL', 'ENV_PACKAGE')
    ),
    resource_path_or_pid TEXT NOT NULL,
    pre_state_digest TEXT NOT NULL,
    dirty_after_step INTEGER NOT NULL CHECK (dirty_after_step IN (0, 1)),
    reversible_via_snapshot INTEGER NOT NULL CHECK (reversible_via_snapshot IN (0, 1)),
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_artifacts_immutable
BEFORE UPDATE ON snapshot_non_git_artifacts
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_non_git_artifacts rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_artifacts_snap
ON snapshot_non_git_artifacts(run_id, snapshot_id, created_seq);

CREATE TABLE IF NOT EXISTS snapshot_budget_ledger_events (
    ledger_event_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    tokens_delta INTEGER NOT NULL CHECK (tokens_delta >= 0),
    handoff_delta INTEGER NOT NULL CHECK (handoff_delta >= 0),
    cumulative_tokens_spent INTEGER NOT NULL CHECK (cumulative_tokens_spent >= 0),
    cumulative_handoff_spent INTEGER NOT NULL CHECK (cumulative_handoff_spent >= 0),
    total_token_budget INTEGER NOT NULL CHECK (total_token_budget BETWEEN 1 AND 1000000),
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    CHECK (cumulative_tokens_spent + cumulative_handoff_spent <= total_token_budget),
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_budget_immutable
BEFORE UPDATE ON snapshot_budget_ledger_events
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_budget_ledger_events rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_budget_run
ON snapshot_budget_ledger_events(run_id, created_seq);

CREATE TABLE IF NOT EXISTS snapshot_fsm_transitions (
    transition_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    snapshot_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    event TEXT NOT NULL,
    to_state TEXT NOT NULL,
    rollback_epoch INTEGER NOT NULL CHECK (rollback_epoch >= 0),
    manifest_hash TEXT NOT NULL,
    seq_no INTEGER NOT NULL CHECK (seq_no >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_transitions_immutable
BEFORE UPDATE ON snapshot_fsm_transitions
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_fsm_transitions rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_transitions_run
ON snapshot_fsm_transitions(run_id, snapshot_id, seq_no);

CREATE TABLE IF NOT EXISTS snapshot_rollback_dispatches (
    dispatch_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    source_snapshot_id TEXT NOT NULL,
    target_root_snapshot_id TEXT NOT NULL,
    restoration_mode TEXT NOT NULL CHECK (
        restoration_mode IN ('FULL_SANDBOX_SNAPSHOT', 'GIT_DIFF_REPLAY', 'QUARANTINED_NOOP')
    ),
    selection_score REAL NOT NULL CHECK (selection_score >= 0.0),
    projected_handoff_tokens INTEGER NOT NULL CHECK (projected_handoff_tokens >= 0),
    projected_branch_tokens INTEGER NOT NULL CHECK (projected_branch_tokens >= 0),
    recovery_efficiency REAL NOT NULL CHECK (recovery_efficiency >= 0.0),
    cache_invalidated_entries INTEGER NOT NULL CHECK (cache_invalidated_entries >= 0),
    rollback_epoch INTEGER NOT NULL CHECK (rollback_epoch >= 1),
    stale_reads_blocked INTEGER NOT NULL CHECK (stale_reads_blocked IN (0, 1)),
    allowed INTEGER NOT NULL CHECK (allowed IN (0, 1)),
    block_reason TEXT,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_dispatches_immutable
BEFORE UPDATE ON snapshot_rollback_dispatches
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_rollback_dispatches rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_dispatches_run
ON snapshot_rollback_dispatches(run_id, created_seq);

CREATE TABLE IF NOT EXISTS snapshot_quarantine_entries (
    quarantine_id TEXT PRIMARY KEY,
    run_id TEXT NOT NULL,
    snapshot_id TEXT,
    error_class TEXT NOT NULL CHECK (
        error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')
    ),
    rule_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (run_id) REFERENCES snapshot_runs(run_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_snapshot_quarantine_immutable
BEFORE UPDATE ON snapshot_quarantine_entries
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: snapshot_quarantine_entries rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_snapshot_quarantine_run
ON snapshot_quarantine_entries(run_id, created_seq);
