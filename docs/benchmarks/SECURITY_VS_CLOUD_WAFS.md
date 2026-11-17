<!-- manifest_hash: 4a446cfc7aa488cc2b193750e694b95f5b66d694387ecd5b66d2090c0303f6be -->
# AI Agent Governance & Prompt Injection Firewalls: `CTXFW` vs. Cloud Runtime WAFs (`Lakera Guard`, `Palo Alto Prisma AIRS`, `Protect AI`, `Cloudflare Firewall for AI`)

**Canonical Version:** `ctxfw v4.1.0`  
**Security Attestation:** Glama MCP Registry **Grade A (100/100 Security)** · Skills Directory **Grade A (100/100 across 120 static patterns)**  
**Empirical Benchmark Dossiers:** [`docs/benchmarks/TRILOGY_EMPIRICAL_BENCHMARK.md`](TRILOGY_EMPIRICAL_BENCHMARK.md) & [`benchmarks/run_sara_security_benchmark.py`](../../benchmarks/run_sara_security_benchmark.py)

---

## 1. Executive Summary: The Pre-Ingestion AST/MCP Boundary vs. Cloud Runtime Proxies

When enterprise CISOs, Staff Engineers, and AI Platform Architects evaluate **AI Agent Governance & Prompt Injection Firewalls**, the market divides into two distinct architectural layers that solve fundamentally different attack surfaces:

1. **Cloud Runtime API Firewalls (`Lakera Guard`, `Palo Alto Networks Prisma AIRS`, `Protect AI Guardian`, `Cloudflare Firewall for AI`) & Foundation Model Guardrails (`OpenAI`, `Anthropic`, `Microsoft Azure OpenAI Service`)**:
   - **What they protect:** HTTP/REST inference traffic between customer-facing chatbots and cloud LLM APIs.
   - **How they work:** Probabilistic classifier models or cloud edge proxies inspecting assembled text prompts over the network.
   - **Enterprise Limitation for Coding & MCP Agents:** Require transmitting proprietary source code and tool outputs to an external cloud inspection endpoint (**Network Egress**), add `30 ms – 250 ms` of network round-trip latency per call, and **save 0% of peripheral AST token bloat**.
2. **Local Pre-Ingestion Context & MCP Firewall (`CTXFW // Context Firewall v4.1.0`)**:
   - **What it protects:** Autonomous coding agents (`Claude Code`, `Cursor`, `Windsurf`, `Antigravity`, `Aider`) and Model Context Protocol (`MCP`) tool pipelines **before** context assembly leaves the developer workstation or air-gapped CI runner.
   - **How it works:** Deterministic in-memory **Tree-Sitter AST/CST topological compaction** (D0 -> D3) combined with **`ctxfw.sara` (Sovereign Agent Induction Firewall)**, **`ctxfw.rules` (Normative Rules Enforcer)**, **`TokenCast` (FinOps Circuit Breaker)**, and **`TraceKit` (SHA-256 Hash-Chained Audit Ledger)**.
   - **Enterprise Advantage:** **100% Zero-Egress** (runs strictly in local RAM / stdio / loopback), **0.33 ms median SARA inspection latency** (`437,351 tokens/sec` AST slicing throughput), and **cuts peripheral dependency token costs by 42.96% to 90.26%** while blocking indirect prompt injections and Trojan-Source bidi escapes deterministically.

---

## 2. Head-to-Head Architectural & Benchmark Matrix

| Evaluation Dimension | **CTXFW (`Context Firewall v4.1.0`)** | **Lakera Guard** (`Check Point`) | **Palo Alto Networks Prisma AIRS** | **Protect AI Guardian / Rebuff** | **Cloudflare Firewall for AI** |
| :--- | :--- | :--- | :--- | :--- | :--- |
| **Primary Protection Layer** | **Pre-Ingestion AST, Repository Context & MCP Tool Boundary (`stdio` / Local Proxy)** | Runtime HTTP Prompt / Response API Classifier | Enterprise Cloud Network & Runtime AI Security | ML Supply Chain & Runtime LLM Guardrails | Edge WAF for HTTP LLM API Endpoints |
| **Data Sovereignty / Egress** | **100% Zero-Egress (Air-Gapped Local RAM & SQLite WAL)** | Cloud API Egress (or heavy Enterprise container) | Cloud Inspection / Network Appliance | Cloud / Self-Hosted ML Inference | Cloud Edge Proxy Egress |
| **Indirect Prompt Injection Defense (`MCP` / Tool I/O)** | **Deterministic `ctxfw.sara`**: Blocks `<system>`, `[INST]`, role hijacks, null-bytes & Trojan-Source Unicode bidi escapes (`U+202E`) | Probabilistic ML Bert/Transformer classifier | Network + Runtime policy inspection | Heuristic + Vector DB + ML classifier | Edge WAF regex + LLM scoring |
| **Token & FinOps Cost Reduction** | **42.96% – 90.26% D1 AST Bloat Eliminated** (~**USD 87.70 saved per 1K calls**) | **0% token reduction** (bills per API call) | **0% token reduction** | **0% token reduction** | **0% token reduction** |
| **Focal Code Signal Preservation (D0)** | **100.00% Byte-for-Byte Identical (`AXIOM-3`)** — Zero focal loss | N/A (Pass-through text) | N/A (Pass-through text) | N/A (Pass-through text) | N/A (Pass-through text) |
| **Inspection Latency (P50 / P95)** | **0.33 ms P50 / 1.72 ms P95 (SARA) · < 0.8 ms (Warm WAL Cache)** | `35 ms – 120 ms` (Network + ML inference) | `25 ms – 90 ms` (Inline proxy) | `40 ms – 150 ms` | `15 ms – 60 ms` (Edge hop) |
| **Cryptographic Audit Trail** | **Built-in `TraceKit` (`tracekit.db`)**: 283-byte canonical SHA-256 Merkle chain | Cloud dashboard logs | Panorama / Strata Cloud logs | Guardian telemetry logs | Cloudflare dashboard logs |
| **MCP Ecosystem Native Support** | **Native 5-Tool JSON-RPC `stdio` Server (`Glama Grade A 100/100`)** | No native AST/MCP `stdio` compactor | External MCP discovery only | No native AST/MCP compactor | No local `stdio` MCP compactor |
| **Setup Complexity** | **1 Command (< 10 sec)**: `pipx install ctxfw && ctxfw init` | API keys + SDK wrapper refactoring | TLS decryption + network routing | SDK + Vector DB setup | DNS / Cloudflare Worker proxy |

---

## 3. Reproducible Indirect Prompt Injection & Trojan-Source Benchmark (`OWASP AISVS C02-01` & `arXiv:2510.05244v2`)

To address enterprise security requirements for reproducible, offline verification against indirect prompt injection arriving via untrusted MCP tool outputs, third-party docstrings, and repository files, [`benchmarks/run_sara_security_benchmark.py`](../../benchmarks/run_sara_security_benchmark.py) executes a 24-vector deterministic suite (`16` adversarial indirect prompt-injection / Trojan-Source vectors + `8` benign polyglot production code vectors):

```bash
python benchmarks/run_sara_security_benchmark.py
```

| Benchmark Metric | Empirical Result (`ctxfw v4.1.0`) | Verification Standard / Notes |
| :--- | :---: | :--- |
| **Total Corpus Size** | **`24` vectors** | `16` Adversarial (`OWASP AISVS C02-01` / `arXiv:2510.05244v2`) + `8` Benign (`Python`, `TS`, `Go`, `SQL`) |
| **Adversarial Detection Recall** | **`100.0%` (`16 / 16`)** | Role hijacks (`<system>`, `[INST]`, `<|im_start|>`), Trojan-Source BiDi (`U+202E`, `U+2067`), ANSI OSC escapes, RCE pipe-to-shell, subshells `$()`, null-bytes, & `%252e%252e` traversal |
| **Benign False Positive Rate (FPR)** | **`0.0%` (`0 / 8`)** | `100.0%` Precision — zero false alarms on legitimate `def execute(...)`, Pydantic DTOs, or SQL queries |
| **Median Inspection Latency (P50)** | **`0.3264 ms`** | Deterministic O(n) in-memory lexical & AST induction parser |
| **95th Percentile Latency (P95)** | **`1.7200 ms`** | Includes synchronous SQLite WAL cryptographic audit commit (`sara.db`) |
| **External Network Egress Calls** | **`0` (`100% Zero-Egress`)** | Operates completely offline in air-gapped VPCs and GitHub Actions runners |
| **SHA-256 Attestation Digest** | `b691dd2824e9c654336f02f350e66ecbbd3ad2fd5ca114528b16b2f5f36f575b` | Deterministic canonical summary digest |

---

## 4. Resolving the 3 Core Enterprise Objections (Empirical Evidence)

### Objection 1: *"Is there independent benchmark evidence against real production codebases and prompt injection vectors?"*
- **Independent Security Certification (`100/100 Grade A`)**:
  - Audited by the **[Glama MCP Registry](https://glama.ai/mcp/servers/heuristicolab/ctxfw)** (`Grade A · Security 100/100 · TDQS 4.5/5.0`) and **[Skills Directory](https://www.skillsdirectory.com/authors/heuristicolab)** (`100/100 Security` across 120 static vulnerability patterns).
- **Deterministic Prompt Injection & Trojan-Source Sieve (`ctxfw.sara` + `ctxfw.rules`)**:
  - Verified at **100.0% recall and 0.0% false positive rate** (`0.33 ms` P50 latency) via [`benchmarks/run_sara_security_benchmark.py`](../../benchmarks/run_sara_security_benchmark.py).
- **Production Monorepo Validation (`TRILOGY_EMPIRICAL_BENCHMARK.md`)**:
  - Verified in isolated Ubuntu 24.04 LTS containers across **[`zulip/zulip`](https://github.com/zulip/zulip)** (`-42.96%` Interface / `-78.20%` Nominal D1 reduction, `44.1 ms`), **[`PostHog/posthog`](https://github.com/PostHog/posthog)** (`-59.53%` D1 reduction, `50.2 ms`), and **[`apache/airflow`](https://github.com/apache/airflow)** (`-66.90%` Interface / `-90.26%` Nominal D1 reduction, **40,428 bloat tokens pruned**, `437,351 tok/s` throughput, `0 bytes` stdio leak).

### Objection 2: *"Does pruning the AST risk losing signal that the coding agent needs?"*
- **Mathematical Guarantee — `AXIOM-3` (100% Zero Focal Degradation)**:
  - **`CTXFW` NEVER modifies, summarizes, or prunes the active focal file (D0) being edited or debugged.** D0 is preserved **100% byte-for-byte**.
  - Compaction is strictly applied to **peripheral imported dependencies (D1, D2)** where the agent only needs the **typed function signature, class hierarchy, return types, and docstrings** (`...` interface stubs) rather than 5,000 lines of internal helper implementation.
  - Furthermore, **D3 Ambient Cartography** injects a bounded flat symbol catalog (<= 1,000 tokens) up to 3 hops deep, **increasing** agent reasoning accuracy by eliminating *Lost-in-the-Middle* attention degradation. Every compacted output is verified via `ast.parse()` (`100% PASS` syntactic validity).

### Objection 3: *"Does a 6-subsystem firewall add operational complexity?"*
- **Zero-Touch 1-Command Provisioning (< 10 Seconds)**:
  - All 6 subsystems (`Tree-Sitter Pruner`, `TraceKit`, `TokenCast`, `RulesCompiler`, `SARA`, `SWE-Gate`) ship inside a single pure-Python/C-binding package (`pip install ctxfw`) with **zero external databases or cloud accounts required**.
  - Running `ctxfw init --global` (or `ctxfw install --claude`) automatically discovers and configures **Claude Code CLI, Claude Desktop, Cursor, and Windsurf** with atomic `.bak.<timestamp>` backups and `3x` idempotency.
  - Running `ctxfw doctor` verifies the entire stack in `< 2 seconds`.

---

## 5. Recommended Enterprise Defense-in-Depth Stack (`OpenAI` · `Anthropic` · `Azure OpenAI` + `CTXFW` + Cloud WAFs)

`CTXFW` is **100% model-agnostic** across **Anthropic Claude (`Claude Opus 4.6`, `Claude Sonnet 4.6`)**, **OpenAI (`GPT-5.4`, `o3`)**, **Google Gemini (`Gemini 3.1 Pro`)**, and **Microsoft Azure OpenAI Service**, and complements cloud runtime WAFs (`Lakera Guard`, `Prisma AIRS`, `Cloudflare Firewall for AI`):
- **Layer 0 — Developer Workstation, IDE, MCP Server, and CI/CD Pre-Commit (`CTXFW v4.1.0`)**: Guarantees **Zero-Egress** code sovereignty, cuts LLM API token bills by **43%–72%+** (`4.2x` multi-turn compound savings), enforces `.cursorrules`/`CLAUDE.md` deterministically, and sanitizes MCP tool observations locally before they ever reach OpenAI, Anthropic, or Azure OpenAI.
- **Layer 7 — Public Cloud API Edge (`Lakera Guard` / `Prisma AIRS` / `Cloudflare`)**: Monitors external end-user chat traffic hitting production customer-support endpoints.
