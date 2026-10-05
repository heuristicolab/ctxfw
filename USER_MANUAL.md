# Context & Token Optimization Engine — Canonical Operating Manual & Runbook (v3.0)
### Target System: `ord-2026-4f003b` | Heuristico LAB Sovereign Core

[![Security Review](https://img.shields.io/badge/Security-Air--Gapped%20Certified-00ff66?style=flat-square)]()
[![Spec Version](https://img.shields.io/badge/Version-3.9.1-blue?style=flat-square)]()
[![Compliance](https://img.shields.io/badge/Compliance-NDA%20%26%20IP%20Shield-purple?style=flat-square)]()

---

## 1. Executive Security Blueprint: Data Plane vs. Control Plane (HU-15)

The Context Firewall architecture establishes strict sovereign isolation between the **Data Plane** (source code, ASTs, and file structures) and the **Control Plane** (telemetry, token counts, and upstream LLMs).

```
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                        SOVEREIGN DATA PLANE (Strictly Local)                          │
│                                                                                        │
│  [Source Tree] ──► [AST/Tree-sitter Pruner] ──► [Local SQLite WAL Cache]               │
│                            │                                                           │
│                            ▼                                                           │
│               [Sanitized Contractual Stubs]                                            │
│               - Bodies replaced by PEP 484 (...)                                       │
│               - Precondition raises sanitized: raise ValueError("...")                 │
│               - Zero internal algorithmic secrets or strings leaked                    │
└────────────────────────────────────┬───────────────────────────────────────────────────┘
                                     │
                                     ▼ (Sanitized Slices Only)
┌────────────────────────────────────────────────────────────────────────────────────────┐
│                         CONTROL PLANE (Upstream / Delivery)                            │
│                                                                                        │
│  [Agent Interfaces: MCP / Proxy / CLI] ──► [Upstream LLMs: OpenAI / Anthropic]        │
│                                        └──► [FinOps Ledger: tests/finops_audit.json]   │
└────────────────────────────────────────────────────────────────────────────────────────┘
```

### Inviolable Institutional Guarantees
1. **Zero Outbound Data Plane Emission (Air-Gapped):** Raw module code, internal algorithm implementations, and private database credentials never leave `localhost`. Only sanitized interfaces and contract stubs are emitted to downstream prompt contexts.
2. **Secret Neutralization in `raise` Statements:** All dynamic string interpolations and sensitive error tokens inside exception arguments are replaced with generic ellipsis strings (`raise ExceptionType("...")`).
3. **Local-Only FinOps Accounting:** Financial metrics are computed locally via character-to-token projection models ($max(1, \text{chars} // 4)$) at a standard baseline ($3.00 USD / 1M tokens), with zero third-party tracking calls.

---

## 2. Multi-Surface MCP & Zero-MCP Proxy Setup (HU-09 // v3.9.1 Industrial Architecture)

The Context Firewall exposes deterministic context compaction capabilities to autonomous coding agents across standard I/O (`sys.stdin` / `sys.stdout`) using JSON-RPC 2.0 (MCP Protocol Version `2024-11-05`), as well as transparent HTTP reverse proxy routing.

### A. Automated Multi-Surface Installation (`ctxfw init` / `ctxfw install`)

Executing `ctxfw init` (or `ctxfw install`) automatically scans, detects, and configures up to 4 autonomous coding environments without manual JSON editing:

1. **Claude Code CLI**:
   - Location: `~/.claude.json`
2. **Claude Desktop** (Dynamic Cross-Platform Resolution):
   - **macOS (Darwin)**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%\Claude\claude_desktop_config.json` (fallback: `~\AppData\Roaming\Claude\...`)
   - **Linux / POSIX**: `~/.config/Claude/claude_desktop_config.json`
3. **Cursor IDE**:
   - Location: `.cursor/mcp.json` (scoped to current workspace).
4. **Windsurf IDE**:
   - Location: `~/.codeium/windsurf/mcp_config.json` (configured when `.codeium` signature exists).

#### Safety & Non-Destructive Invariants:
- **Timestamped Backup Snapshot (`.bak.<timestamp>`)**: Automatically creates an immutable snapshot of existing configuration files before applying any changes.
- **100% Third-Party Server Preservation**: Preserves all existing MCP servers, external keys, and top-level settings intact.
- **Zero-Failure Execution**: Resolves `sys.executable` with `["-m", "ctxfw.mcp"]` (or canonical absolute binary path if running within a PyInstaller standalone executable), eliminating ambient `$PATH` and virtualenv resolution failures.
- **3x Idempotency**: Multiple consecutive invocations guarantee byte-for-byte convergence without duplicating keys or generating spurious diffs.

```json
{
  "mcpServers": {
    "ctxfw": {
      "command": "C:\\Program Files\\Python310\\python.exe",
      "args": ["-m", "ctxfw.mcp"]
    }
  }
}
```

### B. High-Assurance Diagnostics (`ctxfw doctor`)

Verify environmental attestation, stdio stream isolation, and local cache health across 6 diagnostic sentries:

```bash
ctxfw doctor
```

The 6 automated health checks comprise:
1. **Python Package & sys.path**: Validates `ctxfw` package integrity, version attestation (`v3.9.1`), and clean module importability.
2. **MCP stdio Stream Isolation**: Asserts 100% pure JSON-RPC on stdout and verifies diagnostic logs are strictly isolated to stderr to prevent agent JSON-RPC parsing failures.
3. **Global CLI Executable (PATH)**: Verifies that the `ctxfw` binary is registered and resolvable in the system PATH.
4. **Axiomatic Sieve Engine**: Executes formal verification of specifications against negative invariants ($N \ge 5$) and domain bounds, confirming ACI $\ge$ 0.9000.
5. **SQLite WAL Cache & Concurrency**: Confirms Write-Ahead Logging (`PRAGMA journal_mode=WAL`) and 5000ms busy timeout for safe multi-process concurrent access.
6. **Polyglot Tree-Sitter Grammars**: Verifies initialization of TypeScript, Go, and Java CST parsers alongside the Python standard library `ast`.

### C. Exposed MCP Tools
- `prune_file`:
  - `path` (string, required): Path to source file.
  - `depth` (string, default `"interface"`): `"full"`, `"interface"`, or `"nominal"`.
  - `strip_docs` (boolean, default `false`): Purge docstrings.
  - `language` (string, default `"python"`): `"python"`, `"typescript"`, `"go"`, `"java"`.
- `resolve_context_bundle`:
  - `target_file` (string, required): Active editing buffer (Distance 0).
  - `project_root` (string, optional): Root directory for dependency resolution.
- `evaluate_spec_axioms`:
  - `brief` (string, required): Architecture or feature specification in markdown.
  - Validates negative invariants, bounds, state machines, and error taxonomies, returning an ACI score and manifest hash.

### D. Zero-MCP Reverse Proxy Gateway (Aider, OpenCode, Continue, CLI)

For AI coding tools and CLI workflows that do not natively support the Model Context Protocol, `ctxfw` provides a local zero-egress reverse proxy:

```bash
# 1. Start the local reverse proxy daemon
ctxfw proxy --port 8765
```

#### Client Configuration:
- **Aider CLI**:
  ```bash
  export ANTHROPIC_BASE_URL="http://localhost:8765/v1"
  aider --model claude-3-7-sonnet-20250219
  ```
- **OpenCode Interpreter / Shell Agents**:
  ```bash
  export OPENAI_BASE_URL="http://localhost:8765/v1"
  ```
- **Continue.dev (`~/.continue/config.json`)**:
  ```json
  {
    "models": [
      {
        "title": "CTXFW Proxied Sonnet",
        "provider": "anthropic",
        "model": "claude-3-7-sonnet-20250219",
        "apiBase": "http://localhost:8765/v1"
      }
    ]
  }
  ```

---

## 3. Ingress Interface 2: Perimeter Reverse Proxy Gateway (HU-10)

Transparent reverse proxy intercepting LLM requests, compacting structured markdown code blocks on the fly with $< 5\text{ ms}$ warm cache overhead.

### Starting the Gateway
```bash
ctxfw proxy --port 8765 --host 127.0.0.1
# or with custom upstream:
ctxfw proxy --port 8765 --upstream https://api.openai.com
```

### A. Python Client Integration (OpenAI SDK)
```python
from openai import OpenAI

client = OpenAI(
    base_url="http://localhost:8080/v1",
    api_key="your-api-key-here",  # Passed transparently upstream
)

response = client.chat.completions.create(
    model="gpt-4o",
    messages=[
        {"role": "user", "content": "Analyze this code:\n```python\nclass Service:\n    def run(self):\n        x = 100\n        return x\n```"}
    ],
)
```

### B. Python Client Integration (Anthropic SDK)
```python
import os
from anthropic import Anthropic

client = Anthropic(
    base_url="http://localhost:8080",
    api_key="your-anthropic-api-key",
)

response = client.messages.create(
    model="claude-3-5-sonnet-20241022",
    max_tokens=1024,
    messages=[
        {"role": "user", "content": "Review:\n```python\ndef logic():\n    secret = 42\n    return secret\n```"}
    ],
)
```

### Audit Response Headers
Every response includes cryptographic FinOps auditing headers:
- `X-Tokens-Saved`: Net context tokens eliminated prior to upstream delivery.
- `X-Firewall-Latency-Ms`: Milliseconds consumed by the firewall inspection loop.
- `X-Firewall-Status`:
  - `compacted`: Code blocks compacted and tokens saved.
  - `pass-through`: Non-code prompt forwarded untouched.
  - `bypassed`: Header `X-Context-Firewall-Bypass: true` detected.
  - `fail-open`: Syntax or parsing error triggered graceful passthrough.

### Bypassing Compaction
To pass code uncompacted without stopping the proxy, supply the header:
```bash
curl -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -H "X-Context-Firewall-Bypass: true" \
  -d '{"model": "gpt-4o", "messages": [{"role": "user", "content": "..."}]}'
```

---

## 4. Ingress Interface 3: Developer Terminal CLI (HU-12)

Immediate command-line tool for developers using web chat interfaces (ChatGPT, Claude Web). Compacts the topological dependency tree of any target file and atomically deposits the formatted prompt into the OS clipboard.

### Usage
```bash
# Compact target and copy directly to OS clipboard
python firewall_cli.py contracts.py

# Specify explicit project root
python firewall_cli.py contracts.py C:\sandbox\arch-ord-2026-4f003b

# Save output to Markdown file instead of clipboard
python firewall_cli.py contracts.py --no-clip --output prompt.md

# Pipe raw prompt to stdout
python firewall_cli.py contracts.py --stdout | other-tool
```

### Workspace Self-Seeding (`ctxfw init`)
Transform any repository or directory into an active sovereign workspace in $< 1\text{ ms}$:

```bash
# Initialize sovereign perimeter in current project root
ctxfw init

# Or target an arbitrary folder
ctxfw init C:\sandbox\nuevo-proyecto
```

**Atomically Deployed Sovereign Artifacts:**
1. `.mcp.json` — Universal stdio MCP server manifest (`{"command": "python", "args": ["-m", "ctxfw.mcp"]}`).
2. `.agent/rules.yaml` — Sovereign architect perimeter directives (`FIREWALL_LAW_01`, `FIREWALL_LAW_02`, `FINOPS_AUDIT_03`).
3. `.agents/rules/firewall_laws.md` — Topological firewall governance laws.
4. `.agents/skills/context-firewall/SKILL.md` — Native discoverable agent skill for Antigravity, Cursor, and Claude.

### Terminal Telemetry Output
```text
========================================================================
  CONTEXT FIREWALL -- SOVEREIGN CLIPBOARD & TOKEN OPTIMIZER (v3.3.0)
========================================================================
Target Module:  contracts.py
Project Root:   C:\sandbox\arch-ord-2026-4f003b

DIST   | MODULE                           | DEPTH      | ORIG TOK  | PRUNED   | SAVINGS 
------------------------------------------------------------------------------------
D0     | contracts.py                     | FULL       | 2,995     | 2,995    | 0.0%    
D1     | polyglot_pruner.py               | INTERFACE  | 1,739     | 426      | 75.5%   
------------------------------------------------------------------------------------
TOTAL  | 2 Modules                        |            | 4,734     | 3,421    | 27.7%   

[*] Net Context Tokens Saved:  1,313 tokens (27.7% reduction)
[*] Projected FinOps Savings:  $0.0039 USD (@ $3.00/1M tokens)
[*] Pipeline Latency:          1.85 ms
[*] Clipboard Status:          COPIED TO SYSTEM CLIPBOARD
========================================================================
```

---

## 5. Ingress Interface 4: CI/CD PR Gatekeeper (HU-11)

Automated PR impact analyzer for GitHub Actions and Git pre-commit hooks.

### Local CLI Execution
```bash
# Analyze changes against main branch
python ci_gatekeeper.py --base origin/main --head HEAD --output pr_summary.md

# Generate .pre-commit-config.yaml
python ci_gatekeeper.py --generate-pre-commit .pre-commit-config.yaml
```

### GitHub Actions Workflow (`.github/workflows/context_firewall.yml`)
```yaml
name: Context Firewall PR Perimeter Gate
on: [pull_request]

jobs:
  analyze-pr-context:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: "3.10"

      - name: Install dependencies
        run: pip install -e .

      - name: Evaluate Topological PR Perimeter
        run: |
          python ci_gatekeeper.py --base ${{ github.event.pull_request.base.sha }} --head ${{ github.sha }} --output summary.md
          cat summary.md >> $GITHUB_STEP_SUMMARY
```

---

## 6. Empirical A/B Benchmarking Harness (HU-07)

Empirical test harness measuring task success rates (`pass@1`) and token reduction across coding tasks.

```bash
# Run hermetically in CI using simulated/mock responses
python scripts/run_evals.py --mock --output tests/eval_report.json

# Run against live OpenAI endpoint
python scripts/run_evals.py --provider openai --model gpt-4o --output tests/eval_report.json
```

---

## 7. Operational Troubleshooting Matrix (HU-13)

| Issue | Symptom | Root Cause | Remediation Protocol |
| :--- | :--- | :--- | :--- |
| **Database Contention (`SQLITE_BUSY`)** | `sqlite3.OperationalError: database is locked` | Concurrent writer threads colliding during WAL sync | Verify `PRAGMA busy_timeout = 5000;` is active. Run SQLite manual checkpoint: `sqlite3 tokens_cache.db "PRAGMA wal_checkpoint(TRUNCATE);"` |
| **Selective Cache Invalidation** | Stale code stubs served after refactoring | Source code changed but hash collided or rules version unchanged | Invalidate cache table safely: `sqlite3 heuristic_tokens_cache.db "DELETE FROM tokens_cache WHERE cache_key LIKE '...';"` or delete `.db` file (auto-recreated on launch). |
| **Syntax Error Fail-Open** | Code blocks passed without token savings | Code contains invalid syntax (`SyntaxError`) | The proxy logs `[fail-open]` to `stderr` and passes payload intact to prevent developer workflow interruption. Correct syntax in source file. |
| **MCP stdio Protocol Corruption** | Agent reports `JSON-RPC parse error` | Extraneous text or `print()` statements routed to `sys.stdout` | **Inviolable rule:** Never write logs to `stdout`. Direct all diagnostic output to `sys.stderr.write()`. Check `sys.stderr` logs in agent console. |
| **Port Conflict on Proxy** | `OSError: [Errno 98] Address already in use` | Another service bound to port 8080 | Supply `--port <new_port>` (e.g. `python proxy_gateway.py --port 8081`). |
| **Tree-sitter Language Not Found** | Warning: `tree-sitter-<lang> grammar unavailable` | Missing grammar package | Run `pip install tree-sitter-typescript tree-sitter-go tree-sitter-java`. Python files fall back automatically to native standard library `ast`. |
