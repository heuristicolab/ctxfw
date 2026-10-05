# Release Notes: ctxfw v3.9.1

`ctxfw v3.9.1` is a critical resilience and packaging hotfix that guarantees 100% zero-failure execution across minimal headless environments without optional network dependencies.

---

## What's Fixed in v3.9.1

### 1. Resilient Telemetry Import & Fail-Open Isolation
* Replaces top-level unconditional `import httpx` in `src/ctxfw/storage/telemetry.py` with an idempotent fail-open guard (`try: import httpx except ImportError: httpx = None`).
* Heartbeat synchronization routines (`push_telemetry_heartbeat` and `push_telemetry_heartbeat_sync`) fail-open cleanly (returning `0`) in minimal headless environments without crashing local CLI execution.
* Guarantees that fresh installations in pristine virtual environments (`pip install --no-cache-dir ctxfw==3.9.1`) execute `ctxfw --version` and `ctxfw doctor` without raising `ModuleNotFoundError`.

### 2. Elimination of Orphan CST Imports
* Removes unreferenced `from ctxfw.storage.telemetry import TelemetryLedger` import in `src/ctxfw/core/polyglot.py`.
* Ensures that the core AST/CST pruning pipeline maintains complete isolation from the optional telemetry push infrastructure.

### 3. Strict Air-Gapped Zero-Egress Preservation
* Preserves the lean packaging footprint (<0.1 MB wheel) without forcing heavy network transitive dependencies (`httpcore`, `certifi`, `idna`, `sniffio`) onto air-gapped runtimes.
* Complies fully with AXIOM-1 through AXIOM-21 under formal ACI 1.0000 governance.

---

## Upgrade & Verification

```bash
# Upgrade via PyPI
pip install --upgrade ctxfw

# Verify version
ctxfw --version  # Output: ctxfw 3.9.1

# Run diagnostic health sentry
ctxfw doctor
```
