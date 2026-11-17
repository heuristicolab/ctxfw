# CTXFW Operating Manual & Architecture Runbook (`v4.2.1`)

[![PyPI Version](https://img.shields.io/pypi/v/ctxfw?style=flat-square&label=PyPI)](https://pypi.org/project/ctxfw/)
[![Python Versions](https://img.shields.io/pypi/pyversions/ctxfw?style=flat-square)](https://pypi.org/project/ctxfw/)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache%202.0-black?style=flat-square)](LICENSE)

> **Current Version:** `ctxfw v4.2.1` · **Release Notes:** [`docs/RELEASE_NOTES_v4.2.1.md`](docs/RELEASE_NOTES_v4.2.1.md) · **Suite Status:** `667/667` tests passing · **Standalone Windows Binary:** `14.18 MB` (`19` embedded `.sql`/`.json` assets)

---

## 1. Security Blueprint: Data Plane vs. Control Plane

`ctxfw` enforces strict deterministic isolation between the **Sovereign Data Plane** (source code, syntax trees, tool outputs, and local SQLite WAL stores) and the **Upstream Control Plane** (LLM API payloads and FinOps accounting):

```text
+------------------------------------------------------------------------------+
| SOVEREIGN DATA PLANE (Local CPU & RAM — Zero Network Egress)                 |
|                                                                              |
|  [Source Tree / Tool IO] --> [SARA + LexicalSanitizer] --> [AST Pruner]      |
|                                       |                        |             |
|                                       v                        v             |
|                            [TraceKit SHA-256 WAL]    [Typed D1-D3 Stubs]     |
|                            - Bodies elided to '...'                          |
|                            - Exception messages sanitized                    |
+------------------------------------------------------------------+-----------+
                                                                   |
                                             Sanitized Context Only v
+------------------------------------------------------------------------------+
| UPSTREAM DELIVERY PLANE                                                      |
|                                                                              |
|  [MCP stdio / Loopback Proxy / Clipboard CLI] --> [OpenAI / Anthropic / Local]|
|                                               --> [Local FinOps Ledger]      |
+------------------------------------------------------------------------------+
```

### Core Data-Plane Guarantees
1. **Zero Outbound Code Egress:** Raw repository files, private helper implementations, and secret strings never leave `localhost` during pruning, security inspection, or axiom verification.
2. **Contractual Stub Compaction (`AXIOM-3`):** Only peripheral imported modules (`D1`–`D2`) have executable bodies replaced with `...` and exception payloads sanitized to `raise ExceptionType("...")`. The active focal file (`D0`) is always kept 100% intact.
3. **Local Token Estimation:** FinOps savings use deterministic character-to-token projection (`max(1, chars // 4)`) stored exclusively in local SQLite WAL databases.

---

## 2. MCP `stdio` Server & Multi-Surface Provisioning

### A. Automated IDE Setup (`ctxfw init` / `ctxfw install`)

Running `ctxfw init` (or `ctxfw install`) automatically detects and updates MCP configurations across up to four environments:

1. **Claude Code CLI:** `~/.claude.json`
2. **Claude Desktop:**
   - **macOS:** `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows:** `%APPDATA%\Claude\claude_desktop_config.json`
   - **Linux / POSIX:** `~/.config/Claude/claude_desktop_config.json`
3. **Cursor IDE:** `.cursor/mcp.json` (workspace scope)
4. **Windsurf IDE:** `~/.codeium/windsurf/mcp_config.json`

Targeted invocations:

```bash
# Configure Claude Code CLI & Claude Desktop
ctxfw init --claude

# Auto-detect all installed IDEs
ctxfw init --global

# Initialize SPEC.axioms.md and git pre-commit verification hook in a repository
ctxfw init --repo .
```

**Safety guarantees:**
- Creates a timestamped backup `<config>.bak.<timestamp>` before mutating any file.
- Preserves all third-party `mcpServers` entries verbatim.
- Binds cleanly to the exact interpreter (`sys.executable -m ctxfw.mcp`) or frozen executable path (`ctxfw.exe mcp`).

Example generated server declaration:

```json
{
  "mcpServers": {
    "ctxfw": {
      "command": "python",
      "args": ["-m", "ctxfw.mcp"]
    }
  }
}
```

### B. Health & Stream Isolation Diagnostics (`ctxfw doctor`)

```bash
ctxfw doctor
```

Validates `8` core invariants in under 2 seconds:
1. **Python Package & `sys.path`:** Confirms clean import and canonical `ctxfw` version (`4.2.1`).
2. **MCP `stdio` Stream Isolation:** Asserts pure JSON-RPC 2.0 frames on `stdout` with diagnostic output isolated to `stderr`.
3. **Global CLI Executable (`PATH`):** Verifies executable availability in `$PATH`.
4. **Axiomatic Sieve Engine:** Verifies negative-invariant evaluation and `ACI >= 0.9000`.
5. **SQLite WAL Cache & Concurrency:** Confirms `PRAGMA journal_mode=WAL` and `busy_timeout = 5000 ms`.
6. **Polyglot Tree-Sitter Grammars:** Checks Python `ast` plus optional `tree-sitter-typescript`, `tree-sitter-go`, and `tree-sitter-java`.
7. **TraceKit Ledger Audit:** Verifies append-only SHA-256 hash chain consistency.
8. **Sovereign Pentad WAL Ledgers:** Summarizes live row counts across `sara.db`, `tokencast.db`, `rules.db`, `swegate.db`, and `mcp_guard`.

### C. Exposed MCP Tools

- **`prune_file`**: `path` (required), `depth` (`"full"`, `"interface"`, or `"nominal"`), `strip_docs` (boolean), `language` (`"python"`, `"typescript"`, `"javascript"`, `"go"`, `"java"`).
- **`resolve_context_bundle`**: `target_file` (required `D0`), `project_root` (optional root for `D1`–`D3` dependency resolution).
- **`evaluate_spec_axioms`**: `brief_text` (required markdown brief). Validates ≥ 5 negative invariants (`never` / `shall never`), bounded variables, finite-state transitions, and 4-class error taxonomy; returns `ACI` score and SHA-256 `manifest_hash`.
- **`evaluate_patch`**: `diff_text` (required unified diff). Enforces `max_cyclomatic_delta` (default `10`), banned imports, zero `# type: ignore`, and functional verdict gates (`ALLOW_MERGE` / `REJECT_*`).
- **`query_audit_ledger`**: `evaluation_id` (`EVL-...`) and/or `session_id` (`SES-...`). Verifies `TraceKit` hash chain integrity and inspects sealed ledger blocks under Gate `0d` confinement.

---

## 3. Loopback HTTP Reverse Proxy (`ctxfw proxy`)

For coding tools that communicate over HTTP REST instead of MCP `stdio` (Aider, OpenCode Interpreter, Continue.dev), `ctxfw` provides a local loopback reverse proxy:

```bash
# Start proxy on default port 8765
ctxfw proxy --host 127.0.0.1 --port 8765

# Or forward to a custom upstream endpoint
ctxfw proxy --port 8765 --upstream https://api.anthropic.com
```

### Client Environment Configuration

```bash
# Anthropic SDK / Aider / Claude API clients
export ANTHROPIC_BASE_URL="http://localhost:8765/v1"

# OpenAI SDK / OpenCode / Continue.dev
export OPENAI_BASE_URL="http://localhost:8765/v1"
```

Every proxy response emits local telemetry headers:
- `X-Tokens-Saved`: Net context tokens eliminated prior to upstream forwarding.
- `X-Firewall-Latency-Ms`: End-to-end firewall inspection duration in milliseconds.
- `X-Firewall-Status`: `compacted`, `pass-through`, `bypassed` (when `X-Context-Firewall-Bypass: true` is supplied), or `fail-open`.

### Managing the Background Service (`ctxfw service`)

```bash
ctxfw service status
ctxfw service install --user --port 8765
ctxfw service start
ctxfw service stop
```

---

## 4. Terminal CLI & Clipboard Compactor

Compact a target module and its topological dependency perimeter directly from the command line:

```bash
# Compact target and copy prompt to OS clipboard
ctxfw path/to/contracts.py

# Specify explicit project root
ctxfw path/to/contracts.py path/to/repo

# Save Markdown prompt to disk or stream to stdout
ctxfw path/to/contracts.py --no-clip --output prompt.md
ctxfw path/to/contracts.py --stdout --price 3.00
```

Benchmark token reduction against an existing repository directory:

```bash
ctxfw benchmark ./src --model claude-3-5-sonnet --cycles 500 --format json
```

---

## 5. CI/CD Gatekeeping, Axioms & Audit Ledgers

### A. SWE-Gate Pull Request Verifier (`ctxfw gate`)

```bash
# Inspect a unified patch file
ctxfw gate --diff pr.patch --github-summary

# Inspect staged changes locally or diff against base ref
ctxfw gate --staged --max-cyclomatic-delta 10
ctxfw gate --base origin/main --json --tests-passed 120 --tests-failed 0
```

### B. Topological PR Impact & FinOps Analyzer (`ctxfw ci`)

```bash
ctxfw ci --base origin/main --head HEAD --output pr_summary.md
ctxfw ci --generate-pre-commit .pre-commit-config.yaml
```

### C. Specification Sieve, Ledger Verification & FinOps Reports

```bash
# Verify formal axioms in SPEC.axioms.md
ctxfw spec verify SPEC.axioms.md

# Backward-verify TraceKit SHA-256 hash chain integrity
ctxfw trace verify

# Audit token savings ledger and emit shareable / team reports
ctxfw audit --json
ctxfw report --share
ctxfw report --export-json ./my-ledger.json
ctxfw report --team-merge ./team-ledgers/
```

---

## 6. Empirical Security & Benchmark Suites

Run the bundled offline verification harnesses (`network_egress_calls = 0`):

```bash
# 24-vector SARA prompt injection & Trojan-Source suite
python benchmarks/run_sara_security_benchmark.py --json

# Wave 2 multi-engine suite (mcp_guard, PASAC, TaskAuth, TraceLite, Provenance, Multilingual)
python benchmarks/run_wave2_v42_benchmark.py --json

# 60-document Spanish regulatory, legal & noisy OCR benchmark (SARA-RegDoc-60)
python benchmarks/run_regulatory_ocr_benchmark.py --json

# Mocked or live coding-agent evaluation harness
python scripts/run_evals.py --mock --output tests/eval_report.json
```

---

## 7. Operational Troubleshooting Matrix

| Issue | Symptom | Root Cause | Remediation |
| :--- | :--- | :--- | :--- |
| **SQLite Lock Contention** | `sqlite3.OperationalError: database is locked` | Concurrent writers colliding during WAL sync | Confirm WAL mode (`busy_timeout = 5000`); run `sqlite3 <db_path> "PRAGMA wal_checkpoint(TRUNCATE);"` |
| **Cache Reset Needed** | Stale dependency stubs after manual file renames | Cached key from prior state | Run snapshot rollback / delete ephemeral cache `.db` in `~/.ctxfw/` (recreated automatically) |
| **Tree-Sitter Grammar Missing** | `tree-sitter-<lang>` parser skipped | Core install omits optional non-Python grammars | Run `pip install "ctxfw[polyglot]"` (`Python` `ast` works out of the box) |
| **Proxy Dependencies Missing** | `ctxfw proxy` fails with `ImportError` (`fastapi` / `uvicorn`) | Optional HTTP proxy extras not installed | Run `pip install "ctxfw[proxy]"` |
| **Port Already Bound** | `OSError` when launching `ctxfw proxy` | Another local process owns port `8765` | Pass `--port <free_port>` (e.g. `ctxfw proxy --port 8766`) |
| **MCP `stdio` Parse Error** | Client reports invalid JSON-RPC on `stdout` | Unsanitized debug output written to `stdout` | Ensure all non-JSON-RPC logging targets `sys.stderr`; verify with `ctxfw doctor` |
| **Team License Not Loaded** | `ctxfw gate` reports missing team credentials | License key unset in environment or `~/.ctxfw/license.key` | Export `CTXFW_LICENSE_KEY` or run `ctxfw license activate <key>` |
