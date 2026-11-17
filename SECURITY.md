# Security Policy

## Supported Versions

| Version | Supported | Security Hardening Status |
| :--- | :---: | :--- |
| `4.2.x` (`4.2.1`) | Yes | Current release (`SARA`, `mcp_guard`, Gate `0d`, multi-hop `Provenance`, `%XX` & homoglyph hardening) |
| `4.1.x` | Security fixes via upgrade to `4.2.x` | Upgrade via `pip install --upgrade ctxfw` |
| `< 4.1.0` | No | End of support |

---

## Architectural Trust Boundary (`Plano 0`, Apache 2.0)

`ctxfw` is designed as a **Zero-Egress** local pre-ingestion security and AST pruning engine:

- **No Outbound Telemetry in Data Plane:** Source code, AST stubs, prompts, and local SQLite WAL ledgers (`tracekit.db`, `sara.db`, `swegate.db`, `tokencast.db`, `rules.db`) remain strictly on localhost/workstation storage.
- **Deterministic Fail-Closed Gates:**
  - `ctxfw.sara`: Inspects untrusted tool observations (`<= 64 KB`, zero NUL bytes, NFKC normalization, zero-width/BiDi `U+202A–U+202E` and ANSI stripping, localized/multilingual role-override detection, intra-token homoglyphs, `1..4`-pass `%XX` path decoding, and `STRIP_COMMANDS` / `QUARANTINE_TOOL` enforcement).
  - `ctxfw.mcp_guard`: SHA-256 tool schema pinning (`rug-pull` blocking), OS symlink/junction path confinement, `PoC-1/2/3` dynamic containment, and Gate `0d` `ToolCapabilityProfile` anti-laundering.
  - `ctxfw.sara.provenance`: Backward-BFS causal taint propagation blocking delayed multi-hop Indirect Prompt Injection across `apply_patch`.
  - `ctxfw.sara.task_auth`: Task-scoped authorization, scope intersection, `DPoP` HMAC anti-replay, and monotonic epoch verification. Note: `verify_jwt_before_parse` operates on pre-validated upstream JWT signature assertions (`jwt_sig_verified`) in Open-Core `Plano 0`; federated IdP `JWKS` signature validation belongs to external ingress gateways.

### Honest Cryptographic Scope (`Open-Core Plano 0`)
- `TraceKit` (`SQLite WAL`) prevents accidental or inline `UPDATE`/`DELETE` tampering locally via append-only triggers and SHA-256 hash chaining (`283` bytes per block) verifiable with `ctxfw trace verify`.
- Local SQLite files do not provide hardware HSM remote attestation against root/filesystem deletion on a compromised host without external log anchoring.

---

## Reporting a Vulnerability

If you discover a security vulnerability, prompt-injection bypass, path confinement escape, or packaging issue in `ctxfw`, **please do not open a public GitHub issue or pull request with exploit payloads before coordinated triage**.

1. **Email:** Send a concise report (affected component/version, minimal reproduction steps, expected vs. observed verdict) to **`mo@heuristicolab.com`** with subject prefix `[SECURITY][ctxfw]`.
2. **Response SLA:** You will receive an acknowledgment within **48 hours** and an initial severity/remediation assessment within **5 business days**.
3. **Coordinated Disclosure:** Once a patch is verified against offline adversarial vectors and released to PyPI/GitHub Releases, advisory credits will be published in `CHANGELOG.md` (if requested).

---

## Offline Security Verification

Anyone auditing `ctxfw` from source can verify security invariants with zero network calls:

```bash
ctxfw doctor
ctxfw spec verify SPEC.axioms.md
pytest tests/ -q
python benchmarks/run_sara_security_benchmark.py --json
python benchmarks/run_wave2_v42_benchmark.py --json
python benchmarks/run_regulatory_ocr_benchmark.py --json
```
