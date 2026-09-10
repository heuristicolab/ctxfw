<div align="center">

# CTXFW // CONTEXT FIREWALL
### High-Assurance Axiomatic Gatekeeper for Synthetic Code Intelligence

[![Axiomatic Completeness Index](https://img.shields.io/badge/ACI-1.0000_VERIFIED-000000?style=for-the-badge&logo=shield)](https://github.com/)
[![Specification Seal](https://img.shields.io/badge/ATTESTATION-SHA--256_SEALED-0a0a0a?style=for-the-badge&logo=auth0)](https://github.com/)
[![Runtime Engine](https://img.shields.io/badge/RUNTIME-PYTHON_3.10+-111111?style=for-the-badge&logo=python)](https://github.com/)
[![License](https://img.shields.io/badge/LICENSE-PROPRIETARY_BETA-black?style=for-the-badge)](LICENSE)

**The deterministic boundary between generative AI hallucinations and mission-critical infrastructure.**

[Architecture](#architectural-perimeter) • [Technical Capabilities](#technical-capabilities) • [Zero-Touch Onboarding](#quickstart-the-2-minute-verification) • [Enterprise Compliance](#enterprise-compliance-mapping)

---

</div>

## Executive Abstract

Modern LLM-assisted development introduces catastrophic probabilistic risk: autonomous agents generate plausible, unverified architectures violating core security invariants, transaction idempotency, and regulatory boundaries. 

**CTXFW** is an out-of-band, deterministic context firewall and Model Context Protocol (MCP) gatekeeper. It intercepts architectural intake, enforces a mathematical floor on negative invariants ($N \ge 5$), binds variable domains, and cryptographically signs validated specification manifests. 

> **Core Doctrine:** No synthetic code enters the repository without a verified axiomatic certificate ($\text{ACI} \ge 0.9000$).

---

## Architectural Perimeter

```
PROBABILISTIC DOMAIN                      DETERMINISTIC PERIMETER
┌───────────────────────┐                  ┌────────────────────────────────────────┐
│  Autonomous AI Agent  │                  │             CTXFW ENGINE               │
│  (Claude / Gemini /   │                  │                                        │
│   Cursor / Antigravity│                  │  ┌──────────────────────────────────┐  │
└───────────┬───────────┘                  │  │     Axiomatic Sieve Engine       │  │
            │                              │  │  - Negative Invariant Floor      │  │
            │  Intake Brief                │  │  - Bounded Variable Ranges       │  │
            ▼                              │  │  - Deterministic FSM Delta       │  │
┌───────────────────────┐                  │  │  - 4-Class Error Taxonomy        │  │
│ MCP Stdio Interceptor ├─────────────────►│  └────────────────┬─────────────────┘  │
└───────────────────────┘                  │                   │                    │
                                           │                   ▼                    │
                                           │         [ ACI >= 0.9000? ]             │
                                           │          /              \              │
                                           │       YES                NO            │
                                           │        │                  │            │
                                           │        ▼                  ▼            │
                                           │ ┌──────────────┐   ┌─────────────────┐ │
                                           │ │ VERIFIED     │   │ QUARANTINED     │ │
                                           │ │ SHA-256 Seal │   │ Execution Halt  │ │
                                           │ └──────┬───────┘   └────────┬────────┘ │
                                           └────────┼────────────────────┼──────────┘
                                                    │                    │
                                                    ▼                    ▼
                                           [ Code Generation ]   [ Forensic Report ]
                                           [ & Git Permitted ]   [ Pre-Commit Abort]
```

---

## Technical Capabilities

### 1. Axiomatic Specification Sieve
* **Negative Invariants Floor**: Enforces non-negotiable negative clauses (`shall never` or `never`) preventing silent security degradation (e.g., plaintext PAN/PIN, unvalidated idempotency, untrusted state transitions).
* **Deterministic State Machine (FSM)**: Requires formal state transition definitions $\delta(S, E) \rightarrow S'$ and explicit terminal states before backend synthesis.
* **4-Class Fault Domain Taxonomy**: Strict segregation into Transient (Class 1), Deterministic Client (Class 2), Semantic Business (Class 3), and Security Isolation (Class 4) quarantine sinks.

### 2. Zero-Touch Toolchain Integration
* **Multi-IDE Auto-Discovery**: Automatic environment detection and non-destructive injection for **Google Antigravity**, **Cursor**, and **Claude Desktop**.
* **Safe Configuration Merge**: Idempotent configuration management (`safe_merge`) with strict third-party MCP server preservation.
* **Local Repository Armor**: Automated deployment of `.git/hooks/pre-commit` gatekeeper preventing unverified commits.

### 3. Cryptographic Attestation
* Every verified brief generates an immutable SHA-256 digest (`manifest_hash`) computed over lexicographically sorted negative invariants.
* Enforces provenance: all generated artifacts must embed the attestation seal in their source header.

---

## Quickstart: The 2-Minute Verification

### Installation
Install the pre-built distribution wheel or source package:
```bash
pip install dist/ctxfw-3.5.0-py3-none-any.whl
# or via pipx for global isolation:
pipx install .
```

### 1. System Health & Stream Isolation Audit
Run the diagnostic suite to certify your local runtime and verify stdio channel purity:
```bash
ctxfw doctor
```

### 2. Global IDE Provisioning
Inject the axiomatic gateway directives and MCP endpoints into all detected IDEs:
```bash
ctxfw init --global
```

### 3. Repository Perimeter Armor
Activate the pre-commit gatekeeper and deploy canonical axioms into your project:
```bash
cd /path/to/your/project
ctxfw init --repo .
```

---

## Enterprise Compliance Mapping

CTXFW automates compliance requirements for organizations operating under rigorous audit frameworks:

| Standard | Clause / Control | CTXFW Enforcement Mechanism |
| :--- | :--- | :--- |
| **PCI-DSS v4.0** | Req 3.4 & 6.4 | Pre-code invariant checking: rejects any brief permitting plaintext PAN/CVV storage or unmasked logging. |
| **SOC 2 Type II** | CC6.6 & CC7.1 | Mathematical attestation manifests provide non-repudiable audit logs of code generation inputs and invariants. |
| **EU AI Act** | Article 14 (Human Oversight) | Prevents runaway autonomous code generation by forcing formal spec sign-off gates and quarantine sinks. |
| **DORA (EU)** | ICT Risk Management | Fault domain taxonomy enforces explicit resilience classification and circuit-breaking on all service endpoints. |

---

## Distributed Toolchain Components

The distribution binary provides dedicated console entrypoints for continuous integration and runtime defense:

* `ctxfw`: Unified operational CLI (Distance-0 context compiler and subcommand dispatcher).
* `ctxfw-doctor`: High-assurance environment, stdio stream isolation, and integrity diagnostics.
* `ctxfw-init`: Automated zero-touch global IDE and repository perimeter provisioner.
* `ctxfw-mcp`: Zero-latency JSON-RPC 2.0 stdio protocol server for AI agents.
* `ctxfw-ci`: Headless compliance gatekeeper for CI/CD pipelines (GitHub Actions, Gitea, GitLab CI).
* `ctxfw-audit`: Ledger auditor for cryptographic attestation manifests and token telemetry.
* `ctxfw-proxy`: Local perimeter reverse proxy gateway with streaming SSE compression.
