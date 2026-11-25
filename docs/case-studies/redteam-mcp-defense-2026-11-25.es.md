<!-- manifest_hash: f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546 -->
# Caso de Estudio en Producción: Defensa Autónoma contra Red-Team MCP y Rate Limiting Determinista (2026-11-25)

**Audiencia:** Equipos de Seguridad en IA, Arquitectura MCP, FinOps LLM y CISO (`ctxfw.heuristicolab.com`)  
**Superficie Protegida:** Gateway público HTTP-a-MCP (`POST /api/mcp/invoke` en `danteix.com`) gobernado por **CTXFW Core (`Plane 0`, endurecido en `v4.2.2`)** + **CTXFW Enterprise (`Plane 1`, endurecido en `v1.0.2`)**  
**Spec Core Burst Guard (`ctxfw_mcp_burst_guard_v1`):** `f1329ba99a93db6abeaa6f185ce40327ce2260c53f29ef770477ff1bf22a2546` (`VERIFIED`, `ACI: 1.0000`)  
**Spec Enterprise Pool LRU (`ctxfw_enterprise_vault_lru_v1_0_2`):** `5031fb46f69b9c3c8d29548d34786f7356d1a3e0c7cafc2c78954a50a3c338f3` (`VERIFIED`, `ACI: 1.0000`)

---

## 1. Resumen Ejecutivo

El **25 de noviembre de 2026**, entre las **03:16:53 y las 04:06:46 CST** (`09:16–10:06 UTC`), el endpoint público MCP de Dante IX sufrió una ráfaga automatizada de 50 minutos ejecutada por un fuzzer de seguridad (**`571` peticiones HTTP `POST /api/mcp/invoke`** en Nginx / **`568` invocaciones auditadas en WAL**) contra el tier no autenticado `FREE_TRIAL` desde el bloque `CMNET` (`117.144.0.0/12`, IP enmascarada `117.147.90.x`, pico de `27 req/min` a las `03:40`).

La inspección forense de Nginx, `dante_sara.db`, `dante_tokencast.db` y el WAL aislado del sandbox demostró tres resultados clave:

1. **Cero Brechas de Seguridad y `$0.0000 USD` en Gasto LLM:** El fuzzer probó sistemáticamente **SSTI** (`{{4292*3932}}`, `${''.class.superclass}`), **evaluación multi-lenguaje** (Python/JS/Ruby/Shell), **RCE ciego por tiempo** (`sleep(5)`), **inyección de flags SSH `-oProxyCommand=` OOB**, *path traversal*, *split-brand trojan* e *indirect prompt injection*. Todos los ataques fallaron (**`0` ejecuciones**, **`0` secretos filtrados**, **`0` fugas cross-tenant**, **`$0.0000 USD`** upstream).
2. **`38` Intervenciones Reales de `CTXFW SARA` en Vivo:** `dante_sara.db` confirma **`38` intervenciones activas de `CTXFW SARA`** sobre `dante_mcp_query` (`18` cuarentenas duras `QUARANTINE_TOOL` con `risk_score 0.8000–0.9000` + `20` neutralizaciones `STRIP_COMMANDS` con `risk_score 0.4500`), complementadas por `2` rechazos `MCP-08`, `196` bloqueos Anti-Trojan, `53` bloqueos de Path Traversal y `1` rechazo limpio XML de SSTI.
3. **Postmortem Honesto de Disponibilidad y Remediación Dual (`v4.2.2` + `v1.0.2`):** **`182` llamadas `FREE_TRIAL` válidas** con nombres distintos aprovisionaron `118` espacios aislados (~11 archivos SQLite WAL cada uno), empujando al proceso a **`1,020 / 1,024` FDs (`EMFILE`)**. Esa evidencia dio origen a dos cierres nativos: **`ctxfw v4.2.2`** (Burst Rate Limiter determinista en Open-Core) y **`ctxfw-enterprise v1.0.2`** (pool LRU acotado `max_active_runtimes=16`, rollback atómico en `provision_vault` y `SandboxVaultPolicy`).

---

## 2. Telemetría Forense Verificada del Incidente

| Métrica Forense | Valor Observado en Producción (2026-11-25) | Fuente Verificada |
| :--- | :--- | :--- |
| **Ventana Temporal** | `03:16:53` – `04:06:46 CST` (`50` min, pico `27 req/min`) | Logs Nginx + Ledgers WAL |
| **Origen / Huella de Herramienta** | `CMNET` (`117.144.0.0/12`, `117.147.90.x`) · Fuzzer `McpfTest` / `--clx*` | Cabeceras Edge + `dante_wal.db` |
| **Volumen Total** | **`571`** HTTP `POST /api/mcp/invoke` (`568` auditadas en WAL) | `access.log` + Telemetry WAL |
| **Tier Atacado** | `FREE_TRIAL` no autenticado | Ledger Zero-Knowledge |
| **Gasto LLM Upstream** | **`$0.0000 USD`** (`compute_cost_usd = 0.0` verificado) | TokenCast + Edge Ledger |
| **Secretos Filtrados** | **`0`** (RSA, Ed25519, KEKs intactas) | Auditoría Criptográfica y DLP |
| **Presión Máxima de FDs** | **`1,020 / 1,024`** open FDs (límite *soft* Linux) | Límites kernel del proceso |

---

## 3. Payloads Capturados y Desglose de Defensas Activas

### A. Sondas Exactas del Fuzzer (`FREE_TRIAL` Sandbox — `0` Ejecuciones)

| Vector Probado | Payloads Literales Registrados en Sandbox | Resultado |
| :--- | :--- | :--- |
| **SSTI (Jinja2 / Java EL / Ruby / Format)** | `{{4292*3932}}`, `${4292*3932}`, `#{4292*3932}`, `{{"".__class__.__mro__}}`, `{0.__class__.__mro__}`, `${''.class.superclass}` | **0 ejecuciones.** Texto inerte; `${''.class.superclass}` abortó de forma segura en el parser XML (`unknown_charref`). |
| **Evaluación Multi-Lenguaje / Shell** | `ord("M")*4292`, `"M".charCodeAt(0)*4292`, `"M".ord*4292`, `len("McpfTest")*4292`, `print(4292*3932)`, `echo 4292*3932;` | **0 ejecuciones.** Nunca tocaron `eval()` ni subprocesos. |
| **RCE Ciego por Tiempo (`sleep 5`)** | `__import__("time").sleep(5)`, `const _t=Date.now()+5000;while(Date.now()<_t){};0`, `sleep(5)`, `sleep(5);` | **0 ejecuciones.** Ejecución determinista en *preview* sin amplificación de latencia. |
| **Inyección de Flags CLI / SSH `ProxyCommand`** | `--clxcfb0870b99`, `--clx470c2227e1=1`, `--version`, `-oProxyCommand=wget -qO- ...`, `-oProxyCommand=curl ...` | **0 ejecuciones / 0 egreso.** Ninguna llamada a subprocesos con el objetivo. |

### B. Intervenciones de Seguridad y `CTXFW SARA` (`290` Acciones de Seguridad)

| Capa de Defensa | Conteo | Código / Veredicto Emitido | Vector Neutralizado |
| :--- | :---: | :--- | :--- |
| **CTXFW SARA Cuarentena (`Plane 0`)** | **`18`** | `QUARANTINE_TOOL` (`QUARANTINED_BY_SARA`, `risk_score 0.8000–0.9000`) | *Indirect prompt injection* de alto riesgo en `dante_mcp_query`. |
| **CTXFW SARA Neutralización (`Plane 0`)** | **`20`** | `STRIP_COMMANDS` (`risk_score 0.4500`, hash SHA-256 Zero-Knowledge) | Directivas imperativas de riesgo medio limpiadas pre-ejecución. |
| **Anti-Trojan Coherence Lock** | **`196`** | `ERR_SECURITY_SPLIT_BRAND_TROJAN` (`98` forge shield + `98` remediation) | Spoofing de marcas con dominios ajenos para envenenar artefactos. |
| **Tenant Traversal Shield** | **`53`** | `ERR_SECURITY_TENANT_PATH_TRAVERSAL` (`38` forge shield + `15` remediation) | Secuencias `..`, bytes `NUL` y *spoofing* de `tenant_id_hash`. |
| **Contrato MCP-08 Gate** | **`2`** | `QUARANTINED_BY_GATE` | Violaciones deterministas de esquema (`INVALID_PARAMS`). |
| **Parser Seguro XML/PDF** | **`1`** | Rechazo limpio sin ejecución (`unknown_charref`) | Sonda SSTI bloqueada sin acceso al entorno. |

> **Aislamiento FinOps:** Incluso las **`182`** llamadas `FREE_TRIAL` sintácticamente válidas (`121` consultas de fricción, `45` auditorías, `16` *share probes*) operaron en modo *preview determinista* con **`$0.0000` USD** de consumo en OpenRouter.

---

## 4. Postmortem de Disponibilidad: Agotamiento Asimétrico de Descriptores (`EMFILE`)

A las **`03:20:32 CST`**, abrir **`118` espacios aislados distintos** (~11 archivos SQLite WAL por espacio) llevó al proceso a **`1,020 / 1,024` FDs**, causando **`15` respuestas HTTP `500`** y errores transitorios:

- `57` errores `sqlite3.OperationalError: unable to open database file`.
- `18` `[Errno 24] Too many open files` (`EMFILE`).
- `31` rechazos secundarios `VaultRegistry: Duplicate vault_slug` ante fallos de hidratación sin rollback atómico.

---

## 5. Remediación Dual Nativa: `ctxfw v4.2.2` + `ctxfw-enterprise v1.0.2`

1. **CTXFW Core `v4.2.2` — Burst Guard Nativo (`ctxfw_mcp_burst_guard_v1`):**
   - Incorpora `McpRateLimitPolicyDTO` y `McpBurstRateLimiter` en `ctxfw.mcp_guard.rate_limiter` + `MCPServer` (`enabled=False` opt-in por defecto para `100%` retrocompatibilidad).
   - Aritmética exacta en enteros escalados (`SCALE = 60_000`, `Decimal("0.0001")` — cero floats IEEE-754), reloj inyectable con *clamp* fail-closed ante regresiones, mapa LRU acotado (`[16, 4096]`), aislamiento **Zero-Knowledge** SHA-256 (`client_key_hash`), rechazos Clase 3 **`ERR_RATE_LIMIT_EXCEEDED`** y tabla SQLite WAL inmutable `rate_limit_audit_logs` con triggers `MCG_INV_10`.
   - Sellado con `ACI 1.0000` (`manifest_hash: f1329ba9...2546`), **`673/673` tests en verde** y `ALLOW_MERGE` en SWE-Gate (`cyclomatic_delta <= 9`).
2. **CTXFW Enterprise `v1.0.2` — Pool LRU Nativo y Rollback Atómico (`ctxfw_enterprise_vault_lru_v1_0_2`):**
   - Pool LRU en `EnterpriseVaultOrchestrator` (`max_active_runtimes=16`, `[2, 32]`, env `CTXFW_ENTERPRISE_MAX_ACTIVE_VAULTS`), rehidratación transparente de vaults desalojados sin `Duplicate vault_slug`, rollback atómico en `provision_vault` / `unregister_vault`, cierre completo en `VaultRuntimeState.close()` + `EnterpriseKernelAuditBridge`, y política oficial `SandboxVaultPolicy` / `resolve_sandbox_or_tenant_slug`.
   - Sellado con `ACI 1.0000` (`manifest_hash: 5031fb46...38f3`) y `95` tests en verde.
3. **Controles de Gateway y SO:**
   - Sandbox único `FREE_SANDBOX_TENANT_ID` (`1` solo espacio para `N` inputs gratuitos), rate limit en Nginx sobre IP real (`12 req/min`, `burst=15`, `HTTP 429`) y `LimitNOFILE=65536`.

---

## 6. Conclusiones

- **Defensa en Profundidad Dentro de JSON MCP:** Las `38` intervenciones `SARA`, `196` Anti-Trojan y `53` Path Traversal vivían dentro de argumentos JSON válidos que un WAF HTTP genérico deja pasar.
- **Trazabilidad Zero-Knowledge:** Toda la secuencia quedó reconstruida bit a bit mediante hashes SHA-256 sin exponer IPs ni secretos en los ledgers.
- **Ciclo Cerrado Verificado (`Spec -> TDD -> SWE-Gate`):** Tanto `ctxfw v4.2.2` como `ctxfw-enterprise v1.0.2` convirtieron un incidente real en protección formalmente verificada el mismo día.
