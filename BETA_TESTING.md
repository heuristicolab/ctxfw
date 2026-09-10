# Protocolo de Validación Externa y Rúbrica de Beta Testing: Context Firewall (`ctxfw`)

Este documento define el protocolo formal de evaluación para ingenieros de sistemas, líderes técnicos y auditores DevSecOps externos que participan en la fase beta de `ctxfw`.

---

## 1. Objetivos del Beta Testing
1. **Validación de Determinismo**: Comprobar que la compuerta axiomática de `ctxfw` actúa como un cortafuegos infranqueable frente a la ambigüedad y alucinación en prompts.
2. **Ergonomía Developer Experience (DX)**: Evaluar la experiencia de onboarding sin fricción en IDEs (`ctxfw init --global`) y en repositorios (`ctxfw init --repo`).
3. **Aislamiento y Rendimiento**: Confirmar que el servidor MCP y las herramientas de poda de contexto operan en tiempos sub-50ms y con cero contaminación de `stdout`.

---

## 2. Rúbrica de Evaluación Cuantitativa y Cualitativa

Los evaluadores calificarán cada una de las siguientes tres dimensiones en una escala de 1 a 5:

### Dimensión 1: Claridad del Diagnóstico en Cuarentena
*Objetivo: ¿Es evidente para el desarrollador humano y el agente de IA por qué una especificación fue bloqueada y qué debe hacerse para subsanarla?*

| Puntuación | Criterio |
| :---: | :--- |
| **5 (Excelente)** | Las `remediation_notes` identifican con precisión quirúrgica qué invariantes o cotas faltan, permitiendo corregir el pliego en el primer reintento sin ambigüedad. |
| **3 (Aceptable)** | El reporte indica que faltan invariantes o cotas, pero requiere releer la documentación para entender la sintaxis exacta. |
| **1 (Deficiente)** | El reporte arroja errores genéricos o no explica cómo satisfacer el índice ACI. |

### Dimensión 2: Tiempos de Respuesta y Rendimiento de la Tool MCP
*Objetivo: ¿Las herramientas MCP operan con fluidez imperceptible en el ciclo de interacción del agente?*

| Puntuación | Criterio |
| :---: | :--- |
| **5 (Excelente)** | Respuesta de `evaluate_spec_axioms` y `prune_file` en `< 25ms`. Cero jitter. Sin bloqueos en el hilo stdio. |
| **3 (Aceptable)** | Respuesta entre `50ms` y `150ms`. |
| **1 (Deficiente)** | Latencias superiores a `500ms` o bloqueos detectados por el IDE. |

### Dimensión 3: Fricción de Adopción en Proyectos Existentes (Zero-Touch)
*Objetivo: ¿Con qué facilidad se integra `ctxfw` en un repositorio corporativo preexistente?*

| Puntuación | Criterio |
| :---: | :--- |
| **5 (Excelente)** | `ctxfw init --global` detectó y configuró los IDEs automáticamente sin tocar configuraciones previas; el pre-commit hook funcionó a la primera tanto en Git Bash/Windows como en macOS/Linux. |
| **3 (Aceptable)** | Requirió reiniciar el IDE o ajustar una variable de entorno en un entorno exótico. |
| **1 (Deficiente)** | Sobreescribió un archivo de configuración preexistente o el hook de git falló al ejecutarse. |

---

## 3. Protocolo de Pruebas de Estrés para Evaluadores

Se alienta a los evaluadores a ejecutar los siguientes escenarios adversos:

1. **Prueba de Invariantes Negativas Camufladas**: Redactar oraciones que no usen `never` o `shall never` (por ejemplo, "evitar accesos") y confirmar que el Sieve Engine no es burlado y mantiene la cuarentena.
2. **Prueba de Preservación de Servidores MCP**: Verificar que al ejecutar `ctxfw init --global`, ningún servidor existente en `mcp_config.json` o `claude_desktop_config.json` pierda claves o argumentos.
3. **Prueba de Concurrencia SQLite WAL**: Ejecutar múltiples instancias de `ctxfw spec verify` o consultas simultáneas para comprobar que no ocurren bloqueos de base de datos (`database is locked`).
4. **Prueba de Autodiagnóstico en Frío**: Ejecutar `ctxfw doctor` en una máquina limpia y validar que detecte si falta el binario en el `PATH` o si falta una gramática de Tree-sitter.

---

## 4. Plantilla Estandarizada para Envío de Retroalimentación

Al concluir las pruebas, enviar el reporte con la siguiente estructura:

```markdown
### Reporte de Evaluación Beta Tester
- **Evaluador**: [Nombre / Organización]
- **Entorno**: [SO: Windows 11 / macOS Sonoma / Ubuntu 22.04] [IDE: Antigravity / Cursor / Claude]
- **Versión de ctxfw**: 3.5.0
- **Hash de Manifiesto Verificado**: [SHA-256]

#### Calificaciones
1. Claridad de Diagnóstico en Cuarentena: [1-5]
2. Latencia de Herramientas MCP: [1-5]
3. Fricción de Adopción Zero-Touch: [1-5]

#### Hallazgos y Comentarios
- [Aspectos destacados de la compuerta axiomática]
- [Fricciones o advertencias encontradas durante `ctxfw doctor` o `ctxfw init`]
- [Sugerencias de nuevas gramáticas o invariantes de dominio]
```
