# Release Notes: ctxfw v4.2.0 — Wave 2 Sovereign Security, Causal Provenance & Hermetic Packaging
<!-- manifest_hash: 5797b5fd9df0b81be0cd88fc2c995331951fe8829dc7965d7e55a1da8ed43a22 -->

`ctxfw v4.2.0` completes **Wave 1** (`mcp_guard`, `PASAC`, `TraceLite`, `Snapshots`) and **Wave 2 Blocks A–E** on top of the **Sovereign Pentad** (`TraceKit`, `TokenCast`, `RulesCompiler`, `SARA`, `SWE-Gate`), introducing multi-hop indirect prompt injection causal provenance, dynamic capability-laundering containment, monotonic epoch replay prevention, 7-language + homoglyph hygiene without UTF-8 false positives, and fully self-contained wheel and PyInstaller standalone distribution.

For exact clean-room distribution metrics, see [`docs/benchmarks/WAVE2_V42_SECURITY_LATENCY_BENCHMARK.md`](benchmarks/WAVE2_V42_SECURITY_LATENCY_BENCHMARK.md).

---

## Highlights Across Wave 1 & Wave 2 (Blocks A–E)

### 1. Block E.1 — Causal Provenance, Dynamic Containment & Monotonic Epochs (`#31`, `#04`, `#28`)
- **Multi-Hop Causal Provenance (`ctxfw.sara.provenance` & `provenance_store`):** Backward BFS over active session edges (`ALIGNED` + `MISALIGNED`), fail-closed `depth_truncated=True` handling (`max_depth` bounded in `[1..64]`), and mutually exclusive Pydantic + SQLite `CHECK` classification (`CLEAN_BENIGN`, `BENIGN_AGENT_DRIFT`, `IPI_CONFIRMED`) storing SHA-256 digests without raw payload persistence.
- **Session Graph Continuity Across `STRIP_COMMANDS`:** `_record_post_tool_provenance` preserves causal ancestry when SARA strips adversarial directives (`saraStripped=True`) and links subsequent clean reads (`prev_node -> OBS_*`), blocking delayed `apply_patch` execution with `PROVENANCE_IPI_BLOCKED: IPI_CONFIRMED`.
- **Dynamic Paired Containment & Capability Laundering (`ctxfw.mcp_guard`):** Enforces `InferredSandboxBoundary` canary disjointness, `PoC-1 / PoC-2 / PoC-3` paired containment (`evaluate_paired_containment`), `FirewallState.ALLOW` for clean profiles, and pre-execution Gate `0d` checks (`CTXFW_CAPABILITY_PROFILES` fail-closed up to `65,536` bytes / `128` tools), including enforcement prior to `query_audit_ledger`.
- **Generic Monotonic Epoch Freshness (`#28`):** Strictly increasing `epoch_k > last_consumed_k` micro-kernel integrated cleanly into `ProvenanceStore`, `TaskAuthStore`, and `SandboxSnapshotStore` without disturbing `_run_epochs`.

### 2. Block E.2 — Multilingual Lexical Hygiene & Intra-Token Confusable Defense (`#13`)
- **7-Language Role-Override Coverage + Intra-Token Confusables (`ctxfw.sara.lexical` & `induction`):** Detects indirect role-override injections across **Spanish, French, German, Portuguese, Chinese, Japanese, Korean** (including `[을를]?` particles and `하고` conjunctions), and intra-token Cyrillic/Greek homoglyph spoofs, while maintaining **`0.0%` false positives** on benign polyglot UTF-8 codebases.
- **Symmetric Slot Preservation:** `verify_symmetric_slot_preservation` verifies preserved interface/slot SHA-256 parity and `validate_language_tag` enforces strict BCP-47 bounds.

### 3. Block D — Task-Scoped Anti-Replay Auth & Cadence AIMD Scheduler (`#07`, `#08`, `#10`, `#19`)
- **Task-Scoped Authorization (`ctxfw.sara.task_auth`):** Open extensible `ToolDomain`, HMAC-SHA256 `DPoP` anti-replay nonces (`task_auth_dpop_nonces`), workspace `pre_state_sha256` continuity, PoLP sandbox verification, and spoof delimiter rejection (`<INST BEGIN>`, `<DATA END>`).
- **Cadence AIMD Proxy Scheduler (`ctxfw.budget.cadence`):** Deterministic `[i_base .. i_max]` AIMD interval expansion (`[2, 4, 6, 8, 8, 2]` verified trajectory) paired with fail-closed `REPLACEMENT` anomaly vetoes inside `proxy.py` and isolated `cadence_occ_ledger` concurrency.

### 4. Block A–C Foundations & Hardening (`mcp_guard`, `PASAC`, `TraceLite`, `Snapshots`)
- **Block A (`mcp_guard`):** SHA-256 tool description pinning + rug-pull detection (`RUG_PULL_BLOCKED`), strict semver built-in server upgrade matching (`^ctxfw-mcp-\d+\.\d+\.\d+...`), OS symlink/junction workspace confinement, and Gate `0a` parameter binding guards.
- **Block B (`PASAC`):** 6-layer Boundary Assurance Vector (`b_scope..b_response`), hazard telemetry gate, quarantine alerts, and offline accountability reauthorization.
- **Block C (`TraceLite` & `Snapshots`):** `82.43%` trace token compaction (`5.692x`) preserving edit actions and newest steps, paired with SQLite WAL snapshot rollback epoch cache invalidation (`cache.get_rollback_epoch`).

### 5. Reproducible Packaging & Windows Runtime Fixes
- **Complete Wheel & PyInstaller Assets (`ctxfw.spec`):** Bundles all lazy `ctxfw` submodules (`80` modules) and all **`19`** `.sql` and `.json` schema/blueprint artifacts cleanly inside both `dist/ctxfw-4.2.0-py3-none-any.whl` and `dist/ctxfw.exe`.
- **Standalone `doctor` Resolution (`src/ctxfw/installer.py`):** Under `sys.frozen`, `resolve_mcp_command()` and `run_doctor()` launch `[sys.executable, "mcp"]` (avoiding `-m` under PyInstaller `--onefile`), passing `ctxfw.exe doctor` cleanly.
- **Windows Piped UTF-8 Stdio Isolation (`src/ctxfw/mcp.py`):** `run_stdio_loop()` reconfigures piped `sys.stdin`, `sys.stdout`, and `sys.stderr` from `cp1252` to `utf-8`, eliminating mojibake on UTF-8 paths and source files.
- **External Benchmark `--root` Auto-Detection (`src/ctxfw/cli/commands/benchmark.py`):** `ctxfw benchmark <external_path>` automatically infers `project_root` cleanly (verified on `chronos-engine` across `90` Spanish/UTF-8 modules with `-55.0%` token savings).
- **Recursive CI SQL Check (`.github/workflows/ci.yaml`):** Validates every schema matching `src/ctxfw/**/*.sql` in SQLite (`13/13` schemas verified).

---

## Verification & Upgrade

```bash
# Install or upgrade from PyPI
pip install --upgrade ctxfw

# Check version, self-diagnostics, and specification axioms
ctxfw --version          # ctxfw 4.2.0
ctxfw doctor             # Verdict: [HEALTHY] [ATTESTED]
ctxfw spec verify SPEC.axioms.md  # ACI Score: 1.0000
pytest tests/ -q         # 565/565 passed (562 core/security + 3 docs parity)

# Run reproducible Wave 2 & SARA benchmarks (offline SQLite WAL, zero network egress)
python benchmarks/run_wave2_v42_benchmark.py --json
python benchmarks/run_sara_security_benchmark.py --json
```
