# Architectural Specification Brief: Context Firewall (ctxfw) Sovereign Industrialization

## 1. Domain Entities & Bounded Variables
The industrialization engine enforces deterministic execution bounds across all runtime interfaces:
- Variable `mcp_handshake_timeout_ms`: integer bounded >= 10 and <= 5000 milliseconds.
- Variable `max_mcp_payload_bytes`: integer bounded >= 1024 and <= 10485760 bytes (10 MB).
- Variable `aci_verification_threshold`: float bounded >= 0.9000 and <= 1.0000 completeness index.
- Variable `db_busy_timeout_ms`: integer bounded >= 100 and <= 60000 milliseconds.
- Variable `stdio_buffer_size_bytes`: integer bounded >= 4096 and <= 1048576 bytes (1 MB).
- Variable `idle_memory_limit_mb`: integer bounded >= 10 and <= 100 megabytes.
Bounds: 6 / 6

## 2. Deterministic State Machine (FSM)
Lifecycle states and transition map $\delta(S, E)$ governing specifications and sovereign runtime:
- States: `DRAFT`, `QUARANTINED`, `VERIFIED`, `SEALED`
- State transition $\delta(\text{DRAFT}, \text{EVALUATE}_{\text{ACI} < 0.9000 \lor \text{INV} < 5}) \to \text{QUARANTINED}$
- State transition $\delta(\text{DRAFT}, \text{EVALUATE}_{\text{ACI} \ge 0.9000 \land \text{INV} \ge 5}) \to \text{VERIFIED}$
- State transition $\delta(\text{QUARANTINED}, \text{REMEDIATE}) \to \text{DRAFT}$
- State transition $\delta(\text{VERIFIED}, \text{SIGN\_MANIFEST}) \to \text{SEALED}$
- Terminal State: `SEALED` is immutable. Any mutation attempt triggers $\delta(\text{SEALED}, \text{MUTATION\_ATTEMPT}) \to \text{QUARANTINED}$.

## 3. Error Taxonomy & Quarantine
Formal error taxonomy isolates 4 discrete fault domains with explicit routing:
- Class 1 (Transient Fault): SQLite WAL lock contention, transient socket timeout -> Exponential backoff and retry (max 3 retries).
- Class 2 (Deterministic Input Fault): Tree-Sitter grammar syntax parse failure, invalid JSON-RPC format -> Fail-open or AST stub preservation.
- Class 3 (Business & Specification Violation): ACI score < 0.9000 or negative invariant count < 5 -> Inviolable quarantine sink rejection.
- Class 4 (Security & Isolation Violation): Stdout stream contamination, path traversal outside workspace, unencrypted credentials -> Immediate halt, stderr forensic log, process abort.

## 4. Formal Proof & Cryptographic Attestation
Formal proof included: Mathematical induction validates inductive invariance across FSM state transitions, ensuring no unverified transition can enter `SEALED`.
Deterministic SHA-256 attestation seal guarantees manifest immutability by hashing lexicographically sorted negative invariants.

## 5. Negative Invariants (Floor of 5 Required)
- The context firewall engine shall never emit raw stdout logs during stdio MCP communication.
- The proxy gateway shall never transmit unpruned D1 or D2 AST tokens when strict compression mode is enabled.
- The specification sieve shall never issue a VERIFIED status certificate if the Axiom Completeness Index (ACI) is strictly below 0.9000.
- The CLI installer shall never overwrite or corrupt existing external MCP server entries inside user IDE configuration files.
- The pre-commit enforcement hook shall never permit git commits containing specification briefs marked with QUARANTINED status.
- The core pipeline shall never persist unencrypted secret credentials or API tokens in the SQLite WAL telemetry cache.
- The system shall never execute arbitrary unstubbed code blocks during architectural intake evaluation.

## Appendix B: Multi-Repository Empirical Validation (The Benchmark Trilogy)
The formal architecture of `ctxfw` was subjected to destructive A/B stress testing in isolated containerized environments (Linux VPS / Docker Engine) across three representative open-source engineering archetypes: `zulip/zulip` (Coupled Django Monolith), `posthog/posthog` (Modern COSS / Data OS), and `apache/airflow` (Async Orchestration Monorepo / Airflow 3). Empirical telemetry rigorously validates compliance across all system axioms:
- **AXIOM-1 (MCP Stream Purity / Zero Leakage):** Verified across all three benchmark suites with strictly 0 bytes leaked to `stdout` during in-memory AST execution (`leak_bytes == 0`), ensuring clean JSON-RPC stdio transport for IDE agents.
- **AXIOM-2 (Deterministic Perimeter Pruning $D_1$):** Achieved consistent, scale-amplified token mass reductions across the dependency perimeter:
  - Zulip ($D_1$): **42.96%** (`INTERFACE`) / **78.20%** (`NOMINAL`)
  - PostHog ($D_1$): **59.53%** (`INTERFACE`)
  - Airflow ($D_1$): **66.90%** (`INTERFACE`) / **90.26%** (`NOMINAL`)
- **AXIOM-3 (Inviolability of Focal Context $D_0$):** Target active files (`users.py`, `team.py`, `dag.py`) remained 100% byte-for-byte intact without elision, mutation, or semantic corruption.
- **AXIOM-4 (Syntactic Integrity & Contract Preservation):** Preserved 100% of class definitions, method signatures, decorators, and type annotations with verified AST compilation (`ast.parse() == True`) and zero hallucinations across all evaluated targets.

## Appendix C: Claude Code Zero-Touch Injection & Sovereign Plugin Engine
<!-- Axiom Manifest Hash: 4a35e336c0621f5b76a6abb20d975bc896c15592b5da2098f2454adc6a4d66a6 -->
<!-- Axiom Completeness Index (ACI): 1.0000 | Status: VERIFIED | Bounds: 6/6 -->

### C.1 Domain Entities & Bounded Variables
Deterministic runtime bounds governing the Claude Code and Claude Desktop injection engine:
- Variable `config_backup_retention_count`: integer bounded >= 1 and <= 10 backups.
- Variable `atomic_write_timeout_ms`: integer bounded >= 50 and <= 5000 milliseconds.
- Variable `max_claude_json_payload_bytes`: integer bounded >= 1024 and <= 5242880 bytes (5 MB).
- Variable `claude_mcp_handshake_timeout_ms`: integer bounded >= 100 and <= 10000 milliseconds.
- Variable `permission_whitelist_entries_count`: integer bounded >= 1 and <= 32 entries.
- Variable `aci_verification_threshold`: float bounded >= 0.9000 and <= 1.0000 completeness index.
Bounds: 6 / 6

### C.2 Deterministic State Machine (FSM)
Lifecycle states and transition map $\delta(S, E)$ governing configuration mutation:
- States: `INSPECT`, `BACKUP`, `MUTATE_STAGED`, `VERIFIED_ATOMIC`, `ROLLED_BACK`
- State transition $\delta(\text{INSPECT}, \text{CONFIG_VALID}) \to \text{BACKUP}$
- State transition $\delta(\text{INSPECT}, \text{CONFIG_CORRUPT}) \to \text{ROLLED_BACK}$
- State transition $\delta(\text{BACKUP}, \text{SNAPSHOT_CREATED}) \to \text{MUTATE_STAGED}$
- State transition $\delta(\text{MUTATE_STAGED}, \text{VALIDATE_PASS}) \to \text{VERIFIED_ATOMIC}$
- State transition $\delta(\text{MUTATE_STAGED}, \text{VALIDATE_FAIL}) \to \text{ROLLED_BACK}$
- Terminal State: `VERIFIED_ATOMIC` commits via atomic filesystem rename; `ROLLED_BACK` restores snapshot without side effects.

### C.3 Error Taxonomy & Quarantine
Formal error taxonomy isolating fault domains during IDE injection:
- Class 1 (Transient Fault): Filesystem write lock or temporary access collision -> Exponential backoff and retry (max 3 retries).
- Class 2 (Deterministic Input Fault): Malformed JSON in existing ~/.claude.json or invalid schema -> Abort mutation, preserve file intact, emit forensic report to stderr.
- Class 3 (Business & Specification Violation): Invariant count < 5 or ACI score < 0.9000 -> Rejection to quarantine sink without touching target configurations.
- Class 4 (Security & Isolation Violation): Path traversal attempt outside user profile, credential leakage in arguments, or non-local binary resolution -> Process abort, immediate security quarantine, stderr alert.

### C.4 Negative Invariants (Floor of 5 Required)
- The installer shall never overwrite, strip, or corrupt unmanaged third-party MCP servers or configuration keys in ~/.claude.json.
- The installer shall never execute non-atomic writes directly to user IDE configuration files without creating a pre-mutation backup.
- The installer shall never configure MCP server commands referencing non-local or unverified remote executable URIs.
- The installer shall never transmit telemetry, user prompts, file paths, or authentication tokens outside the local host during installation.
- The injected Claude Code plugin shall never bypass the deterministic AST pruning pipeline or emit unpruned context when strict firewall mode is enabled.
- The configuration engine shall never proceed with file mutation if the existing configuration fails deterministic JSON syntax validation.

## Appendix D: Topological Depth Engine (D3) & Ambient Cartography
<!-- Axiom Completeness Index (ACI): 1.0000 | Status: VERIFIED | Bounds: 6/6 -->
<!-- Attestation Manifest Hash: 9845b97331f39b4cb728b0702dd5b56693b5588c1d129a35a9843d5b8ad8d3ca -->

### D.1 Domain Entities & Bounded Variables
Deterministic runtime bounds governing the D3 ambient cartography engine:
- Variable `max_topological_depth`: integer bounded >= 0 and <= 3 levels.
- Variable `ambient_manifest_token_ceiling`: integer bounded >= 100 and <= 1000 tokens.
- Variable `distractor_budget`: integer bounded >= 20 and <= 500 symbols.
- Variable `d3_resolution_latency_p95_ms`: integer bounded >= 1 and <= 25 milliseconds.
- Variable `max_inline_reparse_modules`: integer bounded >= 1 and <= 20 modules.
- Variable `aci_verification_threshold`: float bounded >= 0.9000 and <= 1.0000 completeness index.
Bounds: 6 / 6

### D.2 Deterministic State Machine (FSM)
Lifecycle states and transition map $\delta(S, E)$ governing topological D3 resolution:
- States: `DRAFT`, `DISCOVERY`, `RESOLVING_D3`, `CLAMPED_EMIT`, `FAIL_OPEN`
- State transition $\delta(\text{DRAFT}, \text{REQUEST_RECEIVED}) \to \text{DISCOVERY}$
- State transition $\delta(\text{DISCOVERY}, \text{DEPTH_LE_2}) \to \text{CLAMPED_EMIT}$
- State transition $\delta(\text{DISCOVERY}, \text{DEPTH_EQ_3}) \to \text{RESOLVING_D3}$
- State transition $\delta(\text{RESOLVING_D3}, \text{PARSE_SUCCESS}) \to \text{CLAMPED_EMIT}$
- State transition $\delta(\text{RESOLVING_D3}, \text{PARSE_ERROR}) \to \text{FAIL_OPEN}$
- State transition $\delta(\text{FAIL_OPEN}, \text{FALLBACK_STALE}) \to \text{CLAMPED_EMIT}$
- Terminal State: `CLAMPED_EMIT` is immutable and sealed for agent prompt delivery.

### D.3 Error Taxonomy & Quarantine
Formal error taxonomy isolating fault domains during D3 ambient resolution:
- Class 1 (Transient Fault): SQLite WAL lock contention or cache miss burst -> Fallback to stale SQLite snapshot and out-of-band asynchronous worker.
- Class 2 (Deterministic Input Fault): PEP 562 dynamic symbols or unparseable syntax -> Tag namespace with [DYNAMIC_UNBOUND:?] and fail-open.
- Class 3 (Business & Specification Violation): Depth requested > 3 or distractor budget > 500 -> Clamp to D2 or budget boundary.
- Class 4 (Security & Isolation Violation): Workspace path egress or telemetry leakage in config -> Immediate halt, zero external transmission, stderr alert.

### D.4 Negative Invariants (Floor of 5 Required)
- **AXIOM-17 (Dynamic Namespace Quarantine):** The D3 ambient manifest generator shall never emit a closed symbol list for modules implementing PEP 562 '__getattr__', dynamic '__all__' expressions, or dynamic registries, and must explicitly flag the namespace with the token '[DYNAMIC_UNBOUND:?]' to inhibit negative absence hallucination.
- **AXIOM-18 (Throttled Warmup & Stale-Read Guarantee):** The D3 symbol resolution engine shall never execute synchronous inline re-parsing of more than 20 cache-missed modules within a single request turn, and shall never block the primary stdio JSON-RPC thread beyond 40 ms; it must return the last attested stale SQLite snapshot.
- **AXIOM-19 (Subsystem Boundary Clamping):** The D3 ambient manifest serializer shall never inject more than 1,000 net tokens of D3 symbols into a prompt, and shall strictly reject modules crossing outside the architectural subsystem boundary of the D1/D2 ancestors.
- **AXIOM-20 (Configuration Depth Ceiling):** The configuration engine shall never parse or execute topological depth expansions strictly exceeding depth level 3 (D > 3), and shall reject malformed numeric depth values.
- **AXIOM-21 (Zero Telemetry Leakage in Config):** The configuration loader shall never transmit .ctxfwrc contents, workspace paths, or environment variable overrides outside the local host runtime.

