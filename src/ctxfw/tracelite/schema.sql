-- src/ctxfw/tracelite/schema.sql — TraceLite Immutable SQLite WAL DDL
-- manifest_hash: 00743e30ed7cee52140a1538a8622aeccb12a6c524adc80d875ab067bd39f762
-- blueprint_manifest_hash: 6a95bb7fd01158ac75d67055df0c328d56433a44625351610307d5ef6b68d0cf

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;
PRAGMA synchronous = NORMAL;

CREATE TABLE IF NOT EXISTS tracelite_trajectories (
    reduction_id TEXT PRIMARY KEY,
    trajectory_id TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    lifecycle_state TEXT NOT NULL CHECK (
        lifecycle_state IN (
            'INGESTED',
            'DEDUPLICATED',
            'PHASE_CLEANED',
            'OPTICALLY_RENDERED',
            'WINDOW_ASSEMBLED',
            'QUARANTINED'
        )
    ),
    total_steps INTEGER NOT NULL CHECK (total_steps >= 0),
    recent_window_w INTEGER NOT NULL CHECK (recent_window_w BETWEEN 1 AND 10),
    optical_ratio_k REAL NOT NULL CHECK (optical_ratio_k >= 1.0 AND optical_ratio_k <= 8.0),
    raw_tokens_total INTEGER NOT NULL CHECK (raw_tokens_total >= 0),
    reduced_tokens_total INTEGER NOT NULL CHECK (reduced_tokens_total >= 0 AND reduced_tokens_total <= raw_tokens_total),
    tokens_saved INTEGER NOT NULL CHECK (tokens_saved >= 0),
    aux_llm_allowed INTEGER NOT NULL CHECK (aux_llm_allowed = 0),
    actions_preserved INTEGER NOT NULL CHECK (actions_preserved = 1),
    newest_preserved INTEGER NOT NULL CHECK (newest_preserved = 1),
    manifest_hash TEXT NOT NULL,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_tracelite_trajectories_immutable
BEFORE UPDATE ON tracelite_trajectories
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: tracelite_trajectories rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_tracelite_traj_id
ON tracelite_trajectories(trajectory_id, created_seq);

CREATE TABLE IF NOT EXISTS tracelite_optical_artifacts (
    artifact_id TEXT NOT NULL,
    reduction_id TEXT NOT NULL,
    trajectory_id TEXT NOT NULL,
    step_index INTEGER NOT NULL CHECK (step_index >= 0),
    source_sha256 TEXT NOT NULL,
    policy_hash TEXT NOT NULL,
    canvas_width_px INTEGER NOT NULL CHECK (canvas_width_px BETWEEN 224 AND 2240),
    canvas_height_px INTEGER NOT NULL CHECK (canvas_height_px BETWEEN 224 AND 2240),
    patch_size_px INTEGER NOT NULL CHECK (patch_size_px BETWEEN 8 AND 32),
    raw_text_tokens INTEGER NOT NULL CHECK (raw_text_tokens >= 1),
    optical_patch_tokens INTEGER NOT NULL CHECK (optical_patch_tokens >= 1 AND optical_patch_tokens <= raw_text_tokens),
    effective_compression_k REAL NOT NULL CHECK (effective_compression_k >= 1.0 AND effective_compression_k <= 8.0),
    char_similarity REAL NOT NULL CHECK (char_similarity >= 0.0 AND char_similarity <= 1.0),
    rendered_digest TEXT NOT NULL,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (reduction_id, step_index, artifact_id),
    FOREIGN KEY (reduction_id) REFERENCES tracelite_trajectories(reduction_id) ON DELETE CASCADE
);

CREATE TRIGGER IF NOT EXISTS trg_tracelite_artifacts_immutable
BEFORE UPDATE ON tracelite_optical_artifacts
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: tracelite_optical_artifacts rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_tracelite_artifacts_traj
ON tracelite_optical_artifacts(trajectory_id, step_index);

CREATE TABLE IF NOT EXISTS tracelite_audit_transitions (
    transition_id TEXT PRIMARY KEY,
    trajectory_id TEXT NOT NULL,
    from_state TEXT NOT NULL,
    event TEXT NOT NULL,
    to_state TEXT NOT NULL,
    policy_id TEXT NOT NULL,
    manifest_hash TEXT NOT NULL,
    seq_no INTEGER NOT NULL CHECK (seq_no >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_tracelite_transitions_immutable
BEFORE UPDATE ON tracelite_audit_transitions
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: tracelite_audit_transitions rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_tracelite_transitions_traj
ON tracelite_audit_transitions(trajectory_id, seq_no);

CREATE TABLE IF NOT EXISTS tracelite_quarantine_incidents (
    incident_id TEXT PRIMARY KEY,
    trajectory_id TEXT NOT NULL,
    error_class TEXT NOT NULL CHECK (error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    rule_code TEXT NOT NULL,
    detail TEXT NOT NULL,
    step_index INTEGER,
    created_seq INTEGER NOT NULL CHECK (created_seq >= 1),
    created_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_tracelite_quarantine_immutable
BEFORE UPDATE ON tracelite_quarantine_incidents
BEGIN
    SELECT RAISE(ABORT, 'SECURITY: tracelite_quarantine_incidents rows are immutable');
END;

CREATE INDEX IF NOT EXISTS idx_tracelite_quarantine_traj
ON tracelite_quarantine_incidents(trajectory_id, created_seq);
