# Release Notes: ctxfw v3.7.1
<!-- Heurístico LAB // Skunk Works Division // Defense Grade Release -->
<!-- Axiom Manifest Hash: 03a5c523fb3fb6559987c97836062b280b8fc2e3438aac07ab9fa0f1f0befa4c -->

## Summary
`ctxfw v3.7.1` introduces the **Triple Surface Architecture** (inspired by DeusData patterns), extending automated zero-touch MCP onboarding and interoperability across the developer ecosystem. It expands agent detection from 2 to 4 native client surfaces, implements zero-failure execution via absolute interpreter resolution, enforces timestamped backup snapshots before any file mutation, and provides a streamlined fallback gateway for non-MCP tooling (Aider, OpenCode, Continue).

---

## What's New in v3.7.1

### 1. Triple Surface MCP Auto-Detection & Injection
`ctxfw init` and `install_mcp_servers` automatically discover and configure 4 primary autonomous coding surfaces:
1. **Claude Desktop (Cross-Platform Native)**:
   - **macOS (Darwin)**: `~/Library/Application Support/Claude/claude_desktop_config.json`
   - **Windows**: `%APPDATA%/Claude/claude_desktop_config.json`
   - **Linux / POSIX**: `~/.config/Claude/claude_desktop_config.json`
2. **Claude Code CLI**:
   - Injects directly into `~/.claude.json`.
3. **Cursor IDE**:
   - Injects into `.cursor/mcp.json` (workspace scope with fallback to parent directory).
4. **Windsurf IDE**:
   - Injects into `~/.codeium/windsurf/mcp_config.json` when the Windsurf environment signature is identified.

### 2. Zero-Failure Execution via Explicit Interpreter Resolution
To prevent path resolution failures across isolated virtualenvs, pyenv shims, and containerized agents:
- MCP command resolution dynamically binds to `sys.executable` with `["-m", "ctxfw.mcp"]`.
- When running in frozen standalone binaries (e.g. PyInstaller via `sys.frozen`), uses canonical resolved binary path with `["mcp"]`.
- Eliminates ambient `$PATH` lookup failures when Claude Desktop or Cursor launches subprocesses outside an active virtualenv.

### 3. Timestamped Backup Snapshots & Non-Destructive Merging
- **Inviolable Backup Requirement**: Before modifying any pre-existing configuration on disk, the installer generates an immutable snapshot at `<config_file>.bak.<timestamp>`.
- **100% Third-Party Preservation**: Preserves all existing MCP servers, top-level settings, and environment variables.
- **Strict Idempotency**: Running the installer repeatedly (3x+ convergence) guarantees byte-for-byte immutability with zero spurious diffs or duplicates.
- **Atomic File Swaps**: Writes configuration to a PID- and nanosecond-scoped temporary file before calling `os.replace`.

### 4. Zero-MCP Interoperability Gateway
For development workflows and AI CLI tools that do not natively support the Model Context Protocol (e.g. **Aider**, **OpenCode Interpreter**, **Continue.dev**, or standard REST clients), the installer prints actionable proxy instructions:
```bash
# 1. Start the zero-egress local proxy server
ctxfw proxy --port 8765

# 2. Export the Anthropic API endpoint in your terminal or tool environment
export ANTHROPIC_BASE_URL="http://localhost:8765/v1"
```

---

## Quality Assurance & Empirical Verification
- **Axiomatic Determinism**: **ACI 1.0000** (`VERIFIED` / 6 Negative Invariants sealed under Manifest Hash `03a5c523fb3fb6559987c97836062b280b8fc2e3438aac07ab9fa0f1f0befa4c`).
- **Comprehensive Test Suite**: 100% passing tests including:
  - Multi-surface path resolution across Windows, macOS, and Linux.
  - Snapshot backup creation (`.bak.<timestamp>`) on existing config mutation.
  - 3x consecutive idempotency verification with zero file divergence.
  - Zero-MCP proxy guidance banner verification.
  - Subprocess stdio isolation and UTF-8 safe banner rendering.

---

## Upgrade Guide
```bash
# Install or upgrade to v3.7.1
pip install --upgrade ctxfw

# Run multi-surface automated configuration
ctxfw init

# Verify complete environment attestation
ctxfw doctor
```
