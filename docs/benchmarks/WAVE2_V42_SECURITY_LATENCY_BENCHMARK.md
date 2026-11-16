# Wave 2 Security, Packaging & Latency Empirical Benchmark (`ctxfw v4.2.0`)
<!-- manifest_hash: c9f28afc9543f48b94ca316d0a6cbedbf1f4baaa979ae9b033f2c36902e8c9ae -->

> Reproducible zero-egress empirical verification of `ctxfw v4.2.0` executed on clean distribution artifacts (`dist/ctxfw-4.2.0-py3-none-any.whl` installed non-editably in an isolated virtualenv and `dist/ctxfw.exe` standalone PyInstaller binary) with `PYTHONUTF8` and `PYTHONPATH` unset.

---

## 1. Distribution Parity & Embedded Runtime Manifest

- **Wheel Artifact:** `dist/ctxfw-4.2.0-py3-none-any.whl` (`390,919` bytes, `104` files, `twine check`: `PASSED`)
- **Source Distribution:** `dist/ctxfw-4.2.0.tar.gz` (`353,989` bytes, `twine check`: `PASSED`)
- **Standalone Binary:** `dist/ctxfw.exe` (`25,561,105` bytes / `24.38 MB`, PyInstaller `--onefile`, `collect_submodules('ctxfw')` + `collect_data_files('ctxfw')`)
- **Embedded SQL & Blueprint Assets (`19` files, identical between `.whl` and `dist/ctxfw.exe` TOC):**
  - `ctxfw/audit/{blueprint_manifest.json,schema.sql}`
  - `ctxfw/budget/{blueprint_manifest.json,cadence_schema.sql,schema.sql}`
  - `ctxfw/finops/model_matrix.json`
  - `ctxfw/mcp_guard/schema.sql`
  - `ctxfw/rules/{blueprint_manifest.json,schema.sql}`
  - `ctxfw/sara/{assurance_schema.sql,blueprint_manifest.json,provenance_schema.sql,schema.sql,task_auth_schema.sql}`
  - `ctxfw/storage/{schema.sql,snapshot_schema.sql}`
  - `ctxfw/swegate/{blueprint_manifest.json,schema.sql}`
  - `ctxfw/tracelite/schema.sql`
- **Local SQLite DDL Check:** `13 / 13` `.sql` schemas verified in `:memory:` with `PRAGMA foreign_keys = ON`.
- **Standalone & Clean-Venv Health:** `ctxfw --version` (`ctxfw 4.2.0`) and `ctxfw doctor C:\ctxfw` exited `0` (`[HEALTHY] [ATTESTED] Perimeter defense operational.`) on both `.whl` and `dist/ctxfw.exe`.

---

## 2. SARA 24-Vector Regression Benchmark (`run_sara_security_benchmark.py --json`)

Executed directly from the clean non-editable `.whl` virtualenv (`iterations`: 24 vectors — 16 adversarial OWASP AISVS `C02-01` / `arXiv:2510.05244v2` vectors + 8 benign developer snippets):

| Metric | Measured Result (`ctxfw v4.2.0`) |
| :--- | :---: |
| Benchmark Script Schema Version | `4.1.0` |
| Corpus Size | `24` (`16` adversarial, `8` benign) |
| True Positives / False Negatives | `16` / `0` |
| True Negatives / False Positives | `8` / `0` |
| Recall / Precision | **`100.0%`** / **`100.0%`** |
| False Positive Rate (`FPR`) | **`0.0%`** |
| Network Egress Calls | `0` |
| Latency P50 / P95 / Max | **`0.57 ms`** / **`1.5696 ms`** / `6.9998 ms` |
| Attestation SHA-256 | `b691dd2824e9c654336f02f350e66ecbbd3ad2fd5ca114528b16b2f5f36f575b` |

---

## 3. Wave 2 Reproducible Empirical Benchmark (`run_wave2_v42_benchmark.py --json`)

Executed from the clean non-editable `.whl` virtualenv across isolated temporary SQLite WAL stores (`iterations = 5`, `isolated_sqlite_wal = true`, `network_egress_calls = 0`):

- **`spec_manifest_hash`:** `c9f28afc9543f48b94ca316d0a6cbedbf1f4baaa979ae9b033f2c36902e8c9ae`
- **`attestation_sha256`:** `4b7723789f929c92723a89231d187270f868919d2be2f4bf78be4075167ea82c` *(verified identical across repeated runs)*

| Wave 2 Block / Engine | Verified Scope & Determinism | Recall / Pass | FPR | Latency P50 | Latency P95 |
| :--- | :--- | :---: | :---: | :---: | :---: |
| **Block A (`mcp_guard`)** | `5/5` SHA-256 rug-pull blocks, `30` poison vectors, `30` confinement paths (incl. OS `junction` escape) | `1.0` (`100%`) | `0.0` (`0%`) | `0.042 ms` | `1.087 ms` |
| **Block B (`PASAC #18`)** | Boundary assurance gating, quarantine & offline reauthorization (`5/5`) | `5/5` | `0.0` | `17.625 ms` | `18.333 ms` |
| **Block D.1 (`TaskAuth #07/#08/#10/#28`)** | DPoP HMAC anti-replay, state continuity, spoof delimiters, PoLP & monotonic epoch (`5/5`) | `5/5` | `0.0` | `3.201 ms` | `3.682 ms` |
| **Block D.2 (`Cadence AIMD #19`)** | Deterministic AIMD trajectory `[2, 4, 6, 8, 8, 2]` + anomaly `REPLACEMENT` veto (`5/5`) | `5/5` | `0.0` | `2.541 ms` | `2.847 ms` |
| **Block C (`TraceLite #12`)** | Trajectory compression `2,237 -> 393` tokens (`1,844` saved, **`82.43%`**, **`5.692x`**) | `5/5` | — | `7.797 ms` | `8.65 ms` |
| **Block C (`Snapshots #17/#28`)** | Wrong-state attractor + rollback epoch cache invalidation (`5/5`) | `5/5` | — | `9.391 ms` | `15.422 ms` |
| **Block E.1 (`#31 Provenance + #28 Epoch`)** | Multi-hop `ALIGNED+MISALIGNED` BFS, `depth_truncated`, `BENIGN_AGENT_DRIFT` vs `CLEAN_BENIGN`, monotonic epoch (`5/5`) | `5/5` | `0.0` | `1.243 ms` | `1.637 ms` |
| **Block E.1 (`#04 Dynamic Containment`)** | Paired PoC-1/2/3 containment + readonly capability laundering + `ParameterBindingGuard` (`5/5`) | `5/5` | `0.0` | `0.762 ms` | `0.901 ms` |
| **Block E.2 (`#13 Multilingual Hygiene`)** | `45` adversarial vectors across `es`, `fr`, `de`, `pt`, `zh`, `ja`, `ko`, `homoglyph_mixed` + `35` polyglot benign UTF-8 vectors | `1.0` (`100%`) | `0.0` (`0%`) | `0.334 ms` | `1.276 ms` |

---

## 4. Real Repository Topological Compaction (`ctxfw benchmark --format json`)

Measured from the clean non-editable `.whl` virtualenv (`model = claude-3-5-sonnet`, `pricing_per_1m = $3.00`, `cycles = 500`, zero edits to target repositories):

| Target Repository | Modules Scanned | Raw Tokens | Pruned Tokens | Net Savings | Tokens Saved / Cycle | Projected Savings (500 cycles) | Latency |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| `C:\ctxfw\src` | `80` | `6,914,785` | `2,044,783` | **`70.4%`** | `4,870,002` | `$7,305.00 USD` | `19,748.63 ms` |
| `C:\os.metaversemexico.mx\chronos-engine` *(Spanish UTF-8)* | `90` | `856,475` | `385,363` | **`55.0%`** | `471,112` | `$706.67 USD` | `2,605.14 ms` |

---

## 5. Live Stdio JSON-RPC End-to-End Parity (`.whl` vs `dist/ctxfw.exe`)

Executed in parallel clean environments with `CTXFW_ENFORCE_PROVENANCE=1`, `CTXFW_CAPABILITY_PROFILES` active, and `PYTHONUTF8` unset:

| Verification Step (7 JSON-RPC Frames, `exit_code == 0`) | Clean `.whl` (`ctxfw mcp`) | Standalone (`dist\ctxfw.exe mcp`) |
| :--- | :---: | :---: |
| `initialize` (`serverInfo.version == "4.2.0"`) & `tools/list` (`5` tools) | **PASS** | **PASS** |
| `prune_file` on Spanish UTF-8 module (`servicio_español.py`) | **PASS** (`0` false positives) | **PASS** (`0` false positives) |
| Gate `0d` before `query_audit_ledger` (`declared_readonly=True` + `filesystem:write`) | **BLOCKED** (`CAPABILITY_LAUNDERING_BLOCKED`) | **BLOCKED** (`CAPABILITY_LAUNDERING_BLOCKED`) |
| Multi-hop IPI: `prune_file` (`saraStripped=True`) → clean `prune_file` → `apply_patch` | **BLOCKED** (`IPI_CONFIRMED`) | **BLOCKED** (`IPI_CONFIRMED`) |
| Target file preservation & pure JSON-RPC `stdout` (`stderr` isolated) | **PASS** (`target_intact=true`) | **PASS** (`target_intact=true`) |

Literal provenance block reason returned identically by both runtimes:

```text
PROVENANCE_IPI_BLOCKED: IPI_CONFIRMED via EXT_prune_file_1 -> OBS_prune_file_1 -> OBS_prune_file_2 -> SINK_apply_patch (depth_truncated=False)
```

---

## 6. Reproducibility Commands

```bash
# Re-run Wave 2 offline empirical benchmark (Blocks A-E)
python benchmarks/run_wave2_v42_benchmark.py --json

# Re-run SARA 24-vector regression benchmark
python benchmarks/run_sara_security_benchmark.py --json

# Profile real AST compaction against local codebase
ctxfw benchmark ./src --format json
```
