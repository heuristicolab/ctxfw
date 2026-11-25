<!-- manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546 -->
# Production Case Study: Autonomous Red-Team MCP Defense & Deterministic Burst Hardening (2026-11-25)

**Audience:** AI Security Engineers, MCP Architects, FinOps Leads, CISOs (`ctxfw.heuristicolab.com`)  
**Protected Surface:** Public HTTP-to-MCP gateway (`POST /api/mcp/invoke` on `danteix.com`) governed by **CTXFW Core (`Plane 0`, hardened in `v4.2.2`)** + **CTXFW Enterprise (`Plane 1`, hardened in `v1.0.2`)**  
**Formal Core Burst Guard Spec (`ctxfw_mcp_burst_guard_v1`):** `f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546` (`VERIFIED`, `ACI: 1.0000`)  
**Formal Enterprise LRU Pool Spec (`ctxfw_enterprise_vault_lru_v1_0_2`):** `5031fb46f69b9c3c8d29548d34786f7356d1a3e0c7cafc2c78954a50a3c338f3` (`VERIFIED`, `ACI: 1.0000`)

---

## 1. Executive Summary

On **November 25, 2026**, between **03:16:53 and 04:06:46 CST** (`09:16–10:06 UTC`), the public Model Context Protocol (MCP) endpoint serving Dante IX was targeted by an automated 50-minute red-team security scanner (**`571` HTTP `POST /api/mcp/invoke` requests** in Nginx access logs / **`568` WAL-audited gateway events**) firing against unauthenticated `FREE_TRIAL` tools from residential/mobile block `CMNET` (`117.144.0.0/12`, masked source `117.147.90.x`, peak rate `27 req/min` at `03:40`).

Forensic inspection of Nginx logs, `dante_sara.db`, `dante_tokencast.db`, and isolated sandbox SQLite WAL ledgers confirmed three decisive operational facts:

1. **Zero Security Breaches & `$0.0000 USD` Upstream LLM Spend:** The automated fuzzer systematically probed **SSTI** (`{{4292*3932}}`, `${''.class.superclass}`), **multi-language code eval** (Python/JS/Ruby/Shell), **time-based blind RCE** (`sleep(5)`), **CLI/SSH `-oProxyCommand=` OOB callbacks**, **path traversal**, **brand spoofing**, and **indirect prompt injection**. Every single attack failed (**`0` code executions**, **`0` leaked secrets**, **`0` cross-tenant leaks**, **`$0.0000 USD`** upstream LLM cost).
2. **`38` Live Pre-Execution `CTXFW SARA` Interventions:** Zero-Knowledge SQLite audits in `dante_sara.db` confirm **`38` live `CTXFW SARA` interventions** on `dante_mcp_query` (`18` hard `QUARANTINE_TOOL` blocks at `risk_score 0.8000–0.9000` + `20` `STRIP_COMMANDS` command-neutralization rewrites at `risk_score 0.4500`), backed by `2` `MCP-08` schema contract rejections, `196` Split-Brand Trojan blocks, `53` Tenant Path Traversal blocks, and `1` SSTI XML-parser rejection.
3. **Honest Availability Postmortem & Coordinated `v4.2.2` + `v1.0.2` Hardening:** **`182` syntactically valid `FREE_TRIAL` calls** carrying unique payload strings spun up `118` isolated storage directories (~11 SQLite WAL files each), hitting **`1,020 / 1,024` file descriptors (`EMFILE`)**. That infrastructure insight shipped dual native hardening: **`ctxfw v4.2.2`** (`McpBurstRateLimiter` in Open-Core) and **`ctxfw-enterprise v1.0.2`** (bounded LRU runtime pool `max_active_runtimes=16`, atomic `provision_vault` rollback, and `SandboxVaultPolicy`).

---

## 2. Verified Production Telemetry

| Forensic Metric | Production Observation (2026-11-25) | Verification Source |
| :--- | :--- | :--- |
| **Attack Window** | `03:16:53` – `04:06:46 CST` (`50` min, peak `27 req/min`) | Nginx access log + WAL ledgers |
| **Source Network / Tool Fingerprint** | `CMNET` (`117.144.0.0/12`, masked `117.147.90.x`) · `McpfTest` / `--clx*` fuzzer | Cloudflare real-IP header + `dante_wal.db` |
| **Volume Observed** | **`571`** HTTP requests (`568` WAL-audited MCP calls) | Nginx `access.log` + edge telemetry WAL |
| **Target Tier** | Unauthenticated `FREE_TRIAL` preview mode | Zero-Knowledge invocation ledger |
| **Upstream LLM Expenditure** | **`$0.0000 USD`** (verified `compute_cost_usd = 0.0`) | FinOps ledger (`TokenCast`) |
| **Secrets / Key Material Disclosed** | **`0`** (RSA, Ed25519, KEKs intact) | Cryptographic boundary & DLP audit |
| **Peak Process File Descriptors** | **`1,020 / 1,024`** open FDs (Linux default soft limit) | Runtime kernel process limits |

---

## 3. Forensic Payload Signatures & Active Defense Breakdown

### A. Captured Automated Fuzzer Probes (`FREE_TRIAL` Sandbox — `0` Executions)

| Attack Vector Probed | Exact Payloads Logged in Isolated Sandbox | Execution Outcome |
| :--- | :--- | :--- |
| **SSTI (Jinja2 / Java EL / Ruby / Format)** | `{{4292*3932}}`, `${4292*3932}`, `#{4292*3932}`, `{{"".__class__.__mro__}}`, `{0.__class__.__mro__}`, `${''.class.superclass}` | **0 executed.** Inert literal storage; `${''.class.superclass}` cleanly aborted XML PDF parsing (`unknown_charref`). |
| **Polyglot `eval()` / Shell Arithmetic** | `ord("M")*4292`, `"M".charCodeAt(0)*4292`, `"M".ord*4292`, `len("McpfTest")*4292`, `print(4292*3932)`, `echo 4292*3932;` | **0 executed.** Never reached Python `eval()`, JS engines, or shell subprocesses. |
| **Time-Based Blind RCE (`sleep 5`)** | `__import__("time").sleep(5)`, `const _t=Date.now()+5000;while(Date.now()<_t){};0`, `sleep(5)`, `sleep(5);` | **0 executed.** Deterministic preview execution held zero delay amplification. |
| **CLI Flag & SSH `ProxyCommand` OOB Injection** | `--clxcfb0870b99`, `--clx470c2227e1=1`, `--version`, `-oProxyCommand=wget -qO- ...`, `-oProxyCommand=curl ...` | **0 executed / 0 egress.** No shell invocation from tool target fields. |

### B. Security Gate & `CTXFW SARA` Interventions (`290` Security Actions Logged)

| Defense Layer | Count | Verdict / Error Code | Neutralized Attack Vector |
| :--- | :---: | :--- | :--- |
| **CTXFW SARA Hard Quarantine (`Plane 0`)** | **`18`** | `QUARANTINE_TOOL` (`QUARANTINED_BY_SARA`, `risk_score 0.8000–0.9000`) | High-risk indirect prompt injections embedded inside `dante_mcp_query`. |
| **CTXFW SARA Command Stripping (`Plane 0`)** | **`20`** | `STRIP_COMMANDS` (`risk_score 0.4500`, SHA-256 Zero-Knowledge log) | Medium-risk imperative/role directives neutralized prior to execution. |
| **Anti-Trojan Coherence Lock** | **`196`** | `ERR_SECURITY_SPLIT_BRAND_TROJAN` (`98` forge shield + `98` remediation) | Brand-spoofing splits trying to poison generated `llms.txt` / schema artifacts. |
| **Tenant Traversal Shield** | **`53`** | `ERR_SECURITY_TENANT_PATH_TRAVERSAL` (`38` forge shield + `15` remediation) | `..` traversals, separators, `NUL` bytes, and `tenant_id_hash` spoofing. |
| **MCP-08 Schema Contract Gate** | **`2`** | `QUARANTINED_BY_GATE` | Deterministic JSON contract violation (`INVALID_PARAMS`). |
| **Hardened PDF/XML Parser** | **`1`** | Clean non-executing parser rejection (`unknown_charref`) | SSTI `${''.class.superclass}` payload neutralized without env access. |

> **FinOps Isolation Guarantee:** All **`182`** syntactically valid `FREE_TRIAL` calls (`121` friction queries, `45` audits, `16` GEO share probes) remained strictly inside deterministic preview mode with **`$0.0000 USD` upstream OpenRouter spend**.

---

## 4. Availability Postmortem: Asymmetric File-Descriptor Exhaustion (`EMFILE`)

At **`03:20:32 CST`**, sequential provisioning of **`118` distinct per-payload storage workspaces** (~11 SQLite WAL files per workspace) pushed open process descriptors to **`1,020 / 1,024`**, causing **`15` HTTP `500`** errors in Nginx alongside transient WAL failures:

- `57` `sqlite3.OperationalError: unable to open database file` exceptions.
- `18` `[Errno 24] Too many open files` (`EMFILE`) OS socket/file failures.
- `31` secondary `VaultRegistry: Duplicate vault_slug` errors due to missing atomic rollback on transient hydration faults.

---

## 5. Dual Native Remediation: `ctxfw v4.2.2` + `ctxfw-enterprise v1.0.2`

1. **CTXFW Core `v4.2.2` — Native MCP Burst Guard (`ctxfw_mcp_burst_guard_v1`):**
   - Ships **`McpRateLimitPolicyDTO`** and **`McpBurstRateLimiter`** in [`ctxfw.mcp_guard.rate_limiter`](../../src/ctxfw/mcp_guard/rate_limiter.py) wired into `MCPServer` (`enabled=False` opt-in default for 100% backward compatibility).
   - Uses exact scaled integer millitoken math (`SCALE = 60_000`, `Decimal("0.0001")` — zero IEEE-754 float drift), injectable millisecond `Clock` with monotonic fail-closed regression clamping, bounded LRU client tracking (`[16, 4096]`), **Zero-Knowledge SHA-256 `client_key_hash`** isolation (raw IPs/keys are never persisted), Class 3 **`ERR_RATE_LIMIT_EXCEEDED`** blocks, and append-only SQLite WAL table `rate_limit_audit_logs` protected by `MCG_INV_10` immutability triggers.
   - Sealed at `ACI 1.0000` (`manifest_hash: f1329ba9...2546`) with **`673/673` passing tests** and `ALLOW_MERGE` across SWE-Gate (`cyclomatic_delta <= 9`).
2. **CTXFW Enterprise `v1.0.2` — Native LRU Pool & Atomic Provisioning (`ctxfw_enterprise_vault_lru_v1_0_2`):**
   - Bounded LRU `EnterpriseVaultOrchestrator` pool (`max_active_runtimes=16`, clamped `[2, 32]`, env `CTXFW_ENTERPRISE_MAX_ACTIVE_VAULTS`), transparent rehydration for evicted vaults while preserving fail-closed rejection for unknown slugs, atomic `provision_vault` + `unregister_vault` rollback on transient I/O faults, complete FD closure across `VaultRuntimeState.close()` + `EnterpriseKernelAuditBridge`, and official `SandboxVaultPolicy` / `resolve_sandbox_or_tenant_slug`.
   - Sealed at `ACI 1.0000` (`manifest_hash: 5031fb46...38f3`) with `95` passing tests and `ALLOW_MERGE` across 6 atomic commits.
3. **Production Edge & OS Controls:**
   - Dedicated single `FREE_SANDBOX_TENANT_ID` (`1` sandbox workspace regardless of `N` inputs), Nginx Cloudflare-aware rate limiting (`12 req/min`, `burst=15`, HTTP `429`), and `LimitNOFILE=65536`.

---

## 6. Why Pre-Execution MCP Governance Matters

- **Payload-Depth Sanitization vs. Perimeter WAFs:** All `38` prompt injections, `196` split-brand trojans, and `53` path traversals traveled inside valid `POST /api/mcp/invoke` JSON arguments that HTTP WAFs pass straight through.
- **Forensic Auditability Without PII Leaks:** `dante_sara.db`, `TraceKit`, and `rate_limit_audit_logs` reconstructed every attack phase cleanly using SHA-256 digests (`Zero-Knowledge`) while leaving zero caller secrets or IPs exposed in ledgers.
- **Closed-Loop Engineering (`Spec -> TDD -> SWE-Gate`):** Both `ctxfw v4.2.2` and `ctxfw-enterprise v1.0.2` converted a live production availability insight into formally attested, regression-tested defenses within hours.
