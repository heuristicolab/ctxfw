# Directiva de Fabricación Agéntica Zero-Drift ($4,500 USD Caliber)

## 1. Contexto de Misión y Arquitectura
Implementar la arquitectura de grado enterprise según el brief técnico: `# ORDEN TÉCNICA SOBERANA: ord-2026-4f003b

## DESCRIPCIÓN DEL REQUERIM`.

## 2. Stack Tecnológico Aprobado
- FastAPI, Pydantic v2, SQLite WAL, Pytest

## 3. Bounded Contexts y Componentes
- Perimeter, Contracts, Persistence, Governance, API

## 4. Reglas Inmutables de Fabricación (Veto Arquitectónico)
1. **Confinamiento Canónico**: Todo el código debe residir estrictamente bajo `src/heuristico/domains/`.
2. **Contratos Inmutables**: Modelos Pydantic v2 con `model_config = ConfigDict(frozen=True, extra='forbid')` y tuplas inmutables `tuple[...]`.
3. **Aduana Perimetral O(1)**: Validación determinista con latencia perimetral garantizada <= 2.0 ms.
4. **Persistencia Relacional WAL**: SQLite WAL / PostgreSQL con integridad referencial completa y cero drift en esquemas.
5. **Cobertura TDD 100%**: Suite Pytest validando invariantes, inmutabilidad y excepciones `ValidationError`.