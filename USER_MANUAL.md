# Context & Token Optimization Engine — Canonical Operating Manual & Runbook (v3.0)
### Target System: `ord-2026-4f003b` | Heuristico LAB Sovereign Core

[![Security Review](https://img.shields.io/badge/Security-Air--Gapped%20Certified-00ff66?style=flat-square)]()
[![Spec Version](https://img.shields.io/badge/Version-3.3.0-blue?style=flat-square)]()
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

## 2. Ingress Interface 1: Model Context Protocol (MCP) Server (HU-09)

The MCP Server exposes context compaction capabilities to AI agents over standard I/O (`sys.stdin` / `sys.stdout`) using JSON-RPC 2.0 (MCP Protocol Version `2024-11-05`).

### A. Cursor Configuration (`.cursor/mcp.json`)
Place in project root or global Cursor settings:
```json
{
  "mcpServers": {
    "context-firewall": {
      "command": "python",
      "args": ["C:/sandbox/arch-ord-2026-4f003b/mcp_server.py"]
    }
  }
}
```

### B. Claude Desktop Configuration (`claude_desktop_config.json`)
Location on Windows: `%APPDATA%\Claude\claude_desktop_config.json`
Location on macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
```json
{
  "mcpServers": {
    "context-firewall": {
      "command": "python",
      "args": ["C:/sandbox/arch-ord-2026-4f003b/mcp_server.py"]
    }
  }
}
```

### Exposed MCP Tools
- `prune_file`:
  - `path` (string, required): Path to source file.
  - `depth` (string, default `"interface"`): `"full"`, `"interface"`, or `"nominal"`.
  - `strip_docs` (boolean, default `false`): Purge docstrings.
  - `language` (string, default `"python"`): `"python"`, `"typescript"`, `"go"`, `"java"`.
- `resolve_context_bundle`:
  - `target_file` (string, required): Active editing buffer (Distance 0).
  - `project_root` (string, optional): Root directory for dependency resolution.

---

## 3. Ingress Interface 2: Perimeter Reverse Proxy Gateway (HU-10)

Transparent reverse proxy intercepting LLM requests, compacting structured markdown code blocks on the fly with $< 5\text{ ms}$ warm cache overhead.

### Starting the Gateway
```bash
python proxy_gateway.py --port 8080 --host 0.0.0.0 --upstream https://api.openai.com
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
