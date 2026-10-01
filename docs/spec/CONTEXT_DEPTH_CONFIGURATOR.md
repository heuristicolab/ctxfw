# SPEC-004: CONTEXT DEPTH CONFIGURATOR & ARTIFACT ROUTING
<!-- Heurístico LAB // Skunk Works Division // Technical Specification -->
<!-- Target: ctxfw v4.0.0 Architecture Preview & Local Testbed Protocol -->
<!-- Status: SPECIFICATION VERIFIED | Code Freeze: ACTIVE (v3.8.0 intact) -->
<!-- Pre-Mortem Integration & Dynamic Depth Governance -->
<!-- Attestation Manifest Hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3 -->
<!-- Axiom Completeness Index (ACI): 1.0000 | Status: VERIFIED -->

---

## 1. MARCO OPERATIVO Y AISLAMIENTO LOCAL

> [!IMPORTANT]
> **RESTRICTIVA OPERATIVA ABSOLUTA (CODE FREEZE):**
> La rama `main` en producción permanece sellada en `v3.8.0` (commit `4b98c78`).
> Este documento rige las pruebas empíricas locales en la rama `experiment/depth-configurator`.
> Queda prohibido cualquier push a ramas remotas hasta concluir la ventana de observación de 7 días.

---

## 2. ESQUEMA DE CONFIGURACIÓN FORMAL (`.ctxfwrc`)

Para gobernar dinámicamente la resolución de profundidad sin recompilar el binario ni alterar el comportamiento por defecto de producción (v3.8.0 = $D_2$), se introduce el contrato de configuración jerárquico.

### A. Precedencia de Configuración
1. **Variables de Entorno e Inyección por Cliente MCP (Prioridad Máxima - Runtime Override):**
   - Variables de entorno del sistema o bloque `env` inyectado por clientes MCP (`~/.claude.json`, `.cursor/mcp.json` o `claude_desktop_config.json`): `CTXFW_DEPTH`, `CTXFW_DISTRACTOR_BUDGET`.
   - Ejemplo de inyección desatendida en cliente MCP:
     ```json
     {
       "mcpServers": {
         "ctxfw": {
           "command": "ctxfw",
           "args": ["mcp"],
           "env": {
             "CTXFW_DEPTH": "3",
             "CTXFW_DISTRACTOR_BUDGET": "150"
           }
         }
       }
     }
     ```
2. **Archivo Local de Proyecto:** `.ctxfwrc` / `.ctxfw.json` en la raíz del espacio de trabajo.
3. **Configuración Global del Usuario:** `%LOCALAPPDATA%\ctxfw\config.json` (Windows) o `~/.config/ctxfw/config.json` (POSIX).
4. **Valores por Defecto Canónicos:** Nivel de producción $D_2$ (Topología nominal v3.8.0).

### B. Contrato Pydantic v2 Inmutable
```python
from enum import IntEnum
from pydantic import BaseModel, ConfigDict, Field

class ContextDepthLevel(IntEnum):
    PURE_PASSTHROUGH = 0      # D0: Exclusivamente archivo activo (100% lógica)
    DIRECT_INTERFACE = 1      # D1: Contratos directos y stubs tipados (...)
    TRANSITIVE_NOMINAL = 2    # D2: Firmas y clases nominales (Baseline v3.8.0)
    AMBIENT_CARTOGRAPHY = 3   # D3: Manifiesto léxico de coordenadas (v4.0 H1)

class CtxfwConfigDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_depth: ContextDepthLevel = Field(
        default=ContextDepthLevel.TRANSITIVE_NOMINAL,
        description="Profundidad topológica máxima para la resolución del grafo."
    )
    ambient_manifest: bool = Field(
        default=False,
        description="Habilitar generación de índice plano de símbolos a D3."
    )
    distractor_budget: int = Field(
        default=150,
        ge=20,
        le=500,
        description="Cota máxima de símbolos exportados inyectables en D3."
    )
    subsystem_clamping: bool = Field(
        default=True,
        description="Restringir D3 a los prefijos de paquete compartidos por D1/D2."
    )
    stale_reads_on_herd: bool = Field(
        default=True,
        description="Retornar snapshot SQLite previo ante cambios masivos de mtime."
    )
```

### C. Archivo de Muestra `.ctxfwrc`
```json
{
  "$schema": "https://ctxfw.heuristicolab.com/schemas/v4/config.json",
  "max_depth": 3,
  "ambient_manifest": true,
  "distractor_budget": 150,
  "subsystem_clamping": true,
  "stale_reads_on_herd": true
}
```

---

## 3. MATRIZ DE ENRUTAMIENTO POR ARQUETIPO DE PROYECTO

La profundidad no es un control de volumen financiero, sino un regulador de fidelidad contextual.

| Nivel | Nombre del Modo | Tipo de Proyecto Recomendado | Justificación Arquitectónica | Riesgo de Mala Configuración |
| :--- | :--- | :--- | :--- | :--- |
| **$D_0$** | **Pass-Through Puro** | Scripts autónomos, algoritmos aislados, CLI tools simples. | Máxima velocidad de inferencia (<10 ms). Cero distracción; el modelo no procesa dependencias externas. | Si el archivo consume lógica local, el agente alucinará contratos a ciegas. |
| **$D_1$** | **Contratos Directos** | Microservicios desacoplados (FastAPI, Go, NestJS), librerías DDD/Hexagonales. | Contratos estrictos de interfaces sin cadenas de herencia profundas. Preserva tipos y docstrings sin cuerpos. | Si existen fábricas o herencias multinivel, el modelo desconoce las clases base. |
| **$D_2$** | **Esqueleto Transitivo** | Monolitos web estándar (Django, Rails), plataformas COSS (PostHog), SDKs. | Resuelve modelos de datos y utilidades compartidas a 2 saltos. Estándar de producción actual. | En repositorios de más de 3,000 archivos, acumula ruido si el grafo es circular. |
| **$D_3$** | **Cartografía Ambiental** | Monorrepositorios masivos (Airflow), Turborepos, código legado con imports cruzados. | Elimina alucinaciones de imports (`ModuleNotFoundError`) entregando un índice plano de coordenadas. | En proyectos pequeños introduce ~1,500 tokens de texto que no aportan valor. |

---

## 4. ADICIÓN FORMAL AL RFC v4.0: SALVAGUARDAS DEL PRE-MORTEM

Se integran como invariantes negativas formales en la compuerta axiomática de la v4.0:

```text
AXIOM-17 (Dynamic Namespace Quarantine):
The D3 ambient manifest generator shall never emit a closed symbol list for modules
implementing PEP 562 '__getattr__', dynamic '__all__' expressions, or dynamic registries,
and must explicitly flag the namespace with the token '[DYNAMIC_UNBOUND:?]' to inhibit
negative absence hallucination by the agent.

AXIOM-18 (Throttled Warmup & Stale-Read Guarantee):
The D3 symbol resolution engine shall never execute synchronous inline re-parsing of more
than 20 cache-missed modules within a single request turn, and shall never block the primary
stdio JSON-RPC thread beyond 40 ms; it must return the last attested stale SQLite snapshot
and delegate re-indexing to an out-of-band asynchronous worker.

AXIOM-19 (Subsystem Boundary Clamping):
The D3 ambient manifest serializer shall never inject more than 1,000 net tokens of D3
symbols into a prompt, and shall strictly reject modules crossing outside the architectural
subsystem boundary of the D1/D2 ancestors unless explicitly resolved in the topological call-chain.

AXIOM-20 (Configuration Depth Ceiling):
The configuration engine shall never parse or execute topological depth expansions
strictly exceeding depth level 3 (D > 3), and shall reject malformed numeric depth values.

AXIOM-21 (Zero Telemetry Leakage in Config):
The configuration loader shall never transmit .ctxfwrc contents, workspace paths,
or environment variable overrides outside the local host runtime.
```

---

## 5. PROTOCOLO DEL AGENTE MONITOR (ANTIGRAVITY TESTBED WATCHDOG)

### Directiva de Supervisión Local
El agente auditor en Antigravity ejecutará el análisis forense de cada sesión sin mutar código de producción ni hacer commits a main.

### Tareas del Agente:
1. **Inspección de Persistencia:** Leer `%LOCALAPPDATA%\ctxfw\tokens.db` tras cada invocación del agente.
2. **Cálculo de Variables Clave:**
   - Tokens brutos solicitados vs. tokens finales entregados.
   - Latencia de consulta de caché ($t_{hit}$) vs. latencia de análisis sintáctico ($t_{parse}$).
   - Verificación de First-Pass Yield (¿el código propuesto requirió corrección de imports?).
3. **Registro Continuo:** Actualizar la bitácora local `docs/benchmarks/LOCAL_TESTING_JOURNAL.md`.

---

## 6. FORMAL PROOF OF CORRECTNESS & CRYPTOGRAPHIC ATTESTATION

- **Explicit Bounds:** 5 / 5 bounded variables.
  * Variable 1: Max depth range ($D \in [0, 3]$, integer).
  * Variable 2: Distractor budget range ($S \in [20, 500]$, symbols).
  * Variable 3: Sync re-parsing threshold ($M_{sync} \le 20$, modules).
  * Variable 4: Latency budget limit ($t_{latency} \le 40.0$, ms).
  * Variable 5: Max D3 prompt token ceiling ($T_{D3} \le 1,000$, tokens).

- **Deterministic Finite State Machine (FSM):**
  * $S_0$: `UNCONFIGURED` $\to \delta(S_0, \text{LOAD\_CONFIG}) \to S_1$ (`CONFIG_LOADED`)
  * $S_1$: `CONFIG_LOADED` $\to \delta(S_1, \text{VALIDATE\_DEPTH}) \to S_2$ (`ACTIVE_DEPTH`)
  * $S_1$: `CONFIG_LOADED` $\to \delta(S_1, \text{BOUND\_BREACH}) \to S_5$ (`TERMINAL_QUARANTINED`)
  * $S_2$: `ACTIVE_DEPTH` $\to \delta(S_2, \text{QUERY\_TOPOLOGY}) \to S_3$ (`BUNDLE_COMPOSED`)
  * $S_3$: `BUNDLE_COMPOSED` $\to \delta(S_3, \text{COMPLETE}) \to S_4$ (`TERMINAL_VERIFIED`)
  * $S_3$: `BUNDLE_COMPOSED` $\to \delta(S_3, \text{TIMEOUT\_ERROR}) \to S_5$ (`TERMINAL_QUARANTINED`)
  * **Terminal States:** $S_4$ (`TERMINAL_VERIFIED`), $S_5$ (`TERMINAL_QUARANTINED`).

- **4-Tier Fault Taxonomy & Quarantine:**
  * **Class 1 (Transient System Faults):** Transient IO read error on `.ctxfwrc` (remediated by fallback to default $D_2$).
  * **Class 2 (Deterministic Input & Syntax Faults):** Syntax error in `.ctxfwrc` JSON (remediated by warning to stderr and fallback to $D_2$).
  * **Class 3 (Business Logic & Quarantine Violations):** Out-of-bounds depth value $D > 3$ (remediated by clamping to $D_2$ and quarantine alert).
  * **Class 4 (Security & Perimeter Violations):** Environment exfiltration or path escape attempt (remediated by immediate halt).
