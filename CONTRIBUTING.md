# Contributing to `ctxfw`

Thank you for contributing to `ctxfw`! Every contribution must keep the local Open-Core perimeter deterministic, pure `LF`, `Zero-Egress`, and passing all architectural and security gates.

---

## 1. Local Development Setup

Python `3.10`–`3.13` is supported (`3.10` recommended for parity with standalone build matrices).

```bash
git clone https://github.com/heuristicolab/ctxfw.git
cd ctxfw
python -m venv .venv
# Linux / macOS: source .venv/bin/activate
# Windows PowerShell: .\.venv\Scripts\Activate.ps1
pip install -e ".[all,dev]"
```

Run the full test suite and diagnostics before making edits:

```bash
pytest tests/ -q
ctxfw doctor
ctxfw spec verify SPEC.axioms.md
```

---

## 2. Engineering & Architectural Guardrails

1. **Pure Open-Core Autonomy (`Apache 2.0`):** Never add external SaaS telemetry, cloud phone-home calls, hardcoded secrets, or proprietary client/partner names anywhere in `src/`, `tests/`, `benchmarks/`, or `docs/`.
2. **Axiomatic & `SWE-Gate` Discipline:**
   - Security-critical changes should map to formal invariants in [`SPEC.axioms.md`](SPEC.axioms.md) (`ACI >= 0.9000`, `>= 5` negative invariants).
   - Keep function changes small and shallow (`cyclomatic_delta <= 10`, zero `# type: ignore` suppressions, strict type annotations).
3. **Zero Benchmark Overfitting (*Zero Gaming*):** Never special-case test/benchmark string literals inside `src/ctxfw/`. Fix the underlying syntactic/lexical rule and test both benign controls and adversarial counterparts.
4. **Pure `LF` (`\n`) Line Endings:** Every source, test, SQL schema, JSON manifest, benchmark, and Markdown file must use pure `LF` (`0` `\r` bytes). `.gitattributes` enforces `-text` on critical assets—verify before committing on Windows.
5. **Pure `stdout` JSON-RPC (`AXIOM-1`):** Code executed under `ctxfw mcp` must never write debug logs or prints to `sys.stdout`; route diagnostics exclusively to `sys.stderr`.

---

## 3. Running Offline Verification Suites Before Opening a PR

```bash
# 1. Full unit, security, and docs parity suite
pytest tests/ -q

# 2. Verify repository PR gatekeeper (SWE-Gate)
ctxfw gate --staged

# 3. Verify offline security & accuracy benchmarks (zero egress)
python benchmarks/run_sara_security_benchmark.py --json
python benchmarks/run_wave2_v42_benchmark.py --json
python benchmarks/run_regulatory_ocr_benchmark.py --json
```

All PRs targeting `main` automatically run `tdd-attestation` (Python `3.10–3.13` + SQLite DDL compilation) and cross-platform standalone binary builds (`ubuntu-latest`, `macos-latest`, `windows-latest`) in [`.github/workflows/ci.yaml`](.github/workflows/ci.yaml).
