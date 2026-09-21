# Architectural Specification Brief: Elite Technical GTM Intelligence Agent & Dev-Tools Scout (ctxfw)

## 1. Domain Entities & Bounded Variables
Deterministic runtime bounds for discovery, screening, and intelligence generation:
- Variable `min_forum_activity_posts_per_day`: integer bounded >= 10 and <= 1000 posts/day.
- Variable `max_showcase_response_window_min`: integer bounded >= 15 and <= 120 minutes.
- Variable `token_reduction_benchmark_floor_pct`: float bounded >= 50.0 and <= 95.0 percent.
- Variable `max_target_channels_per_vector`: integer bounded >= 5 and <= 50 channels.
- Variable `max_outreach_attempts_per_lead`: integer bounded >= 1 and <= 3 attempts.
- Variable `benchmark_execution_timeout_sec`: integer bounded >= 1 and <= 60 seconds.
Bounds: 6 / 6

## 2. Deterministic State Machine (FSM)
Lifecycle states and transition map $\delta(S, E)$ governing the intelligence scout execution:
- States: `IDLE`, `VECTOR_SCANNING`, `INVARIANT_SCREENING`, `DOSSIER_SYNTHESIS`, `QUARANTINED`, `COMPLETED`
- Transition $\delta(\text{IDLE}, \text{START_MAPPING}) \to \text{VECTOR_SCANNING}$
- Transition $\delta(\text{VECTOR_SCANNING}, \text{CHANNELS_DISCOVERED}) \to \text{INVARIANT_SCREENING}$
- Transition $\delta(\text{INVARIANT_SCREENING}, \text{INVARIANT_VIOLATION}) \to \text{QUARANTINED}$
- Transition $\delta(\text{INVARIANT_SCREENING}, \text{SCREENING_PASSED}) \to \text{DOSSIER_SYNTHESIS}$
- Transition $\delta(\text{DOSSIER_SYNTHESIS}, \text{DOSSIER_VERIFIED}) \to \text{COMPLETED}$
- Transition $\delta(\text{QUARANTINED}, \text{REMEDIATE_FILTERS}) \to \text{VECTOR_SCANNING}$
- Terminal States: `COMPLETED`, `QUARANTINED`.

## 3. Error Taxonomy & Quarantine
Formal error taxonomy isolating 4 discrete fault domains with explicit routing:
- Class 1 (Transient Fault): HTTP rate limits (429), API socket timeout during vector search -> Exponential backoff with jitter (max 3 retries).
- Class 2 (Deterministic Fault): Schema parse error in forum metadata or dead URL -> Divert suspect channel directly to quarantine sink; continue scanning remaining channels.
- Class 3 (Business & Specification Violation): Discovery candidate violates activity threshold (<10 posts/day) or uses generic growth-hacking tactics -> Immediate exclusion invariant rejection.
- Class 4 (Security & Isolation Violation): Telemetry egress attempt, unencrypted credential leak, or automated unauthorized spam posting -> Immediate halt, forensic audit log emission, and process quarantine.

## 4. Formal Proof & Cryptographic Attestation
Formal proof included: Mathematical induction validates inductive invariance across FSM state transitions, ensuring no channel violating exclusion invariants can transition into `DOSSIER_SYNTHESIS` or `COMPLETED`.
Deterministic SHA-256 attestation seal guarantees manifest immutability by hashing lexicographically sorted negative invariants.

## 5. Negative Invariants (Floor of 5 Required)
- System shall never recommend generic "growth hacking" tactics, SEO content farms, broad LinkedIn groups, or generic Medium publications.
- System shall never include dead forums, inactive subreddits (<10 active posts/day), or spam-heavy Discord servers.
- System shall never propose paid PR wire releases (e.g., PR Newswire, BusinessWire).
- System shall never transmit unencrypted codebases, unpruned AST tokens, or telemetry egress to remote endpoints without explicit local isolation.
- Agent shall never execute automated bulk spam posting or uninvited sales pitches violating platform anti-self-promotion rules or the zero-friction "Show, Don't Sell" doctrine.
- System shall never issue marketing claims using unverified corporate superlatives ("revolutionary", "game-changer") without attaching empirical benchmark reproducibility data.
