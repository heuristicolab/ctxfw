# FABRICATION DIRECTIVE — ord-2026-4f003b Context & Token Optimization Engine (v3.0)

## 1. MISSION CONTEXT
Fabricate an air-gapped, zero-marginal-cost Topological Context Firewall, Polyglot Token Optimization Engine, and Perimeter Ingress Gateway inside Heuristico Lab. The engine performs deterministic AST and Tree-sitter slicing of multi-language source trees (Python, TypeScript, JavaScript, Go, Java), replacing executable bodies with canonical typed ellipsis stubs (`...`) while preserving contractual type annotations, class hierarchies, docstrings, and sanitized precondition `raise` statements. Sliced structures are indexed into an embedded SQLite WAL cache with contention mitigation (`PRAGMA busy_timeout = 5000;`), ensuring sub-2ms retrieval latencies, 100% token savings on repeat analysis, topological multi-depth adaptation ($D_0, D_1, D_{2+}$), MCP server integration, transparent fail-open reverse proxying, and zero cloud reliance.

## 2. INVIOLABLE CONSTRAINTS
1. **Zero Cloud Network Dependency & Hermetic CI:** Pure local execution via Python Standard Library (`ast`, `sqlite3`, `hashlib`, `pathlib`), Tree-sitter, Pydantic v2, and Starlette/FastAPI mock transports.
2. **Signature & Invariant Preservation:** Method names, arguments, return type annotations, decorators, and dataclass schemas must remain unmodified.
3. **Canonical Typed Stubs:** Replace method bodies with PEP 484 `...` (`ast.Constant(Ellipsis)`), not empty `pass`.
4. **Sanitized Precondition Raises:** Retain declared `raise` exceptions with argument sanitization (`raise ExceptionType("...")`) to prevent runtime secret and variable leaks.
5. **Topological Multi-Depth Firewall:**
   - **Distance 0 (Target File):** 100% full implementation retained untouched (`PruningDepth.FULL`).
   - **Distance 1 (Direct Dependencies):** Interface slicing (`PruningDepth.INTERFACE`).
   - **Distance 2+ (Transitive Dependencies):** Nominal class/dataclass stubs (`PruningDepth.NOMINAL`).
6. **Cache Invariant & Resiliency:** Primary key must be `SHA-256(source_code | rules_version | strip_docs | pruning_depth | language)` with `PRAGMA busy_timeout = 5000;`.
7. **Empirical A/B Eval Harness:** Verifiable pass@1 rate with zero degradation ($\Delta\text{pass@1} \ge 0.0\%$) and $>40\%$ token reduction evaluated hermetically in isolated subprocess sandboxes.
8. **Strict stdio MCP Server (v2024-11-05):** Clean stdio stream hygiene writing valid JSON-RPC 2.0 frames to `stdout` and diagnostic logs to `stderr`.
9. **Fail-Open Reverse Proxy Gateway:** Transparent proxying for `/v1/chat/completions` and `/v1/messages` with sub-5ms warm cache overhead and fail-open bypass on invalid syntax or `X-Context-Firewall-Bypass: true`.
10. **FinOps & CI Gatekeeper:** Automated PR changeset perimeter analysis, GitHub Actions Job Summary table generation, and `.pre-commit-config.yaml` export.

## 3. VERIFICATION VECTORS
```bash
python -m py_compile contracts.py topological_resolver.py finops_auditor.py polyglot_pruner.py mcp_server.py proxy_gateway.py ci_gatekeeper.py
pytest tests/ -v --tb=short
python scripts/run_evals.py --mock
powershell -ExecutionPolicy Bypass -File .\checkpoint.ps1
```