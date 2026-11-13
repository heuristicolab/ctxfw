-- manifest_hash: ebbcd0d607fa09a71dda690ea76104d762b3f279cde258f64917421d39a249f4
-- sealed_blueprint_manifest_hash: da52eae13ef720cd4f56f1f3a3c295b7800aeb9585d8b92e346529e90bf4dc95
-- blueprint_id: BP-SIG-97BA08207ECA7295-PROACTIVE-AGENT-ASSURANCE-GATE
-- signal_id: SIG-97ba08207eca7295 | proposal_id: PROP-97ba08207eca7295-H2

PRAGMA journal_mode = WAL;
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS assurance_scope_contracts (
    session_id TEXT PRIMARY KEY CHECK (typeof(session_id) = 'text' AND length(session_id) BETWEEN 10 AND 54),
    proposal_ref TEXT NOT NULL CHECK (length(proposal_ref) = 24),
    egress_mode TEXT NOT NULL CHECK (egress_mode IN ('OFFLINE_ISOLATED', 'ALLOWLISTED_PROXY', 'REPLAY_HERMETIC')),
    live_egress_detected INTEGER NOT NULL CHECK (live_egress_detected IN (0, 1)),
    cross_run_writable INTEGER NOT NULL CHECK (cross_run_writable = 0),
    signoff_role TEXT NOT NULL CHECK (signoff_role IN ('PROGRAM_OWNER', 'ENVIRONMENT_OWNER', 'SECURITY_LEAD', 'INCIDENT_LEAD')),
    preflight_status TEXT NOT NULL CHECK (preflight_status IN ('VALID', 'FAILED', 'PENDING')),
    lifecycle_state TEXT NOT NULL CHECK (lifecycle_state IN (
        'ANTICIPATE_DRAFT', 'CONSTRAINED_CONTRACT', 'PREFLIGHT_VERIFIED', 'ACTIVE_OBSERVED',
        'ELEVATED_REVIEW', 'CONTAINMENT_HALTED', 'REAUTHORIZED_COMPLETE', 'QUARANTINED_BREACH'
    )),
    contract_digest TEXT NOT NULL CHECK (length(contract_digest) = 64)
);

CREATE TABLE IF NOT EXISTS boundary_assurance_probes (
    probe_id TEXT PRIMARY KEY CHECK (length(probe_id) BETWEEN 8 AND 44),
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    b_scope REAL NOT NULL CHECK (b_scope >= 0.0 AND b_scope <= 1.0),
    b_identity REAL NOT NULL CHECK (b_identity >= 0.0 AND b_identity <= 1.0),
    b_network REAL NOT NULL CHECK (b_network >= 0.0 AND b_network <= 1.0),
    b_storage REAL NOT NULL CHECK (b_storage >= 0.0 AND b_storage <= 1.0),
    b_monitor REAL NOT NULL CHECK (b_monitor >= 0.0 AND b_monitor <= 1.0),
    b_response REAL NOT NULL CHECK (b_response >= 0.0 AND b_response <= 1.0),
    min_layer_floor REAL NOT NULL CHECK (min_layer_floor >= 0.10 AND min_layer_floor <= 0.99)
);

CREATE TABLE IF NOT EXISTS agent_risk_telemetry (
    telemetry_id TEXT PRIMARY KEY CHECK (length(telemetry_id) BETWEEN 9 AND 45),
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    task_generality_g REAL NOT NULL CHECK (task_generality_g >= 0.0 AND task_generality_g <= 1.0),
    agent_capability_c REAL NOT NULL CHECK (agent_capability_c >= 0.0 AND agent_capability_c <= 1.0),
    external_exposure_e REAL NOT NULL CHECK (external_exposure_e >= 0.0 AND external_exposure_e <= 1.0),
    scope_weakness_s REAL NOT NULL CHECK (scope_weakness_s >= 0.0 AND scope_weakness_s <= 1.0),
    monitoring_strength_m REAL NOT NULL CHECK (monitoring_strength_m >= 0.0 AND monitoring_strength_m <= 1.0),
    response_speed_r REAL NOT NULL CHECK (response_speed_r >= 0.0 AND response_speed_r <= 1.0),
    hazard_l_t REAL NOT NULL CHECK (hazard_l_t >= 0.0 AND hazard_l_t <= 1.0),
    tau_review REAL NOT NULL CHECK (tau_review >= 0.01 AND tau_review <= 0.90),
    tau_stop REAL NOT NULL CHECK (tau_stop >= 0.02 AND tau_stop <= 1.0 AND tau_review < tau_stop)
);

CREATE TABLE IF NOT EXISTS pep_enforcement_decisions (
    decision_code TEXT PRIMARY KEY CHECK (length(decision_code) BETWEEN 8 AND 44),
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    in_authorized_scope INTEGER NOT NULL CHECK (in_authorized_scope IN (0, 1)),
    resource_whitelisted INTEGER NOT NULL CHECK (resource_whitelisted IN (0, 1)),
    action_risk REAL NOT NULL CHECK (action_risk >= 0.0 AND action_risk <= 1.0),
    risk_threshold REAL NOT NULL CHECK (risk_threshold >= 0.01 AND risk_threshold <= 1.0),
    allow_action INTEGER NOT NULL CHECK (allow_action IN (0, 1)),
    hazard_regime TEXT NOT NULL CHECK (hazard_regime IN ('NOMINAL_ALLOW', 'REVIEW_PAUSE', 'SYNCHRONOUS_STOP')),
    conservative_assurance REAL NOT NULL CHECK (conservative_assurance >= 0.0 AND conservative_assurance <= 1.0),
    manifest_hash TEXT NOT NULL CHECK (length(manifest_hash) = 64)
);

CREATE TABLE IF NOT EXISTS reauthorization_signoffs (
    signoff_code TEXT PRIMARY KEY CHECK (length(signoff_code) BETWEEN 8 AND 44),
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    accountability_role TEXT NOT NULL CHECK (accountability_role IN ('PROGRAM_OWNER', 'ENVIRONMENT_OWNER', 'SECURITY_LEAD', 'INCIDENT_LEAD')),
    approval_rationale TEXT NOT NULL CHECK (length(approval_rationale) BETWEEN 8 AND 240),
    approved_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now'))
);

CREATE TABLE IF NOT EXISTS occ_version_ledger (
    occ_id INTEGER PRIMARY KEY AUTOINCREMENT,
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    occ_version INTEGER NOT NULL CHECK (occ_version >= 1),
    contract_digest TEXT NOT NULL CHECK (length(contract_digest) = 64),
    manifest_hash TEXT NOT NULL CHECK (length(manifest_hash) = 64),
    recorded_utc TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%SZ', 'now')),
    UNIQUE (session_id, occ_version)
);

CREATE TABLE IF NOT EXISTS assurance_breach_quarantine (
    alert_id TEXT PRIMARY KEY CHECK (length(alert_id) BETWEEN 9 AND 45),
    session_id TEXT NOT NULL REFERENCES assurance_scope_contracts(session_id) ON DELETE CASCADE,
    error_class TEXT NOT NULL CHECK (error_class IN ('TRANSIENT', 'DETERMINISTIC', 'BUSINESS', 'SECURITY')),
    assigned_role TEXT NOT NULL CHECK (assigned_role IN ('PROGRAM_OWNER', 'ENVIRONMENT_OWNER', 'SECURITY_LEAD', 'INCIDENT_LEAD')),
    incident_summary TEXT NOT NULL CHECK (length(incident_summary) BETWEEN 8 AND 240),
    occ_version INTEGER NOT NULL CHECK (occ_version >= 1)
);

CREATE TRIGGER IF NOT EXISTS trg_occ_version_ledger_no_update
BEFORE UPDATE ON occ_version_ledger
BEGIN
    SELECT RAISE(ABORT, 'Immutable ledger: occ_version_ledger updates are prohibited');
END;

CREATE TRIGGER IF NOT EXISTS trg_breach_quarantine_no_update
BEFORE UPDATE ON assurance_breach_quarantine
BEGIN
    SELECT RAISE(ABORT, 'Immutable ledger: assurance_breach_quarantine updates are prohibited');
END;

CREATE TRIGGER IF NOT EXISTS trg_pep_decisions_no_update
BEFORE UPDATE ON pep_enforcement_decisions
BEGIN
    SELECT RAISE(ABORT, 'Immutable audit: pep_enforcement_decisions updates are prohibited');
END;

CREATE INDEX IF NOT EXISTS idx_bas_probes_session
    ON boundary_assurance_probes (session_id, min_layer_floor);

CREATE INDEX IF NOT EXISTS idx_pep_decisions_allow
    ON pep_enforcement_decisions (session_id, allow_action, hazard_regime);

CREATE INDEX IF NOT EXISTS idx_quarantine_session_class
    ON assurance_breach_quarantine (session_id, error_class);
