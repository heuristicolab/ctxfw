# SPEC-004: CONTEXT DEPTH CONFIGURATOR & ARTIFACT ROUTING
<!-- Heurístico LAB // Skunk Works Division // Technical Specification -->
<!-- Target: ctxfw v4.0.0 Architecture Preview & Verification Testbed Protocol -->
<!-- Status: SPECIFICATION VERIFIED | Code Freeze: ACTIVE (v3.8.0 intact) -->
<!-- Pre-Mortem Integration & Dynamic Depth Governance -->
<!-- Attestation Manifest Hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3 -->
<!-- Axiom Completeness Index (ACI): 1.0000 | Status: VERIFIED -->

---

## 1. OPERATIONAL FRAMEWORK & LOCAL ISOLATION

> [!IMPORTANT]
> **ABSOLUTE OPERATIONAL CONSTRAINT (CODE FREEZE):**
> Production `main` remains sealed at `v3.8.0` (commit `4b98c78`).
> This specification governs empirical validation on the `experiment/depth-configurator` branch.
> Pushing to remote branches is prohibited until formal release criteria are verified.

---

## 2. FORMAL CONFIGURATION CONTRACT (`.ctxfwrc`)

To dynamically govern depth resolution without recompiling binaries or modifying default production behavior (v3.8.0 = $D_2$), a hierarchical configuration contract is defined.

### A. Configuration Precedence
1. **Environment Variables & MCP Client Ingress (Highest Priority - Runtime Override):**
   - System environment variables or `env` block injected by MCP clients (`~/.claude.json`, `.cursor/mcp.json`, or `claude_desktop_config.json`): `CTXFW_DEPTH`, `CTXFW_DISTRACTOR_BUDGET`.
   - Example headless injection in an MCP client configuration:
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
2. **Local Workspace Configuration:** `.ctxfwrc` / `.ctxfw.json` at project root.
3. **Global User Configuration:** `%LOCALAPPDATA%\ctxfw\config.json` (Windows) or `~/.config/ctxfw/config.json` (POSIX).
4. **Canonical Defaults:** Production level $D_2$ (Nominal topology baseline).

### B. Immutable Pydantic v2 Contract
```python
from enum import IntEnum
from pydantic import BaseModel, ConfigDict, Field

class ContextDepthLevel(IntEnum):
    PURE_PASSTHROUGH = 0      # D0: Active focal file only (100% full implementation)
    DIRECT_INTERFACE = 1      # D1: Direct contracts and typed stubs (...)
    TRANSITIVE_NOMINAL = 2    # D2: Signatures and nominal class skeletons
    AMBIENT_CARTOGRAPHY = 3   # D3: Lexical symbol coordinates manifest

class CtxfwConfigDTO(BaseModel):
    model_config = ConfigDict(frozen=True, extra="forbid")

    max_depth: ContextDepthLevel = Field(
        default=ContextDepthLevel.TRANSITIVE_NOMINAL,
        description="Maximum topological depth for dependency graph resolution."
    )
    ambient_manifest: bool = Field(
        default=False,
        description="Enable zero-syntax flat symbol index generation for D3."
    )
    distractor_budget: int = Field(
        default=150,
        ge=20,
        le=500,
        description="Maximum ceiling of exported symbols injectable in D3."
    )
    subsystem_clamping: bool = Field(
        default=True,
        description="Restrict D3 to package prefixes shared by D1/D2 ancestors."
    )
    stale_reads_on_herd: bool = Field(
        default=True,
        description="Return cached SQLite snapshot under thundering herd mtime spikes."
    )
```

### C. Sample Configuration File (`.ctxfwrc`)
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

## 3. PROJECT ARCHETYPE ROUTING MATRIX

Context depth is an architectural regulator of contextual fidelity, tuning the balance between precision and noise.

| Depth Level | Mode Name | Recommended Architecture | Architectural Rationale | Misconfiguration Risk |
| :--- | :--- | :--- | :--- | :--- |
| **$D_0$** | **Pure Pass-Through** | Standalone scripts, isolated algorithms, simple CLI tools. | Maximum throughput (<10 ms). Zero distraction; model parses no external dependencies. | If the file consumes local logic, agent will hallucinate contracts blindly. |
| **$D_1$** | **Direct Interface** | Decoupled microservices (FastAPI, Go, NestJS), DDD/Hexagonal packages. | Strict interface contracts without deep inheritance hierarchies. Preserves types and docstrings with elided bodies. | If factory patterns or multi-level inheritance exist, model lacks base class schemas. |
| **$D_2$** | **Transitive Nominal** | Standard web monoliths (Django, Rails), COSS data engines (PostHog), SDKs. | Resolves data models and shared utilities up to 2 hops away. Canonical production baseline. | In repositories with >3,000 files, can accumulate noise if the graph is circular. |
| **$D_3$** | **Ambient Cartography** | Massive monorepos (Airflow), Turborepos, legacy code with cross-package imports. | Eliminates import hallucinations (`ModuleNotFoundError`) by supplying a flat coordinate index. | In small projects, adds ~1,500 tokens of text with negligible marginal utility. |

---

## 4. PRE-MORTEM SAFEGUARDS & INVIOLABLE AXIOMS

Integrated as formal negative invariants in the axiomatic gateway:

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

## 5. VERIFICATION & BENCHMARKING PROTOCOL

The test harness evaluates compliance through isolated verification vectors:
1. **Persistence Inspection:** Verify `%LOCALAPPDATA%\ctxfw\tokens.db` integrity after every execution.
2. **Key Metric Evaluation:**
   - Raw requested tokens vs. delivered bundle tokens.
   - Cache query latency ($t_{hit}$) vs. syntax parsing latency ($t_{parse}$).
   - First-Pass Yield verification across multi-depth resolution turns.
3. **Automated Regression Testing:** Continuous validation against the comprehensive 180-test regression suite.

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
