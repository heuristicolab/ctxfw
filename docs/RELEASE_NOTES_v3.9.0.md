# Release Notes: ctxfw v3.9.0

`ctxfw v3.9.0` introduces **$D_3$ Ambient Cartography & Depth Configuration**, headless CI/CD automation infrastructure, formal Appendix D axiomatic verification (ACI 1.0000), and ultra-lean isolated packaging distribution.

---

## What's New in v3.9.0

### 1. $D_3$ Ambient Cartography Engine & Depth Configurator
* Introduces topological level 3 ($D_3$) ambient symbol cartography for multi-hop repository comprehension.
* Enforces a strict 1,000-token ceiling on ambient manifests and distractor budget capping ($\le 500$ symbols).
* Dynamic quarantine mechanism flagging PEP 562 `__getattr__` and dynamic `__all__` namespaces with `[DYNAMIC_UNBOUND:?]` to prevent LLM absence hallucinations (AXIOM-17).
* In-memory L1 cache and SQLite WAL indexing ensuring P95 resolution latency $\le 25\text{ ms}$ with bounded synchronous fallback (AXIOM-18).

### 2. Headless B2A CI/CD Infrastructure
* **Static CI Markdown Emitter:** `ctxfw report --ci-markdown` invokes `CIGatekeeper` to emit PR dependency analysis and FinOps token economics directly to stdout or `--output pr_summary.md` with zero external API or network dependencies.
* **Official Composite GitHub Action:** Deployed at `.github/actions/setup-ctxfw/action.yml` for zero-touch initialization in headless Linux/macOS/Windows runners, featuring dependency caching on `~/.cache/ctxfw` and atomic verification.

### 3. Appendix D Axiomatic Attestation (ACI 1.0000)
* Formally incorporates **AXIOM-17 through AXIOM-21** into `SPEC.axioms.md`.
* Certified **ACI Score 1.0000** over 18 negative invariants with SHA-256 attestation hash `9845b97331f39b4cb728b0702dd5b56693b5588c1d129a35a9843d5b8ad8d3ca`.
* Zero-Egress contract verified: zero network telemetry leaves the host machine.

### 4. Canonical Distribution & Clean Packaging Shield
* Migrated build backend strictly to `hatchling` with explicit sdist/wheel packaging boundaries.
* Distribution wheel size maintained at < 0.1 MB (well below the 2 MB SLA) with zero leakage of test suites, empirical benchmarks, or local SQLite ledgers.
* Local ledger integrity verification utility (`scripts/checkpoint.py --verify-ledger`).

### 5. Deterministic Test Suite
* Full suite of **180/180 tests passing (100% green)** with zero regressions.

---

## Upgrade & Verification

```bash
# Upgrade via PyPI
pip install --upgrade ctxfw

# Verify version
ctxfw --version  # Output: ctxfw 3.9.0

# Verify specification seal
ctxfw spec verify SPEC.axioms.md

# Run local ledger integrity attestation
python scripts/checkpoint.py --verify-ledger
```
