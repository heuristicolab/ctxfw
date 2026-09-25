---
name: eval-benchmark
description: Ejecuta el arnés de evaluación empírica A/B comparando el baseline crudo contra la poda AST de ctxfw en el pipeline transaccional.
tools:
  - run_command
  - read_file
triggers:
  - "run evals"
  - "benchmark"
  - "medir ahorro"
  - "evaluar pipeline"
---

# MISSION & BENCHMARK HARNESS
Ejecuta pruebas comparativas de ingesta de contexto y mide la reducción real de tokens, TTFT y tasa de compilación sintáctica.

## Procedimiento Operativo:
1. Localiza el módulo de prueba (por defecto: pipeline FastAPI/Stripe o `tests/evals/`).
2. Mide la ingesta baseline (archivos completos en D0, D1 y D2) frente a la ingesta procesada por ctxfw.
3. Calcula métricas clave:
   - Tokens de prompt eliminados y porcentaje neto de poda (`-(Raw - Pruned) / Raw * 100`).
   - Delta de costo en USD (Input $3.00/1M, Output $15.00/1M).
   - Time-to-First-Token (TTFT) y rondas de subagentes requeridas.
4. Audita integridad sintáctica:
   - 0 alucinaciones de contratos o argumentos.
   - 100% esquemas Pydantic / TypeScript preservados.
5. Emite la Matriz de Telemetría Comparativa y añade un diagnóstico FinOps con nivel de cinismo configurable (roast).
