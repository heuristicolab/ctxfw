# Release Notes: ctxfw v3.8.0

`ctxfw v3.8.0` introduces **zero-touch atomic onboarding** for **Claude Code CLI** and **Claude Desktop**, backed by a crash-resilient JSON mutation engine and formal ACI 1.0000 axiomatic verification.

---

## What's New in v3.8.0

### 1. Zero-Touch Claude Onboarding Engine (`ctxfw install --claude`)
* Automatically detects and patches `~/.claude.json` (Claude Code CLI) and `%APPDATA%\Claude\claude_desktop_config.json` (Claude Desktop).
* Pre-approves the 3 canonical tools (`prune_file`, `resolve_context_bundle`, `evaluate_spec_axioms`) in `allowedTools` to eliminate recurring user confirmation prompts.
* Resolves dynamic virtualenv and system Python interpreter paths automatically.

### 2. Atomic Configuration Mutation Engine
* **Pre-mutation Syntax Quarantine:** Validates existing JSON syntax before executing any disk operations.
* **Sibling Staging:** Writes changes to a temporary sibling file (`.tmp.<uuid>`) and enforces `os.fsync` prior to inode replacement.
* **Bounded Backup Snapshots ($N \le 5$):** Creates timestamped `.bak.<timestamp>` snapshots, pruning historical backups to prevent disk bloat.
* **Non-Destructive Deep Merging:** Preserves existing external MCP servers, user preferences, and authentication tokens (`oauthAccount`).

### 3. Verification & Compliance Matrix
* **Deterministic Test Suite:** Expanded to **153/153 tests passing (100% green)** with zero regressions.
* **Axiomatic Sieve (Appendix C):** Certified **ACI Score 1.0000** over 13 sealed negative invariants.
* **Zero Egress Contract:** Verified 100% air-gapped / memory-resident execution. Zero telemetry leaves the host machine.

---

## Upgrade & Verification

```bash
# Upgrade via PyPI
pip install --upgrade ctxfw

# Verify version
ctxfw --version  # Output: ctxfw 3.8.0

# Execute atomic zero-touch onboarding
ctxfw install --claude
```
