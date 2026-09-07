# FABRICATION DIRECTIVE — ord-2026-4f003b Context & Token Optimization Engine

## 1. MISSION CONTEXT
Fabricate an air-gapped, zero-marginal-cost Context & Token Optimization Engine inside Heuristico Lab. The engine performs deterministic AST slicing of Python source trees, replacing executable method bodies with `pass` while preserving contractual type annotations, class hierarchies, and interfaces. Sliced structures are indexed into an embedded SQLite WAL cache, ensuring sub-2ms retrieval latencies, 100% token savings on repeat analysis, and zero cloud reliance.

## 2. INVIOLABLE CONSTRAINTS
1. **Zero External APIs:** Pure local execution via Python Standard Library (`ast`, `sqlite3`, `hashlib`) and Pydantic v2.
2. **Signature Preservation:** Method names, arguments, return signatures, decorators, and dataclass schemas must remain unmodified.
3. **Cache Invariant:** Primary key must be `SHA-256(source_code | rules_version | strip_docs)`.
4. **Target Latency:** Cold AST slicing $\le 15\text{ ms}$; Warm WAL lookup $\le 2\text{ ms}$.
5. **Context Reduction:** Minimum character and estimated token reduction threshold of $\ge 35\%$.

## 3. VERIFICATION VECTORS
```bash
python -m py_compile contracts.py tests/test_contracts.py
pytest tests/ -v --tb=short
sqlite3 :memory: < schema.sql
```