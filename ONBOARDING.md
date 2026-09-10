# CTXFW // FIELD ONBOARDING PROTOCOL
### HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE
**Document ID:** `ONB-v3.5.0-BILINGUAL`  
**Security Classification:** `RESTRICTED BETA`  
**Sovereign Node:** `https://git.metaversemexico.mx/heuristicolab/arch-ord-2026-4f003b`

---

## [ EN ] ENGLISH VERSION

Welcome to the **Context Firewall (`ctxfw`) v3.5.0** field evaluation. CTXFW provides an out-of-band deterministic context firewall, AST-based dependency pruning, and axiomatic gatekeeping for agentic code workflows with zero probabilistic leniency.

### 1. System Prerequisites
* **Python Runtime**: Version `>= 3.10`.
* **Git Engine**: `>= 2.30` available in `PATH`.
* **Operating Systems**: Windows 10/11 (PowerShell & Git Bash), macOS (Darwin), Linux (Ubuntu/Debian, Fedora, Arch).
* **Target IDEs**: Google Antigravity, Cursor, Claude Desktop.

### 2. Single-Command Installation
Install the distribution wheel in your environment:
```bash
# Standalone Wheel Installation:
pip install ctxfw-3.5.0-py3-none-any.whl

# Or install directly via sovereign Git remote:
pipx install git+https://git.metaversemexico.mx/heuristicolab/arch-ord-2026-4f003b.git@v3.5.0
```

Verify binary registration in your system path:
```bash
ctxfw --help
```

### 3. 30-Second Zero-Touch Provisioning

#### A. Diagnostic Health & Stream Isolation Audit
Run the self-diagnostic suite to certify runtime health and verify stdio channel isolation:
```bash
ctxfw doctor
```
All indicators must return tactical emerald `[PASS]` and overall verdict `[HEALTHY] [ATTESTED]`.

#### B. Multi-IDE Global Injection
Inject the sovereign MCP server endpoints and governance directives across installed IDEs:
```bash
ctxfw init --global
```
*Non-destructive operation: Preserves external third-party MCP servers inside your IDE configuration files.*

#### C. Repository Perimeter Armor
Activate the pre-commit gatekeeper and deploy the canonical specification brief inside your active project:
```bash
cd /path/to/your/project
ctxfw init --repo .
```
This provisions:
- Canonical template `SPEC.axioms.md`.
- Sovereign pre-commit sentry `.git/hooks/pre-commit`.

### 4. The 2-Minute Litmus Test

#### Stage 1: Provoking Quarantined Interception
Create a deliberately ambiguous brief named `TEST_BRIEF.axioms.md`:
```markdown
# Intake Brief: Payment Processor
- We need a fast and secure payment system.
- Configurable timeout.
- Auto-retry on failure.
- System should never leak credentials.
```

Evaluate specification determinism:
```bash
ctxfw spec verify TEST_BRIEF.axioms.md
```
*Result:* Returns `[FAIL] SPECIFICATION QUARANTINED` ($\text{ACI} < 0.9000$, invariants floor violated).

Attempt staging and committing to Git:
```bash
git add TEST_BRIEF.axioms.md
git commit -m "feat: draft payment system"
```
The pre-commit sentry aborts the transaction in <80ms, preventing unverified code synthesis.

#### Stage 2: Quarantine Breach via Axiomatic Remediation
Update `TEST_BRIEF.axioms.md` with explicit variable bounds, deterministic FSM, 4-class error taxonomy, and 5 mandatory negative invariants:
```markdown
# Architectural Specification Brief: Payment Processor

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

Re-run formal evaluation:
```bash
ctxfw spec verify TEST_BRIEF.axioms.md
```
*Result:* Returns `[PASS] READY FOR FORGE` ($\text{ACI} = 1.0000$, cryptographic manifest hash emitted).

Commit to Git:
```bash
git add TEST_BRIEF.axioms.md
git commit -m "feat: verified payment processor"
```
The sentry authorizes the commit and logs the manifest seal to history.

---

## [ ES ] VERSIÓN EN ESPAÑOL

Bienvenido al programa de evaluación en campo de **Context Firewall (`ctxfw`) v3.5.0**. CTXFW proporciona compuertas axiomáticas deterministas, poda semántica de dependencias y aislamiento de contexto para flujos agénticos con cero complacencia probabilística.

### 1. Requisitos del Sistema
* **Entorno Python**: Versión `>= 3.10`.
* **Motor Git**: `>= 2.30` configurado en el `PATH`.
* **Sistemas Operativos**: Windows 10/11 (PowerShell y Git Bash), macOS (Darwin), Linux (Ubuntu/Debian, Fedora, Arch).
* **IDEs Soportados**: Google Antigravity, Cursor, Claude Desktop.

### 2. Instalación en un Solo Comando
Instala el paquete distribuible directamente en tu entorno:
```bash
# Instalación directa del Wheel:
pip install ctxfw-3.5.0-py3-none-any.whl

# O instalación directa desde el repositorio soberano:
pipx install git+https://git.metaversemexico.mx/heuristicolab/arch-ord-2026-4f003b.git@v3.5.0
```

Verifica la disponibilidad global del ejecutable:
```bash
ctxfw --help
```

### 3. Onboarding Zero-Touch en 30 Segundos

#### A. Autodiagnóstico de Salud y Aislamiento de Flujos
Ejecuta el verificador táctico para auditar la pureza del canal stdio y el motor SQLite WAL:
```bash
ctxfw doctor
```
Todos los indicadores deben responder en verde táctico `[PASS]` con veredicto general `[HEALTHY] [ATTESTED]`.

#### B. Inyección Multi-IDE Idempotente
Enchufa automáticamente los endpoints MCP y las directivas de gobernanza en tus editores instalados:
```bash
ctxfw init --global
```
*Operación no destructiva: Preserva intactos los servidores MCP de terceros en tus archivos de configuración.*

#### C. Blindaje Perimetral del Repositorio
Despliega el centinela pre-commit y el pliego axiomático canónico en tu proyecto:
```bash
cd /ruta/a/tu/proyecto
ctxfw init --repo .
```
Esto genera:
- La plantilla canónica `SPEC.axioms.md`.
- El hook soberano `.git/hooks/pre-commit`.

### 4. La Prueba de Fuego Guiada de 2 Minutos (The 2-Minute Litmus Test)

#### Etapa 1: Provocación de Cuarentena Deliberada
Crea un requerimiento deliberadamente incompleto llamado `TEST_BRIEF.axioms.md`:
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
*Resultado:* Retorna `[FAIL] SPECIFICATION QUARANTINED` ($\text{ACI} < 0.9000$, incumplimiento del piso de invariantes).

Intenta hacer commit en Git:
```bash
git add TEST_BRIEF.axioms.md
git commit -m "feat: draft pagos"
```
El centinela pre-commit aborta la transacción en <80ms, bloqueando el ingreso de código ambiguo.

#### Etapa 2: Ruptura de Cuarentena con Pliego Axiomático Formal
Edita `TEST_BRIEF.axioms.md` proveyendo cotas, FSM, taxonomía de errores y las 5 cláusulas never requeridas:
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

Vuelve a evaluar formalmente:
```bash
ctxfw spec verify TEST_BRIEF.axioms.md
```
*Resultado:* Retorna `[PASS] READY FOR FORGE` ($\text{ACI} = 1.0000$, hash de atestación criptográfica emitido).

Completa el commit en Git:
```bash
git add TEST_BRIEF.axioms.md
git commit -m "feat: modulo pagos verificado"
```
El centinela autoriza el commit e inscribe el sello de atestación en el historial.

---

<div align="center">
<sub>ENGINEERED & CLASSIFIED BY HEURISTICO LAB // SKUNK WORKS DIVISION</sub><br>
<sub>HIGH-ASSURANCE DEFENSE SYSTEMS GROUP</sub>
</div>
