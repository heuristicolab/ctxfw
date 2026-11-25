<!-- manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546 -->
# CTXFW v4.2.2 Release Notes — Native Deterministic MCP Burst Guard & Live Red-Team Hardening

- **Release Date:** 2026-11-25
- **Formal Specification Seal (`ctxfw_mcp_burst_guard_v1`):** `VERIFIED` · `ACI: 1.0000` · `manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546`
- **Axiom Specification Ledger:** [SPEC.axioms.md — Appendix L](../SPEC.axioms.md) (`78` negative invariants, `ACI: 1.0000`)
- **Automated Test Suite:** **`673 / 673` passing tests (`0` failed)** across Core, `SARA`, `mcp_guard`, `PASAC`, `TaskAuth`, `Cadence`, `TraceLite`, `Provenance`, `test_mcp_burst_guard.py`, and docs parity.
- **SWE-Gate (`ctxfw.evaluate_patch`, `max_cyclomatic_delta=10`, `forbid_type_ignores=True`):** `ALLOW_MERGE` across all `v4.2.2` modules (`cyclomatic_delta` `0..9`, zero architectural violations).

---

## 1. What Changed in `ctxfw v4.2.2`

1. **Deterministic Zero-Drift MCP Burst Rate Limiter (`ctxfw.mcp_guard.rate_limiter` + `MCPServer`):**
   - Added frozen configuration contract **`McpRateLimitPolicyDTO`** (`enabled=False` opt-in default for 100% backward compatibility with `v4.2.1` and `ctxfw-enterprise v1.0.1+`, `requests_per_minute [1..60000]`, `burst_capacity [1..10000]`, `cost_per_call [1..100] <= burst_capacity`, `max_tracked_clients [16..4096]`, strict rejection of `float`/`bool`, and `from_env()` parsing `CTXFW_MCP_RATE_LIMIT_*`).
   - Added **`McpBurstRateLimiter`** using exact scaled integer millitokens (`SCALE = 60_000`) and quantized `Decimal("0.0001")` formatting (zero IEEE-754 floating-point drift), injectable integer millisecond `Clock` with monotonic high-water fail-closed regression clamping (`elapsed_ms = max(0, now_ms - last_refill_ms)`), and bounded LRU client tracking (`OrderedDict`).
   - Enforced **Zero-Knowledge SHA-256 identity isolation**: caller hints (`_meta.client_key_hash`, `client_key`, `client_id`, `cf_connecting_ip`) are hashed via `derive_client_key_hash` (`^[a-f0-9]{64}$`); raw IPs and API keys never touch `mcp_guard.db` or `TraceKit`.
   - Added append-only SQLite WAL table `rate_limit_audit_logs` in `mcp_guard/schema.sql` sealed with `MCG_INV_10` immutability triggers (`BEFORE UPDATE` / `BEFORE DELETE`), recording Class 3 **`ErrorClass.BUSINESS`** / **`ERR_RATE_LIMIT_EXCEEDED`** rejections with exact `retry_after_ms`.
   - Integrated lazily into `ctxfw.mcp_guard.__init__`, `ctxfw.mcp.MCPServer`, and `ctxfw.mcp_server` while preserving zero eager `sqlite3` imports.

2. **Verified Live Red-Team Production Case Study (`2026-11-25`):**
   - Published bilingual forensic case study ([EN](case-studies/redteam-mcp-defense-2026-11-25.md) | [ES](case-studies/redteam-mcp-defense-2026-11-25.es.md)) covering `571` live HTTP requests (`568` WAL-audited) from an automated MCP fuzzer (`$0.0000 USD` LLM spend, `0` secret/cross-tenant leaks, **`38` live `CTXFW SARA` interventions**, `2` `MCP-08` blocks, `196` Split-Brand Trojan, `53` Tenant Path Traversal, `1` SSTI XML rejection) and coordinated dual hardening with **`ctxfw-enterprise v1.0.2`**.

---

## 2. SWE-Gate Attestation Ledger

| Module | Evaluation ID | Verdict | Cyclomatic Delta |
| :--- | :--- | :--- | :---: |
| `src/ctxfw/mcp_guard/contracts.py` | `EVL-d56de96dd47df2aa` | `ALLOW_MERGE` | `4` |
| `src/ctxfw/mcp_guard/rate_limiter.py` | `EVL-432757bc48257f8e` | `ALLOW_MERGE` | `8` |
| `src/ctxfw/mcp_guard/store.py` | `EVL-f19ab16e0e87e96a` | `ALLOW_MERGE` | `8` |
| `src/ctxfw/mcp_guard/__init__.py` | `EVL-ab1c490e9c70ebca` | `ALLOW_MERGE` | `0` |
| `src/ctxfw/mcp.py` | `EVL-c6bf89d572164063` | `ALLOW_MERGE` | `9` |
| `src/ctxfw/mcp_server.py` | `EVL-eba32ddcd64e1737` | `ALLOW_MERGE` | `1` |
