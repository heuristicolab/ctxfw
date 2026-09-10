# Guía Rápida de Onboarding para Beta Testers: Context Firewall (`ctxfw`)

Bienvenido al programa de evaluación de **Context Firewall (`ctxfw`) v3.5.0**. Esta suite proporciona compuertas axiomáticas deterministas, poda semántica de dependencias y aislamiento de contexto para flujos agénticos con cero complacencia probabilística.

---

## 1. Requisitos Mínimos del Sistema
- **Python**: Versión `>= 3.10` (`py --version`, `python --version` o `python3 --version`).
- **Git**: `>= 2.30` configurado en el `PATH`.
- **Sistemas Operativos**: Windows 10/11 (PowerShell & Git Bash), macOS (Darwin), Linux (Ubuntu/Debian, Fedora, Arch).
- **IDEs Soportados**: Google Antigravity, Cursor, Claude Desktop.

---

## 2. Instalación en Un Solo Comando

Instala `ctxfw` directamente en tu entorno Python global o aislado (mediante `pipx` o `pip`):

```bash
# Opción recomendada para herramientas globales de CLI:
pipx install .

# O mediante pip en modo editable para desarrollo:
pip install -e .
```

Verifica la disponibilidad inmediata del binario sin configurar `$env:PYTHONPATH` a mano:
```bash
ctxfw --help
```

---

## 3. Onboarding Zero-Touch en 30 Segundos

### Paso A: Autodiagnóstico de Salud del Sistema
Ejecuta el verificador integral para auditar aislamiento `stdio`, base de datos SQLite WAL y dependencias:
```bash
ctxfw doctor
```
Deberás observar todos los indicadores en verde `[OK]` y el veredicto `[HEALTHY]`.

### Paso B: Configuración Global de IDEs
Inyecta automáticamente los perfiles del servidor MCP en tus IDEs instalados (Google Antigravity, Cursor, Claude Desktop):
```bash
ctxfw init --global
```
> [!NOTE]
> Esta operación es estrictamente **idempotente y no destructiva**: preserva todos tus servidores MCP de terceros preexistentes en `mcp_config.json`, `.cursor/mcp.json` o `claude_desktop_config.json`.

### Paso C: Blindaje del Repositorio Actual
Activa el perímetro axiomático y el hook de git pre-commit en tu proyecto de trabajo:
```bash
ctxfw init --repo .
```
Esto genera:
- La plantilla canónica `SPEC.axioms.md`.
- El hook `.git/hooks/pre-commit` que intercepta y bloquea commits en estado `QUARANTINED`.

---

## 4. La Prueba de Fuego Guiada de 2 Minutos (The 2-Minute Litmus Test)

Esta prueba demuestra cómo la compuerta axiomática de `ctxfw` protege el código contra alucinaciones o especificaciones ambiguas.

### Etapa 1: Provocar una Cuarentena Deliberada
Crea un archivo de requerimientos incompleto llamado `TEST_BRIEF.axioms.md`:

```markdown
# Intake Brief: Módulo Pagos
- Queremos un endpoint de pagos seguro y rápido.
- Timeout configurable.
- Si falla, reintentar.
- El sistema nunca debe exponer claves privadas.
```

Ejecuta la verificación formal:
```bash
ctxfw spec verify TEST_BRIEF.axioms.md
```

**Resultado Observado:**
```text
========================================================================
  CTXFW SPECIFICATION SIEVE -- AXIOMATIC DETERMINISM VERIFIER
========================================================================
Evaluated File:             TEST_BRIEF.axioms.md
ACI Score:                  0.0000
Negative Invariants Count:  1
Final Verdict:              [FAIL] SPECIFICATION QUARANTINED
Remediation Notes:
  - Negative invariants floor violated: found 1 distinct clauses, minimum required is 5 ('never' or 'shall never').
  - Axiom Completeness Index (ACI) 0.0000 is below activation threshold 0.9000.
  - Missing deterministic state machine (FSM) specification.
  - Missing explicit error taxonomy or quarantine routing specification.
  - Missing formal proof of correctness or cryptographic attestation seal.
========================================================================
```

Intenta commitear este archivo a Git:
```bash
git add TEST_BRIEF.axioms.md
git commit -m "feat: draft pagos"
```
El hook `.git/hooks/pre-commit` abortará la operación de inmediato, impidiendo la síntesis de código no verificable.

---

### Etapa 2: Romper la Cuarentena con un Pliego Axiomático Formal
Edita `TEST_BRIEF.axioms.md` proveyendo cotas, FSM y los 5 invariantes negativos obligatorios:

```markdown
# Architectural Specification Brief: Módulo Pagos

## 1. Domain Entities & Bounded Variables
- Variable `max_amount_cents`: integer bounded >= 1 and <= 100000000.
- Variable `gateway_timeout_ms`: integer bounded >= 100 and <= 5000.
- Variable `max_retries`: integer bounded >= 0 and <= 3.
- Variable `idempotency_ttl_sec`: integer bounded >= 60 and <= 86400.
- Variable `circuit_breaker_threshold`: integer bounded >= 3 and <= 10.
Bounds: 5 / 5

## 2. Deterministic State Machine (FSM)
Lifecycle states and transition map:
- States: DRAFT, QUARANTINED, VERIFIED, SEALED
- Transition delta(DRAFT, EVALUATE_DEFICIENT) -> QUARANTINED
- Transition delta(DRAFT, EVALUATE_COMPLIANT) -> VERIFIED
- Transition delta(QUARANTINED, REMEDIATE) -> DRAFT
- Transition delta(VERIFIED, SIGN_MANIFEST) -> SEALED
- Terminal State: SEALED is immutable. Boundary violation diverts to QUARANTINED.

## 3. Error Taxonomy & Quarantine
Formal error taxonomy isolates 4 fault domains:
- Class 1 (Transient Fault): Gateway timeout -> Exponential retry.
- Class 2 (Deterministic Input Fault): Validation error -> 400 Bad Request.
- Class 3 (Business & Specification Violation): Invariants violated -> Quarantine sink.
- Class 4 (Security & Isolation Violation): Key leak attempt -> Immediate halt.

## 4. Formal Proof & Cryptographic Attestation
Formal proof included: Mathematical induction validates inductive invariance across FSM state transitions.
Deterministic SHA-256 attestation seal guarantees manifest immutability.

## 5. Negative Invariants (Floor of 5 Required)
- System shall never process unauthenticated payment transactions.
- System shall never double-charge an identical idempotency key.
- System shall never log raw card numbers or CVV codes to stdout or disk.
- System shall never bypass quarantine sink during transaction failure.
- System shall never execute payment transfers without pre-allocating ledger balances.
```

Vuelve a evaluar:
```bash
ctxfw spec verify TEST_BRIEF.axioms.md
```

**Resultado:**
```text
========================================================================
  CTXFW SPECIFICATION SIEVE -- AXIOMATIC DETERMINISM VERIFIER
========================================================================
Evaluated File:             TEST_BRIEF.axioms.md
ACI Score:                  1.0000
Negative Invariants Count:  5
Final Verdict:              [PASS] READY FOR FORGE
Manifest Hash (SHA-256):    [HASH EMITIDO]
========================================================================
```

¡Ahora el commit pasa sin resistencia y el agente de IA está formalmente autorizado a sintetizar el código backend con el `manifest_hash` emitido!
