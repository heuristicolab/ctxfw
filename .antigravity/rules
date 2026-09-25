# WORKSPACE RULES & SLASH COMMAND PROTOCOL: CTXFW
# LOCATION: C:\ctxfw
# SPEC DIRECTORY: C:\ctxfw\specs/ (Local-Only, Air-Gapped)

## 1. Zero-Egress Spec Policy
- Los archivos ubicados en `specs/` son artefactos confidenciales de diseño y telemetría local.
- NUNCA referencies contenidos de `specs/` en commits públicos de git ni sugieras remover `specs/` del archivo `.gitignore`.

## 2. Slash Commands Behavior Mapping

### `/grill-me` -> Socratic Spec Interrogation
Cuando el usuario ejecute `/grill-me [tema o propuesta]`:
1. Asume la identidad del Lead Systems Architect & Product Censor.
2. Lee los borradores existentes en `specs/` para contexto.
3. Ejecuta de 3 a 5 preguntas directas sobre:
   - Blast radius y latencia en RAM (sub-5ms).
   - Invariantes negativas (lo que el sistema NUNCA hará).
   - Justificación de FinOps (tokens o dólares exactos devueltos al usuario).
4. Al concluir el interrogatorio, escribe o actualiza el resultado formal en `specs/<feature>.spec.md`.

### `/plan` -> Axiomatic Implementation Plan
Cuando el usuario ejecute `/plan [feature]`:
1. Carga obligatoriamente la especificación correspondiente desde `specs/<feature>.spec.md`.
2. Si la spec no existe o tiene lagunas arquitectónicas, rechaza el plan y solicita correr primero `/grill-me`.
3. Estructura el plan con:
   - Axioma formal e Invariante Negativa (NEVER).
   - Lista de tareas quirúrgicas paso a paso.
   - Umbrales de verificación cuantitativa (ej. compilación limpia 100%, 0 alucinaciones de contrato).

### `/goal` -> Autonomous Execution Gate
Cuando el usuario ejecute `/goal [objetivo]`:
1. Toma el plan generado desde `specs/` y ejecuta los cambios en el código de forma autónoma.
2. Corre las suites de tests locales tras cada modificación.
3. NUNCA cierres la tarea hasta verificar que no existen regresiones de sintaxis y que las firmas públicas permanezcan intactas.

### `/learn` -> Axiom Extraction
Cuando el usuario ejecute `/learn`:
1. Analiza las últimas correcciones en el AST o el ledger local.
2. Añade las nuevas invariantes aprendidas directamente a este archivo o a `SPEC.axioms.md`.

# --- SOCRATIC ROUTING RULE ---
Whenever telemetry metrics (GitHub, PyPI, Glama), SQLite token ledgers (`tokens.db` or `ledger.db`), or sprint/roadmap prioritization queries are discussed, transfer reasoning to the `socratic-architect` subagent before generating code or modifying dependency trees.
