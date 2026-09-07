# FABRICATION DIRECTIVE — ord-2026-4f003b Context & Token Optimization Engine (v2.0)

## 1. MISSION CONTEXT
Fabricate an air-gapped, zero-marginal-cost Topological Context Firewall & Token Optimization Engine inside Heuristico Lab. The engine performs deterministic AST slicing of internal Python source trees, replacing executable method bodies with canonical typed ellipsis stubs (`...`) while preserving contractual type annotations, class hierarchies, docstrings, and sanitized precondition `raise` statements. Sliced structures are indexed into an embedded SQLite WAL cache with contention mitigation (`PRAGMA busy_timeout = 5000;`), ensuring sub-2ms retrieval latencies, 100% token savings on repeat analysis, topological multi-depth adaptation ($D_0, D_1, D_{2+}$), and zero cloud reliance.

## 2. INVIOLABLE CONSTRAINTS
1. **Zero External APIs & Air-Gapped Operation:** Pure local execution via Python Standard Library (`ast`, `sqlite3`, `hashlib`, `pathlib`) and Pydantic v2.
2. **Signature & Invariant Preservation:** Method names, arguments, return type annotations, decorators, and dataclass schemas must remain unmodified.
3. **Canonical Typed Stubs:** Replace method bodies with PEP 484 `...` (`ast.Constant(Ellipsis)`), not empty `pass`.
4. **Sanitized Precondition Raises:** Retain declared `raise` exceptions with argument sanitization (`raise ExceptionType("...")`) to prevent runtime secret and variable leaks.
5. **Topological Multi-Depth Firewall:**
   - **Distance 0 (Target File):** 100% full implementation retained untouched (`PruningDepth.FULL`).
   - **Distance 1 (Direct Dependencies):** Interface slicing (`PruningDepth.INTERFACE`).
   - **Distance 2+ (Transitive Dependencies):** Nominal class/dataclass stubs (`PruningDepth.NOMINAL`).
6. **Cache Invariant & Resiliency:** Primary key must be `SHA-256(source_code | rules_version | strip_docs | pruning_depth)` with `PRAGMA busy_timeout = 5000;`.
7. **FinOps & IP Security Ledger:** Export deterministic accounting of evaluated tokens, net tokens saved, and projected USD cost avoidance to `tests/finops_audit.json`.

## 3. VERIFICATION VECTORS
```bash
python -m py_compile contracts.py topological_resolver.py finops_auditor.py
pytest tests/ -v --tb=short
python -c "import sqlite3; con = sqlite3.connect(':memory:'); con.executescript(open('schema.sql').read()); print('SQL DDL Verified.')"
python scripts/demo_token_optimizer.py
```