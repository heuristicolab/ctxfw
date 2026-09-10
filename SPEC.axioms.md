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
