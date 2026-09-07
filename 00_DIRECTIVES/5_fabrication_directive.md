# DIRECTIVA DE FABRICACIÓN AGÉNTICA — ord-2026-4f003b Context & Token Optimization Engine

## 1. CONTEXTO DE MISIÓN
Implementar un motor determinista, hermético y de costo operativo cero para la optimización de contexto y poda de tokens en Heurístico Lab. El sistema realiza slicing sintáctico de código Python mediante el módulo nativo AST, eliminando cuerpos de funciones y métodos mientras preserva firmas, tipos, jerarquías de clases y contratos inmutables (Pydantic v2). La persistencia opera de forma local sobre SQLite en modo WAL, garantizando cache hits sub-milisegundo (<2ms) y 100% de ahorro de tokens en análisis repetidos.

## 2. INVARIANTES NO NEGOCIABLES
1. Cero Dependencias de Nube: Operación 100% local sobre la librería estándar de Python + Pydantic v2.
2. Preservación Contractual AST: Prohibido mutilar firmas, parámetros, decoradores o jerarquías de herencia. Únicamente vaciar cuerpos reemplazándolos por `pass`.
3. Invariante de Caché: La clave SHA-256 debe calcularse estrictamente sobre `(source_code + rules_version + strip_docs)`.
4. Persistencia SQLite WAL: Conexión con `PRAGMA journal_mode=WAL;` y `PRAGMA synchronous=NORMAL;`.
5. Eficiencia Garantizada: Reducción mínima de tokens de contexto >= 35% en la primera pasada y latencia de respuesta en caché < 5 ms.

## 3. COMANDOS DE VERIFICACIÓN
```bash
python -m py_compile contracts.py tests/test_contracts.py
python -m pytest tests/ -v --tb=short
sqlite3 :memory: < schema.sql
```