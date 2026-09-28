---
name: axiom-sieve
description: Formally audits SPEC.axioms.md, verifies negative invariants (NEVER), computes the ACI Score, and cryptographically seals commits with a SHA-256 hash.
tools:
  - read_file
  - run_command
triggers:
  - "verify axioms"
  - "gatekeeper"
  - "compute aci"
  - "audit spec"
---

# MISSION & CRYPTOGRAPHIC VERIFICATION
Guarantees that no system mutation violates deterministic architectural invariants prior to merging code or packaging releases.

## Operating Procedure:
1. Read and parse `C:\ctxfw\SPEC.axioms.md`.
2. Extract all clauses containing explicit negative constraints (`shall never`, `must never`, `never`).
3. Compute the Axiom Completeness Index (ACI):
   $$\text{ACI} = \frac{\text{Implemented Verifiable Invariants}}{\text{Total Declared Clauses}}$$
4. Failure Condition: If $\text{ACI} < 0.9000$, abort execution with status `[QUARANTINED]`.
5. Compute the SHA-256 cryptographic digest of the specification manifest.
6. Issue the formal verdict:
   - `[PASS] READY FOR FORGE` with SHA-256 digest and clause count.
   - `[FAIL] QUARANTINED` enumerating which axioms lack verification harnesses.
