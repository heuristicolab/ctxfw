# Sovereign Architecture Blueprint Vault — ord-2026-4f003b

> **Bóveda Institucional**: `arch-ord-2026-4f003b`  
> **Organización**: `heuristicolab` (Heurístico Lab)  
> **SLA**: 48H Guaranteed Architecture & TDD Matrix

---

## 📦 Estructura Canónica de Entregables
- `00_DIRECTIVES/5_fabrication_directive.md`: Directiva de manufactura e invariantes de arquitectura.
- `01_TOPOLOGY/1_mermaid_dag.md`: Grafo topológico Mermaid DAG y bounded contexts.
- `02_CONTRACTS/2_pydantic_contracts.py`: Modelos y contratos inmutables Pydantic v2.
- `02_CONTRACTS/3_schema_ddl.sql`: Esquema SQL DDL relacional y constraints de integridad.
- `03_TEST_MATRIX/4_pytest_tdd_matrix.py`: Matriz de pruebas unitarias y forenses Pytest.
- `contracts.py`: Módulo importable directo de contratos Pydantic v2.
- `test_contracts.py`: Matriz TDD ejecutable directa.
- `.gitea/workflows/ci.yaml`: Pipeline de integración continua y atestación hermética.
