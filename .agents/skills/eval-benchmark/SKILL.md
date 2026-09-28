---
name: eval-benchmark
description: Executes the empirical A/B evaluation harness comparing raw baseline ingestion against ctxfw AST pruning across transactional pipelines.
tools:
  - run_command
  - read_file
triggers:
  - "run evals"
  - "benchmark"
  - "measure savings"
  - "evaluate pipeline"
---

# MISSION & BENCHMARK HARNESS
Executes comparative context ingestion benchmarks measuring real token mass reduction, TTFT, and syntactic compilation rates.

## Operating Procedure:
1. Locate the benchmark test module (default: FastAPI/Stripe pipeline or `tests/evals/`).
2. Measure baseline ingestion (unpruned full files across D0, D1, and D2) against ctxfw-processed context.
3. Compute critical metrics:
   - Eliminated prompt tokens and net pruning percentage (`-(Raw - Pruned) / Raw * 100`).
   - Avoided USD inference expenditure (Input $3.00/1M, Output $15.00/1M tokens).
   - Time-to-First-Token (TTFT) latency delta and required agent turn iterations.
4. Audit syntactic integrity:
   - 0 contract or argument signature hallucinations.
   - 100% Pydantic / TypeScript schemas intact and valid.
5. Emit the Comparative Telemetry Matrix with a configurable FinOps diagnostic audit (cynical roast level).
