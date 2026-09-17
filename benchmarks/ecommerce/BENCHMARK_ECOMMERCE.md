# Empirical Benchmark: 52.8% Context Reduction on a Production E-Commerce Pipeline via Deterministic AST Pruning

Most autonomous agent degradation originates from passing raw implementation details and flat directories into LLM context windows. We evaluated `ctxfw` against a production transactional backend (FastAPI, Stripe webhooks, SQLAlchemy, Pydantic) to quantify token elimination across critical checkout, billing, and administrative paths.

---

## Benchmark Telemetry

| Target Module | Raw Tokens | Pruned Tokens | Reduction | Pruning Profile |
| :--- | :--- | :--- | :--- | :--- |
| `apps/api/main.py` | 21,695 | 5,933 | **-72.7%** | Truncates controller bodies to typed interface stubs |
| `apps/api/app/routes/checkout.py` | 12,248 | 6,050 | **-50.6%** | Strips DB/Stripe handlers; preserves Pydantic schemas |
| `apps/api/app/routes/webhooks.py` | 8,413 | 3,303 | **-60.7%** | Isolates event payloads; strips internal side-effects |
| `apps/api/app/routes/admin.py` | 13,569 | 8,538 | **-37.1%** | Retains routing trees; trims batch query logic |
| `apps/api/app/routes/checkin.py` | 4,489 | 3,773 | **-16.0%** | Preserves dense validation rules |
| `apps/api/app/core/database.py` | 1,416 | 997 | **-29.6%** | Preserves session factories; trims engine pooling |
| `apps/api/app/core/config.py` | 1,093 | 1,093 | **0.0%** | Invariant protection (Zero false-compression) |
| **Full Pipeline Lifecycle** | **62,923** | **29,687** | **-52.8%** | **33,236 bloat tokens pruned** |

---

## Architectural Invariants

- **Contract Integrity over Token Stripping**: Tree-Sitter discards imperatively executed function bodies while retaining nominal types, decorators, and function signatures intact. The agent reasons against exact interface contracts with zero syntax degradation.
- **D0 Zero-False-Compression Guarantee**: Declarative configuration boundaries (`config.py`) report an exact 0.0% pruning rate. Environment schemas and system manifests remain untouched when targeted at Distance 0.
- **FinOps Quantization**:
  - **33,236 tokens eliminated** per execution cycle.
  - **~$49.85 USD saved** every 500 agentic cycles (benchmarked against baseline input pricing of $3.00 / 1M tokens on Claude 3.5 Sonnet / GPT-4o).
  - **Attention Concentration**: Prevents middle-context retrieval degradation by restricting context bloat to surface-level API contracts.

---

## Verification & Reproduction

```bash
pip install --upgrade ctxfw
python benchmark_ecommerce.py
```
