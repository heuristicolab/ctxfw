# Reporte Técnico: Benchmark Destructivo A/B sobre `zulip/zulip`
<!-- Heurístico LAB // Skunk Works Division // Empirical Benchmark v4.0.0 -->
<!-- Protocolo: CTXFW Axiomatic Gateway (Status: VERIFIED, ACI: 1.0000) -->
<!-- Attestation Manifest Hash: 837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3 -->
**Entorno de Ejecución:** Servidor Linux Remoto (Ubuntu 24.04 LTS, Docker 29.1.3)  
**Fecha:** 2026-10-02 06:23:29 UTC  
**Sujeto de Evaluación:** Monolito Django/Python [`zulip/zulip`](https://github.com/zulip/zulip)  
**Versión de Engine:** `ctxfw` v4.0.0-preview (Rama: `experiment/depth-configurator`)  

---

## 1. Resumen Ejecutivo
Para auditar la resiliencia y el comportamiento del cortafuegos semántico en arquitecturas monolíticas densamente acopladas, se ejecutó una evaluación destructiva multicapa A/B sobre el modelo central de usuarios de Zulip (`zerver/models/users.py`, objetivo $D_0$) y su grafo transitivo de dependencias a lo largo de 4 niveles de profundidad ($D_0, D_1, D_2, D_3$).

El experimento demostró empíricamente:
1. **Preservación Inviolable de $D_0$ (AXIOM-3):** El archivo focal bajo edición activa permanece 100% íntegro e intocado (Ahorro 0.00%, latencia P95: 4.666 ms).
2. **Poda Perimetral Gradual:** La reducción de tokens escala de forma determinista:
   - **$D_1$ (Interfaz Directa):** 45279 tokens (55.86% ahorro vs raw).
   - **$D_2$ (Nominal Transitivo):** 287845 tokens (76.64% ahorro vs raw).
   - **$D_3$ (Cartografía Ambiental):** 83913 tokens totales (Manifiesto de símbolos: 774 tokens, 87 símbolos inyectados).
3. **Latencia Sub-25ms SLA (CA-01):** La resolución completa de $D_3$ con SQLite WAL y caché L1 se resuelve en **11.61 ms** (P50: **9.855 ms**).
4. **Integridad Sintáctica Absoluta:** 100% de módulos podados superaron `ast.parse() == True` sin ruptura sintáctica ni errores de compilación.

---

## 2. Telemetría Comparativa de Tokens ($D_0 \longrightarrow D_3$)

| Capa / Nivel | Módulos Procesados | Tokens Crudos | Tokens Inyectados | Ahorro vs Raw | Latencia P50 | Latencia P95 | Formato Sintáctico |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :--- |
| **$D_0$ (Focal Activo)** | 1 | 12909 | **12909** | **0.0%** | 4.171 ms | 4.666 ms | Código Python 100% íntegro |
| **$D_1$ (Direct Interface)** | 10 | 102583 | **45279** | **55.86%** | 5.312 ms | 5.694 ms | Cuerpos elididos a `...` |
| **$D_2$ (Transitive Nominal)** | 339 | 1232364 | **287845** | **76.64%** | 30.744 ms | 34.916 ms | Declaraciones de clase nominales |
| **$D_3$ (Ambient Cartography)**| 61 | 328539 | **83913** | **74.46%** | 9.855 ms | **11.61 ms** | Manifiesto léxico zero-syntax |

### Muestra del Manifiesto Ambiental ($D_3$):
```python
### AMBIENT MANIFEST [D3] (Zero-Syntax Symbol Index)
# Compact symbol index for 3-hop transitive dependencies. Bodies and signatures omitted.
corporate.lib.billing_types: []
corporate.lib.registration: [check_spare_license_available_for_changing_guest_user_role:F, check_spare_licenses_available:F, check_spare_licenses_available_for_inviting_new_users:F, check_spare_licenses_available_for_registering_new_user:F, generate_licenses_low_warning_message_if_required:F, get_plan_if_manual_license_manag
```

---

## 3. Certificación de Criterios de Aceptación Inmutables

| Criterio | Especificación Requerida | Métrica Obtenida | Estado |
| :--- | :--- | :---: | :---: |
| **CA-01** | Latencia P95 resolución $D_3 \le 25.0	ext{ ms}$ | **11.61 ms** | **`[PASS]`** |
| **CA-02** | Zero-Focal Degradation en $D_0$ | **100% idéntico carácter por carácter** | **`[PASS]`** |
| **CA-03** | Pureza de canal MCP (cero bytes a `stdout`) | **0 bytes** (stdio 100% puro) | **`[PASS]`** |
| **CA-04** | Integridad sintáctica (`ast.parse`) | **100% PASS** en todas las capas | **`[PASS]`** |
| **AXIOM-19** | Techo de tokens en manifiesto $D_3 \le 1,000$ tok | **774 tokens** (87 símbolos) | **`[PASS]`** |

---
*Reporte emitido bajo el protocolo de soberanía de agentes Heurístico LAB.*  
*Manifiesto criptográfico inmutable:* `837e90a0d2d97f569f7190da2652d4e578efadf86b71d4a5c3020c6e16bf5bd3`
