---
name: axiom-sieve
description: Audita formalmente SPEC.axioms.md, verifica invariantes negativas (NEVER), calcula el ACI Score y sella el commit con hash SHA-256.
tools:
  - read_file
  - run_command
triggers:
  - "verify axioms"
  - "gatekeeper"
  - "calcular aci"
  - "auditar spec"
---

# MISSION & CRYPTOGRAPHIC VERIFICATION
Asegura que ningún cambio al sistema viole las leyes deterministas de la arquitectura antes de fusionar código o empaquetar versiones.

## Procedimiento Operativo:
1. Lee y parsea `C:\ctxfw\SPEC.axioms.md`.
2. Extrae todas las cláusulas que contengan restricciones negativas explícitas (`shall never`, `must never`, `never`).
3. Evalúa el Axiom Completeness Index (ACI):
   $$\text{ACI} = \frac{\text{Invariantes Verificables Implementadas}}{\text{Total de Cláusulas Declaradas}}$$
4. Condición de fallo: Si $\text{ACI} < 0.9000$, aborta con estado `[QUARANTINED]`.
5. Calcula el hash criptográfico SHA-256 del manifiesto de especificación.
6. Emite el veredicto formal:
   - `[PASS] READY FOR FORGE` con digest SHA-256 y conteo de cláusulas.
   - `[FAIL] QUARANTINED` detallando qué axiomas carecen de arnés de verificación.
