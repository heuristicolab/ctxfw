# Reporte Técnico: Benchmark Destructivo A/B sobre `zulip/zulip`
**Entorno de Ejecución:** VPS Linux Engine (Ubuntu 24.04 LTS / Docker 29.1.3 efímero)  
**Fecha:** 2026-09-28  
**Sujeto de Evaluación:** Monolito Django/Python [`zulip/zulip`](https://github.com/zulip/zulip)  
**Versión de Engine:** `heuristicolab/ctxfw` v3.7.0  

---

## 1. Resumen Ejecutivo
Para auditar la resiliencia y el comportamiento del cortafuegos semántico en arquitecturas monolíticas densamente acopladas, se ejecutó una evaluación destructiva A/B sobre el modelo central de usuarios de Zulip (`zerver/models/users.py`, objetivo $D_0$) y su perímetro inmediato de dependencias de primer grado ($D_1$: `realms.py`, `clients.py`, `prereg_users.py`).

El experimento demostró empíricamente que:
1. **Preservación Inviolable de $D_0$:** El archivo bajo edición activa permanece 100% íntegro e intocado (Invariante AXIOM-3).
2. **Poda Perimetral de Alto Rendimiento:** La compresión AST sobre las dependencias $D_1$ alcanza un **42.96%** en modo `INTERFACE` (preservando firmas, tipos y docstrings con cuerpos elididos a `...`) y hasta un **78.20%** en modo `NOMINAL`.
3. **Pureza del Canal MCP:** Cero bytes espurios emitidos a `stdout` (`leak_bytes == 0`), garantizando la integridad de streams JSON-RPC en Cursor y Claude Desktop.
4. **Integridad Sintáctica Absoluta:** 100% de clases (30/30) y métodos (50/50) conservados sin ruptura sintáctica (`ast.parse() == True`).

---

## 2. Telemetría Comparativa de Tokens

La volumetría de tokens fue calculada bajo el estándar canónico `len(text) // 4`:

| Componente | Archivos / Módulos | Tokens Crudos | Tokens Podados (`INTERFACE`) | Reducción Perimetral |
| :--- | :--- | :---: | :---: | :---: |
| **Focal ($D_0$)** | `zerver/models/users.py` | 12,909 | 12,909 | **0.00%** *(Invariante AXIOM-3)* |
| **Perímetro ($D_1$)** | `realms.py`, `clients.py`, `prereg_users.py` | 16,779 | 9,571 | **-42.96%** |
| **Total Agregado** | **$D_0 \cup D_1$** | **29,689** | **22,481** | **-24.28%** *(Ahorro neto: 7,208 tokens)* |

### Comparativa por Modos de Poda en Perímetro $D_1$:
- **Modo `INTERFACE` (Default):** Reducción en $D_1$ del **42.96%** (9,571 tokens finales). Retiene firmas completas, anotaciones de tipos y docstrings.
- **Modo `NOMINAL`:** Reducción en $D_1$ del **78.20%** (3,658 tokens finales). Retiene únicamente interfaces públicas y firmas esenciales.

---

## 3. Certificación de Criterios de Aceptación (Axiomatic DoD)

| Criterio | Especificación Calibrada | Métrica Obtenida | Estado |
| :--- | :--- | :---: | :---: |
| **DoD-1** | Reducción perimetral $D_1 \ge 40.0\%$ (`INTERFACE`) \| $\ge 70.0\%$ (`NOMINAL`) | **42.96%** (`INTERFACE`) / **78.20%** (`NOMINAL`) | **`[PASS]`** |
| **DoD-2** | Preservación de interfaces sintácticas en $D_1$ (`ast.parse`) | `100% PASS` en todos los módulos podados | **`[PASS]`** |
| **DoD-3** | Fuga cero en `stdout` durante ejecución MCP | **0 bytes** (canal JSON-RPC limpio) | **`[PASS]`** |
| **DoD-4** | Integridad de firmas y ausencia de alucinación sintáctica | **30/30 clases** y **50/50 métodos** intactos | **`[PASS]`** |

---

## 4. Instrucciones de Reproducción Local vía Docker

Para reproducir este benchmark en un contenedor Docker aislado y reproducible:

### 1. Clonar el repositorio y preparar el script
```bash
git clone https://github.com/heuristicolab/ctxfw.git /tmp/ctxfw-bench
cd /tmp/ctxfw-bench
```

### 2. Construir la imagen Docker
```dockerfile
# Dockerfile.bench
FROM python:3.11-slim
RUN apt-get update && apt-get install -y --no-install-recommends git && rm -rf /var/lib/apt/lists/*
WORKDIR /workspace
RUN git clone --depth 1 https://github.com/zulip/zulip.git /workspace/zulip
COPY . /workspace/ctxfw
RUN pip install --no-cache-dir /workspace/ctxfw
CMD ["python", "-m", "ctxfw.benchmarks.zulip", "/workspace/zulip"]
```

```bash
docker build -f Dockerfile.bench -t ctxfw-destructive-bench .
```

### 3. Ejecutar y limpiar
```bash
docker run --rm ctxfw-destructive-bench
docker rmi ctxfw-destructive-bench
```
