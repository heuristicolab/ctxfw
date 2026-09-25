---
name: sprint-triage
description: Extrae telemetría del ledger SQLite local, analiza ratios de clonación de GitHub y ejecuta el triaje socrático P0 vs. Kill List para el siguiente sprint.
tools:
  - run_command
  - read_file
  - sql_query
triggers:
  - "triaje"
  - "sprint triage"
  - "analizar ledger"
  - "priorizar roadmap"
---

# MISSION & EXECUTION PROTOCOL
Ejecuta la auditoría de telemetría y destila el alcance del próximo sprint aplicando la navaja socrática contra el sobre-diseño.

## Procedimiento Operativo:
1. Inspecciona la existencia de bases de datos locales en `%LOCALAPPDATA%\ctxfw\tokens.db` o `~/.ctxfw/ledger.db`.
2. Ejecuta la consulta analítica:
   ```sql
   SELECT count(*) as total_cycles, sum(tokens_saved) as raw_tokens, sum(cost_saved_usd) as usd_saved FROM audit_ledger;
   ```
3. Si existen CSVs de tráfico de GitHub en la raíz, calcula el ratio Unique Cloners / Unique Visitors.
4. Ejecuta el filtro de tres pasos:
   - **Interrogación:** 3 preguntas de blast radius y latencia sobre las propuestas en cola.
   - **Triaje:** Asigna cada item a THE KILL LIST (congelado/descartado) o SPRINT P0 (mínima intervención).
   - **Axioma:** Redacta el delta formal para `SPEC.axioms.md` con su invariante negativa (`NEVER`).
5. Renderiza el reporte de triaje en Markdown estructurado.
