-- manifest_hash: b77d4295c196c37e848903d930d8d1a358fc9178b4dca90ba40fd28db264f37a
-- Wave 2 Block E.1 (Appendix H): Causal Provenance (#31) & Monotonic Epoch Freshness (#28) Schema
-- Isolated OCC ledger (provenance_occ_ledger), mutual-exclusion CHECKs, zero raw payloads,
-- and replay-auditable epoch quarantine without impossible INSERT CHECKs.

PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS provenance_graph_edges (
    edge_seq         INTEGER PRIMARY KEY AUTOINCREMENT,
    edge_id          TEXT NOT NULL,
    session_id       TEXT NOT NULL CHECK (length(session_id) BETWEEN 4 AND 64),
    src_node         TEXT NOT NULL CHECK (length(src_node) BETWEEN 4 AND 64),
    dst_node         TEXT NOT NULL CHECK (length(dst_node) BETWEEN 4 AND 64),
    tool_name        TEXT NOT NULL CHECK (length(tool_name) BETWEEN 1 AND 128),
    alignment_status TEXT NOT NULL CHECK (alignment_status IN ('ALIGNED', 'MISALIGNED')),
    tool_succeeded   INTEGER NOT NULL CHECK (tool_succeeded IN (0, 1)),
    payload_sha256   TEXT NOT NULL CHECK (length(payload_sha256) = 64),
    recorded_at_utc  TEXT NOT NULL,
    UNIQUE (session_id, edge_id)
);

CREATE TABLE IF NOT EXISTS provenance_traces (
    trace_id               TEXT PRIMARY KEY,
    session_id             TEXT NOT NULL CHECK (length(session_id) BETWEEN 4 AND 64),
    sink_node              TEXT NOT NULL CHECK (length(sink_node) BETWEEN 4 AND 64),
    classification         TEXT NOT NULL CHECK (classification IN ('CLEAN_BENIGN', 'BENIGN_AGENT_DRIFT', 'IPI_CONFIRMED')),
    has_misaligned_sink_edge INTEGER NOT NULL CHECK (has_misaligned_sink_edge IN (0, 1)),
    reaches_external_root  INTEGER NOT NULL CHECK (reaches_external_root IN (0, 1)),
    depth_truncated        INTEGER NOT NULL CHECK (depth_truncated IN (0, 1)),
    terminal_state         TEXT NOT NULL CHECK (terminal_state IN (
        'CLEAN_VERIFIED',
        'DRIFT_LOGGED',
        'QUARANTINED_IPI',
        'QUARANTINED_LAUNDERING',
        'REJECTED_STALE_EPOCH'
    )),
    error_class            TEXT CHECK (error_class IS NULL OR error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    path_digest_sha256     TEXT NOT NULL CHECK (length(path_digest_sha256) = 64),
    attestation_sha256     TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    recorded_at_utc        TEXT NOT NULL,
    CHECK (
        (classification = 'CLEAN_BENIGN' AND has_misaligned_sink_edge = 0 AND reaches_external_root = 0 AND depth_truncated = 0 AND terminal_state = 'CLEAN_VERIFIED' AND error_class IS NULL)
        OR
        (classification = 'BENIGN_AGENT_DRIFT' AND has_misaligned_sink_edge = 1 AND reaches_external_root = 0 AND depth_truncated = 0 AND terminal_state = 'DRIFT_LOGGED')
        OR
        (classification = 'IPI_CONFIRMED' AND (depth_truncated = 1 OR (has_misaligned_sink_edge = 1 AND reaches_external_root = 1)) AND terminal_state = 'QUARANTINED_IPI' AND error_class = 'SECURITY')
    )
);

CREATE TABLE IF NOT EXISTS provenance_quarantine (
    quarantine_id       TEXT PRIMARY KEY,
    trace_id            TEXT NOT NULL,
    session_id          TEXT NOT NULL,
    classification      TEXT NOT NULL CHECK (classification = 'IPI_CONFIRMED'),
    depth_truncated     INTEGER NOT NULL CHECK (depth_truncated IN (0, 1)),
    error_class         TEXT NOT NULL CHECK (error_class = 'SECURITY'),
    path_digest_sha256  TEXT NOT NULL CHECK (length(path_digest_sha256) = 64),
    attestation_sha256  TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    recorded_at_utc     TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS provenance_occ_ledger (
    ledger_seq          INTEGER PRIMARY KEY AUTOINCREMENT,
    scope_id            TEXT NOT NULL CHECK (length(scope_id) BETWEEN 4 AND 64),
    occ_version         INTEGER NOT NULL CHECK (occ_version >= 1),
    attestation_sha256  TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    recorded_at_utc     TEXT NOT NULL,
    UNIQUE (scope_id, occ_version)
);

CREATE TABLE IF NOT EXISTS epoch_freshness_scopes (
    scope_id            TEXT PRIMARY KEY CHECK (length(scope_id) BETWEEN 4 AND 64),
    last_consumed_k     INTEGER NOT NULL CHECK (last_consumed_k >= -1),
    occ_version         INTEGER NOT NULL DEFAULT 0 CHECK (occ_version >= 0),
    updated_at_utc      TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS epoch_freshness_quarantine (
    rejection_id        TEXT PRIMARY KEY,
    scope_id            TEXT NOT NULL CHECK (length(scope_id) BETWEEN 4 AND 64),
    attempted_epoch_k   INTEGER NOT NULL CHECK (attempted_epoch_k >= 0),
    last_consumed_k     INTEGER NOT NULL CHECK (last_consumed_k >= -1),
    error_class         TEXT NOT NULL CHECK (error_class IN ('BUSINESS', 'SECURITY')),
    reason              TEXT NOT NULL,
    attestation_sha256  TEXT NOT NULL CHECK (length(attestation_sha256) = 64),
    recorded_at_utc     TEXT NOT NULL
);

CREATE TRIGGER IF NOT EXISTS trg_provenance_occ_no_update
BEFORE UPDATE ON provenance_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'provenance_occ_ledger is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_provenance_occ_no_delete
BEFORE DELETE ON provenance_occ_ledger
BEGIN
    SELECT RAISE(ABORT, 'provenance_occ_ledger is append-only');
END;

CREATE TRIGGER IF NOT EXISTS trg_provenance_quarantine_no_update
BEFORE UPDATE ON provenance_quarantine
BEGIN
    SELECT RAISE(ABORT, 'provenance_quarantine is immutable');
END;

CREATE TRIGGER IF NOT EXISTS trg_epoch_quarantine_no_update
BEFORE UPDATE ON epoch_freshness_quarantine
BEGIN
    SELECT RAISE(ABORT, 'epoch_freshness_quarantine is immutable');
END;

CREATE INDEX IF NOT EXISTS idx_provenance_edges_session
    ON provenance_graph_edges (session_id, edge_seq);
CREATE INDEX IF NOT EXISTS idx_provenance_traces_session
    ON provenance_traces (session_id, recorded_at_utc);
CREATE INDEX IF NOT EXISTS idx_epoch_quarantine_scope
    ON epoch_freshness_quarantine (scope_id, recorded_at_utc);
