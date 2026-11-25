# `ctxfw` Documentation Index

Structured index following engineering documentation separation (Quickstart / How-To / Reference / Empirical Verification).

---

## Core Project & Governance

- **[README](../README.md)** — Quickstart (`pip install ctxfw`), capabilities, benchmark summary, MCP tools, and CLI overview.
- **[User Manual & Operations Runbook (`USER_MANUAL.md`)](../USER_MANUAL.md)** — Detailed setup for Claude Code/Desktop, Cursor, Windsurf, loopback HTTP proxy (`ctxfw proxy`), CI gates (`ctxfw gate` / `ctxfw ci`), and troubleshooting.
- **[Changelog (`CHANGELOG.md`)](../CHANGELOG.md)** — Version-by-version release history.
- **[Security Policy (`SECURITY.md`)](../SECURITY.md)** — Threat model boundaries (`Plano 0`), offline verification, and responsible vulnerability disclosure.
- **[Contributing Guide (`CONTRIBUTING.md`)](../CONTRIBUTING.md)** — Local environment setup, coding invariants, `LF` rules, and pre-PR verification commands.

---

## Formal Specifications & RFCs

- **[Formal Axiom Specification (`SPEC.axioms.md`)](../SPEC.axioms.md)** — Appendices A–L covering domain bounds, deterministic FSMs, 4-class error taxonomies, MCP burst guard limits, and non-negotiable negative invariants (`ACI = 1.0000`).
- **[Context Depth Configurator Spec](spec/CONTEXT_DEPTH_CONFIGURATOR.md)** — `D0`–`D3` pruning depth semantics and budget clamping.
- **[`D3` Ambient Manifest RFC](rfcs/RFC_D3_AMBIENT_MANIFEST_v40.md)** — Zero-syntax symbol cartography design.
- **[Architecture DAG Diagram](architecture/1_mermaid_dag.md)** — Dependency resolution flow diagram.

---

## Reproducible Empirical Benchmarks (`Zero-Egress`)

- **[Spanish Regulatory, Legal & Noisy OCR Benchmark (`SARA-RegDoc-60`, `v4.2.1`)](benchmarks/REGULATORY_LEGAL_OCR_BENCHMARK.md)** — 60-document benchmark (`30` adv / `30` benign controls: `100.00%` Recall, `0.00%` FPR, `-62.52%` OCR noise reduction) with transparent `v4.2.0 -> v4.2.1` root-cause trace.
- **[Wave 2 Security, Packaging & Latency Benchmark](benchmarks/WAVE2_V42_SECURITY_LATENCY_BENCHMARK.md)** — Empirical results across Blocks A–E (`mcp_guard`, `PASAC`, `TaskAuth`, `Cadence AIMD`, `TraceLite -82.43%`, `Snapshots`, multi-hop `Provenance`, 7-language + homoglyph hygiene) and live `stdio` parity.
- **[CTXFW vs. Cloud Runtime WAFs](benchmarks/SECURITY_VS_CLOUD_WAFS.md)** — Architectural comparison and 24-vector OWASP AISVS `C02-01` offline evaluation.
- **[Empirical Validation Trilogy (`zulip`, `posthog`, `airflow`)](benchmarks/TRILOGY_EMPIRICAL_BENCHMARK.md)** — Multi-depth AST compaction across large open-source repositories.
- **[Zulip Monolith A/B Report](benchmarks/ZULIP_MONOLITH_AB.md)** & **[D3 Empirical Benchmark Report](benchmarks/D3_EMPIRICAL_BENCHMARK_REPORT.md)** — Granular depth-level latency and token telemetry (`empirical_results_trilogy.json`).

---

## Production Case Studies

- **[Autonomous Red-Team MCP Defense & Deterministic Burst Hardening (2026-11-25, EN)](case-studies/redteam-mcp-defense-2026-11-25.md)** — Live production forensic breakdown of `571` HTTP requests (`568` WAL-audited) from an automated MCP fuzzer (`38` live `SARA` interventions + `252` gateway/schema blocks, `$0.0000 USD` LLM spend, `0` leaked secrets) and dual native hardening (`ctxfw v4.2.2` + `ctxfw-enterprise v1.0.2`).
- **[Defensa Autónoma contra Red-Team MCP y Rate Limiting Determinista (2026-11-25, ES)](case-studies/redteam-mcp-defense-2026-11-25.es.md)** — Edición en español del caso forense en producción y remediación multicapa.

---

## Detailed Release Notes

- [`v4.2.2`](RELEASE_NOTES_v4.2.2.md) · [`v4.2.1`](RELEASE_NOTES_v4.2.1.md) · [`v4.2.0`](RELEASE_NOTES_v4.2.0.md) · [`v4.1.0`](RELEASE_NOTES_v4.1.0.md) · [`v4.0.0`](RELEASE_NOTES_v4.0.0.md) · [`v3.9.1`](RELEASE_NOTES_v3.9.1.md) · [`v3.9.0`](RELEASE_NOTES_v3.9.0.md) · [`v3.8.0`](RELEASE_NOTES_v3.8.0.md) · [`v3.7.1`](RELEASE_NOTES_v3.7.1.md) · [`v3.6.0`](RELEASE_NOTES_v3.6.0.md)
