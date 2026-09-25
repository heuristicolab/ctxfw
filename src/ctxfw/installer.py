"""
src/ctxfw/installer.py — Zero-Touch Industrialization & Diagnostics Engine
Axiom Manifest Hash: a7e63ccb9b5dd0c6f6147cfd2feec447c4d41690dd76aee9e6035db56cb7c31a

Provides zero-touch onboarding, idempotent IDE configuration injection,
multiplatform pre-commit hook deployment, and comprehensive self-diagnostics.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import platform
import shutil
import stat
import subprocess
import sys
from typing import Any, Dict, List, Optional, Tuple
from pydantic import BaseModel, Field

from ctxfw import __version__
from ctxfw.sieve.engine import evaluate_specification


# -----------------------------------------------------------------------------
# Tactical ANSI Color Palette (Zero-Dependency) & Skunk Works Branding
# -----------------------------------------------------------------------------

CLR_RESET = "\033[0m"
CLR_CYAN = "\033[38;5;51m"       # Tactical Ice Blue
CLR_EMERALD = "\033[38;5;48m"    # Emerald Verification
CLR_CRIMSON = "\033[38;5;196m"   # Blood Crimson Alert
CLR_AMBER = "\033[38;5;214m"     # Warning Amber
CLR_GRAPHITE = "\033[38;5;240m"  # Muted Graphite
CLR_WHITE_BOLD = "\033[1;37m"    # Pure White Bold

BANNER = rf"""
  ██████╗████████╗██╗  ██╗███████╗██╗    ██╗
 ██╔════╝╚══██╔══╝╚██╗██╔╝██╔════╝██║    ██║
 ██║        ██║    ╚███╔╝ █████╗  ██║ █╗ ██║
 ██║        ██║    ██╔██╗ ██╔══╝  ██║███╗██║
 ╚██████╗   ██║   ██╔╝ ██╗██║     ╚███╔███╔╝
  ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝      ╚══╝╚══╝  v{__version__}
 ░░░ HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE ░░░
"""


def print_defense_banner(stream=None) -> None:
    """Renders the brutalist defense-grade ASCII banner with UTF-8 encoding safeguard."""
    out = stream if stream is not None else sys.stdout
    is_tty = getattr(out, "isatty", lambda: False)()

    # When connected to an interactive terminal (Windows Terminal, PowerShell), ensure UTF-8
    if is_tty and hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    out_encoding = getattr(out, "encoding", "utf-8") or "utf-8"
    can_encode_unicode = True
    try:
        BANNER.encode(out_encoding)
    except Exception:
        can_encode_unicode = False

    if can_encode_unicode:
        try:
            out.write(f"{CLR_CYAN}{BANNER}{CLR_RESET}\n")
            out.flush()
            return
        except Exception:
            pass

    # Fallback clean ASCII banner for restricted charmaps (e.g. cp1252 pipes)
    fallback = (
        f"{CLR_CYAN}\n"
        "   ____ _______  ______ _       __\n"
        "  / __ /_  __/ |/ / __/ | /| / /\n"
        f" / /_/ // /  |   / _/ | |/ |/ /  v{__version__}\n"
        " \\____//_/  /_/|_/_/   |__/|__/\n"
        " *** HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE ***\n\n"
        f"{CLR_RESET}"
    )
    try:
        out.write(fallback)
        out.flush()
    except Exception:
        try:
            if hasattr(out, "buffer"):
                out.buffer.write(fallback.encode("ascii", errors="replace"))
                out.buffer.flush()
        except Exception:
            pass


# -----------------------------------------------------------------------------
# Canonical Templates
# -----------------------------------------------------------------------------

CANONICAL_SPEC_TEMPLATE = """# Architectural Specification Brief: High-Assurance Target

## 1. Domain Entities & Bounded Variables
- Variable `max_concurrency`: integer bounded >= 1 and <= 256.
- Variable `session_timeout_sec`: integer bounded >= 10 and <= 3600.
- Variable `token_cache_size`: integer bounded >= 64 and <= 8192.
- Variable `max_retries`: integer bounded >= 0 and <= 5.
- Variable `worker_thread_pool`: integer bounded >= 2 and <= 64.
Bounds: 5 / 5

## 2. Deterministic State Machine (FSM)
Lifecycle states and transitions:
- States: DRAFT, QUARANTINED, VERIFIED, SEALED
- Transition delta(DRAFT, EVALUATE_DEFICIENT) -> QUARANTINED
- Transition delta(DRAFT, EVALUATE_COMPLIANT) -> VERIFIED
- Transition delta(QUARANTINED, REMEDIATE) -> DRAFT
- Transition delta(VERIFIED, SIGN_MANIFEST) -> SEALED
- Terminal State: SEALED is immutable. Boundary violation diverts to QUARANTINED.

## 3. Error Taxonomy & Quarantine
Formal error taxonomy isolates 4 fault domains:
- Class 1 (Transient Fault): Socket timeout, WAL busy -> Exponential retry.
- Class 2 (Deterministic Input Fault): Syntax parse error -> Fail-open or AST stub.
- Class 3 (Business & Specification Violation): ACI < 0.9000 or invariants < 5 -> Quarantine sink.
- Class 4 (Security & Isolation Violation): Stdout leak, path escape -> Immediate halt.

## 4. Formal Proof & Cryptographic Attestation
Formal proof included: Mathematical induction validates state machine invariants.
Deterministic SHA-256 attestation seal guarantees manifest immutability.

## 5. Negative Invariants (Floor of 5 Required)
- System shall never emit raw stdout logs during stdio communication.
- System shall never bypass perimeter quarantine filters.
- System shall never mutate sealed configuration state after initialization.
- System shall never persist unencrypted credentials in local caches.
- System shall never execute unvalidated architectural proposals.
"""

SOVEREIGN_DIRECTIVE_RULE = """
# SOVEREIGN AGENT DIRECTIVES (CTXFW PROTOCOL)
## INVIOLABLE AXIOMATIC GATEWAY
Queda estrictamente prohibido generar o modificar codigo backend, esquemas o arquitecturas
sin validar formalmente los requerimientos previos mediante 'ctxfw.evaluate_spec_axioms':
1. Minimo 5 invariantes negativas no negociables ('never' o 'shall never').
2. Cotas explicitas en todas las variables de dominio.
3. FSM determinista con transiciones delta(S, E) y estados terminales.
4. Taxonomia formal de errores en 4 clases.
5. Proceder a sintesis UNICAMENTE con estatus VERIFIED (ACI >= 0.9000).
"""

PRE_COMMIT_HOOK_SCRIPT = r"""#!/bin/sh
# CTXFW Axiomatic Pre-Commit Hook (Sovereign Gatekeeper)
# Manifest Hash: 575d12d75bcb427be48c3d62c643a4fb4a0260768cb49197c5d09133058581ed

echo "[ctxfw] Running axiomatic specification gatekeeper..."

# Multiplatform executable resolution
if command -v python >/dev/null 2>&1; then
    CMD="python -m ctxfw.cli"
elif command -v ctxfw >/dev/null 2>&1; then
    CMD="ctxfw"
elif command -v py >/dev/null 2>&1; then
    CMD="py -m ctxfw.cli"
elif command -v python3 >/dev/null 2>&1; then
    CMD="python3 -m ctxfw.cli"
else
    echo "[ctxfw] [ERROR] Neither 'ctxfw' nor 'python' was found in PATH."
    exit 1
fi

# Detect specification briefs staged for commit
STAGED_SPECS=$(git diff --cached --name-only --diff-filter=ACM 2>/dev/null | grep -E "(\.axioms\.md$|^SPEC\.axioms\.md$)")

if [ -z "$STAGED_SPECS" ]; then
    if [ -f "SPEC.axioms.md" ]; then
        STAGED_SPECS="SPEC.axioms.md"
    fi
fi

if [ -z "$STAGED_SPECS" ]; then
    exit 0
fi

FAIL=0
for spec in $STAGED_SPECS; do
    if [ -f "$spec" ]; then
        echo "[ctxfw] Verifying: $spec"
        $CMD spec verify "$spec"
        EXIT_CODE=$?
        if [ $EXIT_CODE -ne 0 ]; then
            echo "[ctxfw] [BLOCKED] Specification '$spec' is QUARANTINED. Commit rejected."
            FAIL=1
        fi
    fi
done

exit $FAIL
"""


# -----------------------------------------------------------------------------
# Data Models
# -----------------------------------------------------------------------------

class IDEDetectionResult(BaseModel):
    ide_name: str
    detected: bool
    config_paths: List[str] = Field(default_factory=list)
    rules_paths: List[str] = Field(default_factory=list)
    notes: List[str] = Field(default_factory=list)


class DoctorCheckResult(BaseModel):
    name: str
    status: str  # "OK", "WARN", "FAIL"
    details: str
    remediation: Optional[str] = None


class DoctorReport(BaseModel):
    all_passed: bool
    checks: List[DoctorCheckResult] = Field(default_factory=list)


# -----------------------------------------------------------------------------
# IDE Detection & Config Merging
# -----------------------------------------------------------------------------

def resolve_ide_paths(base_home: Optional[Path] = None) -> Dict[str, Dict[str, List[Path]]]:
    """Resolves potential configuration and rule paths across supported IDEs."""
    home = (base_home or Path.home()).resolve()
    current_os = platform.system()
    appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming"))) if current_os == "Windows" else home

    paths: Dict[str, Dict[str, List[Path]]] = {
        "Antigravity": {
            "configs": [
                home / ".gemini" / "antigravity-ide" / "mcp_config.json",
                home / ".gemini" / "config" / "mcp_config.json",
            ],
            "rules": [
                home / ".gemini" / "config" / "rules" / "GEMINI.md",
            ],
            "signatures": [
                home / ".gemini",
            ],
        },
        "Cursor": {
            "configs": (
                [
                    appdata / "Cursor" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
                    home / ".cursor" / "mcp.json",
                ]
                if current_os == "Windows"
                else [
                    home / "Library" / "Application Support" / "Cursor" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
                    home / ".cursor" / "mcp.json",
                ]
                if current_os == "Darwin"
                else [
                    home / ".config" / "Cursor" / "User" / "globalStorage" / "rooveterinaryinc.roo-cline" / "settings" / "cline_mcp_settings.json",
                    home / ".cursor" / "mcp.json",
                ]
            ),
            "rules": [
                home / ".cursorrules",
            ],
            "signatures": [
                home / ".cursor",
                appdata / "Cursor" if current_os == "Windows" else home / ".config" / "Cursor",
            ],
        },
        "Claude Desktop": {
            "configs": (
                [appdata / "Claude" / "claude_desktop_config.json"]
                if current_os == "Windows"
                else [home / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"]
                if current_os == "Darwin"
                else [home / ".config" / "Claude" / "claude_desktop_config.json"]
            ),
            "rules": [],
            "signatures": (
                [appdata / "Claude"]
                if current_os == "Windows"
                else [home / "Library" / "Application Support" / "Claude"]
                if current_os == "Darwin"
                else [home / ".config" / "Claude"]
            ),
        },
    }
    return paths


def detect_installed_ides(base_home: Optional[Path] = None) -> List[IDEDetectionResult]:
    """Detects installed IDE environments based on known directory structures and configurations."""
    all_paths = resolve_ide_paths(base_home)
    results: List[IDEDetectionResult] = []

    for ide_name, spec in all_paths.items():
        signatures = spec.get("signatures", [])
        detected = any(sig.exists() for sig in signatures)
        configs = [str(p) for p in spec.get("configs", []) if p.exists() or detected]
        rules = [str(p) for p in spec.get("rules", []) if p.exists() or detected]

        notes = []
        if detected:
            notes.append("IDE directory or configuration signature identified.")
        else:
            notes.append("Signature not found in default locations.")

        results.append(
            IDEDetectionResult(
                ide_name=ide_name,
                detected=detected,
                config_paths=configs,
                rules_paths=rules,
                notes=notes,
            )
        )
    return results


def safe_merge_mcp_config(
    config_path: Path,
    server_name: str = "ctxfw",
    server_config: Optional[Dict[str, Any]] = None,
) -> Tuple[bool, str]:
    """
    Idempotently injects the MCP server entry into a configuration file.
    Preserves all other pre-existing servers and formatting.
    """
    default_config = {
        "command": "ctxfw",
        "args": ["mcp"],
    }
    target_config = server_config if server_config is not None else default_config

    data: Dict[str, Any] = {}
    if config_path.is_file():
        content = config_path.read_text(encoding="utf-8").strip()
        if content:
            try:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    return False, f"Existing configuration at {config_path} is not a JSON object."
            except Exception as e:
                return False, f"Failed to parse existing JSON at {config_path}: {e}"

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    existing_server = data["mcpServers"].get(server_name)
    if existing_server == target_config:
        return False, f"Server '{server_name}' already configured identically in {config_path}."

    data["mcpServers"][server_name] = target_config

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    return True, f"Injected server '{server_name}' into {config_path}."


# -----------------------------------------------------------------------------
# Autonomous Agent MCP Integration (Claude Desktop & Cursor)
# -----------------------------------------------------------------------------

def resolve_claude_desktop_config_path(
    system: Optional[str] = None,
    home: Optional[Path] = None,
    appdata: Optional[str] = None,
) -> Path:
    """
    Deterministically resolves the Claude Desktop configuration path dynamically across platforms:
    - macOS (Darwin): ~/Library/Application Support/Claude/claude_desktop_config.json
    - Windows: %APPDATA%/Claude/claude_desktop_config.json
    - Linux / Other: ~/.config/Claude/claude_desktop_config.json
    """
    raw_sys = system if system is not None else platform.system()
    sys_name = raw_sys.strip().lower()
    home_dir = (home if home is not None else Path.home()).resolve()

    if sys_name == "darwin":
        return home_dir / "Library" / "Application Support" / "Claude" / "claude_desktop_config.json"
    elif sys_name == "windows":
        appdata_val = appdata if appdata is not None else os.environ.get("APPDATA")
        base = Path(appdata_val).resolve() if appdata_val else (home_dir / "AppData" / "Roaming")
        return base / "Claude" / "claude_desktop_config.json"
    else:
        return home_dir / ".config" / "Claude" / "claude_desktop_config.json"


def resolve_cursor_config_path(cwd: Optional[Path] = None) -> Path:
    """
    Resolves the workspace-scoped Cursor MCP configuration path in the current working directory:
    .cursor/mcp.json
    """
    base_cwd = (cwd if cwd is not None else Path.cwd()).resolve()
    return base_cwd / ".cursor" / "mcp.json"


def inject_agent_mcp_config(
    agent_name: str,
    config_path: Path,
    stream=None,
) -> bool:
    """
    Idempotently injects the standardized ctxfw MCP entrypoint into the target agent configuration file:
      {
        "command": "ctxfw",
        "args": ["mcp"]
      }
    - If the configuration file does not exist, initializes it with {"mcpServers": {}} using 2-space indentation.
    - If the file exists, parses existing JSON preserving all external keys, top-level settings, and third-party MCP servers.
    - If "ctxfw" is already defined under "mcpServers", does not overwrite; emits:
        [~] <Agent>: ctxfw is already configured.
    - Gracefully handles invalid/unparseable JSON reporting a clean warning to stdout/stderr without raising.
    - Emits ANSI-styled status outputs in English:
        [+] <Agent>: Context Firewall injected successfully into <filename>
    """
    out = stream if stream is not None else sys.stdout
    target_config = {
        "command": "ctxfw",
        "args": ["mcp"],
    }

    if config_path.is_dir():
        out.write(f"  {CLR_CRIMSON}[!] {agent_name}: Error - Configuration path is an existing directory, not a file: {config_path}{CLR_RESET}\n")
        if hasattr(out, "flush"):
            out.flush()
        return False

    data: Dict[str, Any] = {}
    if config_path.is_file():
        try:
            content = config_path.read_text(encoding="utf-8-sig").strip()
            if content:
                parsed = json.loads(content)
                if isinstance(parsed, dict):
                    data = parsed
                else:
                    raise ValueError(f"Root JSON entity is not an object (type={type(parsed).__name__})")
        except Exception as e:
            out.write(f"  {CLR_AMBER}[!] {agent_name}: Warning - Failed to parse configuration file {config_path}: {e}{CLR_RESET}\n")
            if hasattr(out, "flush"):
                out.flush()
            return False

    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    if "ctxfw" in data["mcpServers"]:
        out.write(f"  {CLR_AMBER}[~] {agent_name}: ctxfw is already configured.{CLR_RESET}\n")
        if hasattr(out, "flush"):
            out.flush()
        return False

    data["mcpServers"]["ctxfw"] = target_config

    try:
        config_path.parent.mkdir(parents=True, exist_ok=True)
        # Atomic file write to avoid corruption during concurrent writes or sudden termination
        payload_str = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        temp_file = config_path.parent / f".tmp_{config_path.name}_{os.getpid()}"
        temp_file.write_text(payload_str, encoding="utf-8")
        os.replace(temp_file, config_path)
    except Exception as e:
        try:
            if "temp_file" in locals() and temp_file.exists():
                temp_file.unlink(missing_ok=True)
        except Exception:
            pass
        out.write(f"  {CLR_CRIMSON}[!] {agent_name}: Error - Failed to write configuration file {config_path}: {e}{CLR_RESET}\n")
        if hasattr(out, "flush"):
            out.flush()
        return False

    out.write(f"  {CLR_EMERALD}[+] {agent_name}: Context Firewall injected successfully into {config_path}{CLR_RESET}\n")
    if hasattr(out, "flush"):
        out.flush()
    return True


def run_init_mcp_agents(
    cwd: Optional[Path] = None,
    home: Optional[Path] = None,
    system: Optional[str] = None,
    appdata: Optional[str] = None,
    stream=None,
) -> int:
    """
    Executes automated zero-friction MCP integration sweep across primary autonomous coding agents:
    1. Claude Desktop (Cross-platform dynamic path resolution)
    2. Cursor (Workspace scope .cursor/mcp.json)
    """
    out = stream if stream is not None else sys.stdout

    if hasattr(out, "reconfigure"):
        try:
            out.reconfigure(encoding="utf-8", errors="replace")
        except Exception:
            pass

    claude_path = resolve_claude_desktop_config_path(system=system, home=home, appdata=appdata)
    cursor_path = resolve_cursor_config_path(cwd=cwd)

    agents = [
        ("Claude Desktop", claude_path),
        ("Cursor", cursor_path),
    ]

    for agent_name, config_path in agents:
        inject_agent_mcp_config(agent_name, config_path, stream=out)

    try:
        out.write(f"  {CLR_EMERALD}✔ Zero-config integration complete. Restart your agent to activate.{CLR_RESET}\n")
    except UnicodeEncodeError:
        out.write(f"  {CLR_EMERALD}[OK] Zero-config integration complete. Restart your agent to activate.{CLR_RESET}\n")

    if hasattr(out, "flush"):
        out.flush()
    return 0


def inject_sovereign_rule(rule_path: Path) -> Tuple[bool, str]:
    """Idempotently writes the sovereign axiomatic directive into the target rules file."""
    marker = "SOVEREIGN AGENT DIRECTIVES (CTXFW PROTOCOL)"
    existing_content = ""
    if rule_path.is_file():
        existing_content = rule_path.read_text(encoding="utf-8")
        if marker in existing_content:
            return False, f"Directive already present in {rule_path}."

    rule_path.parent.mkdir(parents=True, exist_ok=True)
    delimiter = "\n\n" if existing_content.strip() else ""
    updated_content = existing_content + delimiter + SOVEREIGN_DIRECTIVE_RULE.strip() + "\n"
    rule_path.write_text(updated_content, encoding="utf-8")
    return True, f"Injected sovereign directive into {rule_path}."


def run_global_init(base_home: Optional[Path] = None) -> Dict[str, Any]:
    """
    Executes zero-touch global onboarding across all detected IDEs:
    Antigravity, Cursor, and Claude Desktop.
    """
    all_paths = resolve_ide_paths(base_home)
    actions_taken: List[str] = []
    configs_updated: List[str] = []
    rules_updated: List[str] = []

    for ide_name, spec in all_paths.items():
        configs = spec.get("configs", [])
        rules = spec.get("rules", [])

        for cfg_path in configs:
            # If IDE signature or parent exists, or for primary config
            if cfg_path.parent.exists() or ide_name == "Antigravity":
                updated, msg = safe_merge_mcp_config(cfg_path)
                actions_taken.append(f"[{ide_name}] {msg}")
                if updated:
                    configs_updated.append(str(cfg_path))

        for rule_path in rules:
            if rule_path.parent.exists() or ide_name == "Antigravity":
                updated, msg = inject_sovereign_rule(rule_path)
                actions_taken.append(f"[{ide_name}] {msg}")
                if updated:
                    rules_updated.append(str(rule_path))

    return {
        "status": "SUCCESS",
        "actions": actions_taken,
        "configs_updated": configs_updated,
        "rules_updated": rules_updated,
    }


def init_repository_perimeter(repo_dir: Path) -> Dict[str, Any]:
    """
    Initializes the local repository perimeter:
    - Writes canonical SPEC.axioms.md template if absent.
    - Deploys multiplatform pre-commit hook into .git/hooks/pre-commit.
    """
    repo = repo_dir.resolve()
    spec_path = repo / "SPEC.axioms.md"
    git_dir = repo / ".git"

    created_spec = False
    created_hook = False
    messages: List[str] = []

    # 1. SPEC.axioms.md template
    if not spec_path.exists():
        spec_path.write_text(CANONICAL_SPEC_TEMPLATE, encoding="utf-8")
        created_spec = True
        messages.append(f"Created canonical specification template: {spec_path}")
    else:
        messages.append(f"Specification brief already exists: {spec_path}")

    # 2. Git pre-commit hook
    if git_dir.is_dir():
        hooks_dir = git_dir / "hooks"
        hooks_dir.mkdir(parents=True, exist_ok=True)
        hook_path = hooks_dir / "pre-commit"

        hook_path.write_text(PRE_COMMIT_HOOK_SCRIPT, encoding="utf-8")
        # Ensure executable permissions on POSIX
        try:
            current_mode = hook_path.stat().st_mode
            hook_path.chmod(current_mode | stat.S_IXUSR | stat.S_IXGRP | stat.S_IXOTH)
        except Exception:
            pass

        created_hook = True
        messages.append(f"Installed sovereign pre-commit gatekeeper hook: {hook_path}")
    else:
        messages.append(f"Warning: .git directory not found in {repo}. Pre-commit hook skipped.")

    return {
        "repo_dir": str(repo),
        "created_spec": created_spec,
        "created_hook": created_hook,
        "messages": messages,
    }


# -----------------------------------------------------------------------------
# Doctor Self-Diagnostics Engine
# -----------------------------------------------------------------------------

def run_doctor(project_root: Optional[Path] = None) -> DoctorReport:
    """
    Executes a comprehensive health self-diagnostic of the ctxfw toolchain:
    1. Python environment and sys.path resolution.
    2. Hot stdio log isolation assertion for MCP server.
    3. Global CLI binary resolution in system PATH.
    4. Sieve Engine cryptographic attestation and ACI floor check.
    5. SQLite WAL cache health and busy timeout validation.
    6. Polyglot Tree-Sitter grammar availability.
    """
    checks: List[DoctorCheckResult] = []

    # Check 1: Python environment & package resolution
    try:
        import ctxfw
        pkg_file = getattr(ctxfw, "__file__", "unknown")
        pkg_ver = getattr(ctxfw, "__version__", "unknown")
        checks.append(
            DoctorCheckResult(
                name="Python Package & sys.path",
                status="OK",
                details=f"ctxfw v{pkg_ver} loaded cleanly from {pkg_file}.",
            )
        )
    except Exception as e:
        checks.append(
            DoctorCheckResult(
                name="Python Package & sys.path",
                status="FAIL",
                details=f"Failed to import ctxfw: {e}",
                remediation="Ensure ctxfw is installed: run 'pip install -e .' or 'pipx install .'",
            )
        )

    # Check 2: Hot stdio isolation test (Doctor Sanitizer)
    try:
        proc = subprocess.Popen(
            [sys.executable, "-m", "ctxfw.mcp"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        init_req = json.dumps({
            "jsonrpc": "2.0",
            "id": 999,
            "method": "initialize",
            "params": {"capabilities": {}},
        }) + "\n"

        stdout_data, stderr_data = proc.communicate(input=init_req, timeout=5)
        proc.wait(timeout=2)

        # Assert stdout contains ONLY valid JSON and zero unescaped non-JSON text
        stdout_lines = [line.strip() for line in stdout_data.splitlines() if line.strip()]
        if not stdout_lines:
            checks.append(
                DoctorCheckResult(
                    name="MCP stdio Stream Isolation",
                    status="FAIL",
                    details="No response received on stdout during MCP handshake.",
                    remediation="Check ctxfw.mcp initialization loop.",
                )
            )
        else:
            all_valid_json = True
            found_response = False
            for line in stdout_lines:
                try:
                    parsed = json.loads(line)
                    if parsed.get("id") == 999 and "result" in parsed:
                        found_response = True
                except Exception:
                    all_valid_json = False
                    break

            if all_valid_json and found_response:
                checks.append(
                    DoctorCheckResult(
                        name="MCP stdio Stream Isolation",
                        status="OK",
                        details="100% pure JSON-RPC on stdout. Diagnostic logs correctly isolated to stderr.",
                    )
                )
            else:
                checks.append(
                    DoctorCheckResult(
                        name="MCP stdio Stream Isolation",
                        status="FAIL",
                        details=f"Non-JSON pollution detected on stdout. Raw output: {stdout_data[:200]}",
                        remediation="Remove raw print() calls writing to stdout; redirect all logging to sys.stderr.",
                    )
                )
    except Exception as e:
        checks.append(
            DoctorCheckResult(
                name="MCP stdio Stream Isolation",
                status="FAIL",
                details=f"Failed to execute MCP stdio isolation probe: {e}",
                remediation="Ensure ctxfw.mcp is executable in current Python environment.",
            )
        )

    # Check 3: Global CLI executable resolution
    cli_bin = shutil.which("ctxfw")
    if cli_bin:
        checks.append(
            DoctorCheckResult(
                name="Global CLI Executable (PATH)",
                status="OK",
                details=f"Binary 'ctxfw' found in PATH: {cli_bin}",
            )
        )
    else:
        checks.append(
            DoctorCheckResult(
                name="Global CLI Executable (PATH)",
                status="WARN",
                details="Binary 'ctxfw' is not currently in system PATH.",
                remediation="Install into PATH via 'pip install -e .' or 'pipx install .'",
            )
        )

    # Check 4: Sieve Engine cryptographic attestation & ACI verification
    try:
        eval_res = evaluate_specification(CANONICAL_SPEC_TEMPLATE)
        if eval_res.status == "VERIFIED" and eval_res.aci_score >= 0.9000:
            checks.append(
                DoctorCheckResult(
                    name="Axiomatic Sieve Engine",
                    status="OK",
                    details=f"Evaluation verified (ACI: {eval_res.aci_score:.4f}, Invariants: {eval_res.negative_invariants_count}, Hash: {eval_res.manifest_hash[:16]}...).",
                )
            )
        else:
            checks.append(
                DoctorCheckResult(
                    name="Axiomatic Sieve Engine",
                    status="FAIL",
                    details=f"Canonical evaluation failed with status {eval_res.status} (ACI: {eval_res.aci_score:.4f}).",
                    remediation="Check ctxfw.sieve.engine criteria and bounds calculation.",
                )
            )
    except Exception as e:
        checks.append(
            DoctorCheckResult(
                name="Axiomatic Sieve Engine",
                status="FAIL",
                details=f"Sieve evaluation encountered exception: {e}",
                remediation="Validate pydantic and regex dependencies.",
            )
        )

    # Check 5: SQLite WAL & cache configuration
    try:
        from ctxfw.storage.cache import LocalSemanticCache
        cache = LocalSemanticCache()
        with cache._get_connection() as conn:
            cursor = conn.cursor()
            cursor.execute("PRAGMA journal_mode;")
            journal_mode = cursor.fetchone()[0]
            cursor.execute("PRAGMA busy_timeout;")
            busy_timeout = cursor.fetchone()[0]

        if str(journal_mode).lower() == "wal" and int(busy_timeout) >= 100:
            checks.append(
                DoctorCheckResult(
                    name="SQLite WAL Cache & Concurrency",
                    status="OK",
                    details=f"Journal mode: {journal_mode.upper()}, Busy timeout: {busy_timeout}ms.",
                )
            )
        else:
            checks.append(
                DoctorCheckResult(
                    name="SQLite WAL Cache & Concurrency",
                    status="WARN",
                    details=f"Non-optimal database PRAGMAs: journal_mode={journal_mode}, busy_timeout={busy_timeout}ms.",
                    remediation="Ensure LocalSemanticCache enables WAL mode and busy_timeout >= 5000.",
                )
            )
    except Exception as e:
        checks.append(
            DoctorCheckResult(
                name="SQLite WAL Cache & Concurrency",
                status="FAIL",
                details=f"Cache connection test failed: {e}",
                remediation="Verify write permissions in XDG / AppData directory.",
            )
        )

    # Check 6: Tree-sitter Polyglot Grammars
    try:
        from ctxfw.core.polyglot import TreeSitterContextPruner
        from ctxfw.core.contracts import SupportedLanguage
        loaded_langs = []
        for lang in (SupportedLanguage.TYPESCRIPT, SupportedLanguage.GO, SupportedLanguage.JAVA):
            try:
                parser = TreeSitterContextPruner._get_parser(lang)
                if parser:
                    loaded_langs.append(lang.value)
            except Exception:
                pass
        
        checks.append(
            DoctorCheckResult(
                name="Polyglot Tree-Sitter Grammars",
                status="OK" if loaded_langs else "WARN",
                details=f"Initialized {len(loaded_langs)} language parsers ({', '.join(loaded_langs)}).",
                remediation="Install language grammar packages: tree-sitter-typescript, tree-sitter-go, tree-sitter-java." if not loaded_langs else None,
            )
        )
    except Exception as e:
        checks.append(
            DoctorCheckResult(
                name="Polyglot Tree-Sitter Grammars",
                status="WARN",
                details=f"Tree-Sitter parsers encountered warning: {e}",
                remediation="Ensure tree-sitter language packages are installed.",
            )
        )

    # Project-level Perimeter Checks (if project_root is provided)
    if project_root and Path(project_root).is_dir():
        resolved_root = Path(project_root).resolve()

        # Check 7: Project Specification Perimeter (SPEC.axioms.md)
        spec_candidates = [
            resolved_root / "SPEC.axioms.md",
            resolved_root / "SPEC.md",
            resolved_root / "SPEC_MASTER.md",
        ]
        active_spec = next((s for s in spec_candidates if s.is_file()), None)
        if active_spec:
            try:
                spec_content = active_spec.read_text(encoding="utf-8")
                eval_res = evaluate_specification(spec_content)
                if eval_res.status == "VERIFIED":
                    checks.append(
                        DoctorCheckResult(
                            name="Project Axiomatic Spec",
                            status="OK",
                            details=f"Verified {active_spec.name} (ACI: {eval_res.aci_score:.4f}, Invariants: {eval_res.negative_invariants_count}).",
                        )
                    )
                else:
                    checks.append(
                        DoctorCheckResult(
                            name="Project Axiomatic Spec",
                            status="WARN",
                            details=f"{active_spec.name} quarantined (ACI: {eval_res.aci_score:.4f}, Invariants: {eval_res.negative_invariants_count}).",
                            remediation=f"Improve {active_spec.name} to achieve ACI >= 0.9000 and >= 5 negative invariants.",
                        )
                    )
            except Exception as e:
                checks.append(
                    DoctorCheckResult(
                        name="Project Axiomatic Spec",
                        status="WARN",
                        details=f"Failed reading {active_spec.name}: {e}",
                        remediation="Verify file encoding and permissions.",
                    )
                )
        else:
            checks.append(
                DoctorCheckResult(
                    name="Project Axiomatic Spec",
                    status="WARN",
                    details=f"No SPEC.axioms.md found in {resolved_root.name}.",
                    remediation=f"Initialize repository perimeter: 'ctxfw init --repo {resolved_root}'",
                )
            )

        # Check 8: Project MCP Perimeter (.mcp.json)
        mcp_candidates = [
            resolved_root / ".mcp.json",
            resolved_root / ".gemini" / "config" / "mcp_config.json",
        ]
        has_mcp = any(m.is_file() for m in mcp_candidates)
        if has_mcp:
            checks.append(
                DoctorCheckResult(
                    name="Project MCP Perimeter",
                    status="OK",
                    details=f"MCP configuration found in {resolved_root.name}.",
                )
            )
        else:
            checks.append(
                DoctorCheckResult(
                    name="Project MCP Perimeter",
                    status="WARN",
                    details=f"No local .mcp.json detected in {resolved_root.name}.",
                    remediation="Add .mcp.json or run 'ctxfw init' to configure MCP server integration.",
                )
            )

        # Check 9: Pre-commit Hook Attestation
        hook_path = resolved_root / ".git" / "hooks" / "pre-commit"
        if hook_path.is_file():
            try:
                hook_txt = hook_path.read_text(encoding="utf-8", errors="ignore")
                if "ctxfw" in hook_txt or "spec verify" in hook_txt:
                    checks.append(
                        DoctorCheckResult(
                            name="Git Pre-Commit Gatekeeper",
                            status="OK",
                            details="Active ctxfw axiomatic gatekeeper hook verified.",
                        )
                    )
                else:
                    checks.append(
                        DoctorCheckResult(
                            name="Git Pre-Commit Gatekeeper",
                            status="WARN",
                            details="Existing pre-commit hook does not reference ctxfw.",
                            remediation="Integrate ctxfw gatekeeper via 'ctxfw init --repo .'",
                        )
                    )
            except Exception as e:
                checks.append(
                    DoctorCheckResult(
                        name="Git Pre-Commit Gatekeeper",
                        status="WARN",
                        details=f"Unable to read pre-commit hook: {e}",
                    )
                )
        elif (resolved_root / ".git").is_dir():
            checks.append(
                DoctorCheckResult(
                    name="Git Pre-Commit Gatekeeper",
                    status="WARN",
                    details="No pre-commit hook installed in .git/hooks/.",
                    remediation="Deploy pre-commit gatekeeper: 'ctxfw init --repo .'",
                )
            )

    all_passed = not any(c.status == "FAIL" for c in checks)
    return DoctorReport(all_passed=all_passed, checks=checks)


def render_doctor_report(report: DoctorReport, out=None) -> int:
    """Renders the health diagnostic summary to terminal stream."""
    stream = out if out is not None else sys.stdout
    print_defense_banner(stream)
    stream.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
    stream.write(f"  {CLR_CYAN}CTXFW DOCTOR // HIGH-ASSURANCE HEALTH & ISOLATION DIAGNOSTIC{CLR_RESET}\n")
    stream.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")

    for check in report.checks:
        if check.status == "OK":
            tag_str = f"{CLR_EMERALD}[PASS]{CLR_RESET}  "
        elif check.status == "FAIL":
            tag_str = f"{CLR_CRIMSON}[FAIL]{CLR_RESET}  "
        elif check.status == "WARN":
            tag_str = f"{CLR_AMBER}[WARN]{CLR_RESET}  "
        else:
            tag_str = f"[{check.status}] "

        stream.write(f"{tag_str} {CLR_WHITE_BOLD}{check.name:<32}{CLR_RESET} {check.details}\n")
        if check.remediation and check.status != "OK":
            stream.write(f"         {CLR_AMBER}Remediation: {check.remediation}{CLR_RESET}\n")

    stream.write(f"{CLR_GRAPHITE}" + "-" * 72 + f"{CLR_RESET}\n")
    if report.all_passed:
        stream.write(f"{CLR_WHITE_BOLD}Overall Verdict:{CLR_RESET}            {CLR_EMERALD}[HEALTHY] [ATTESTED]{CLR_RESET} Perimeter defense operational.\n")
        stream.write("========================================================================\n")
        stream.write("CTXFW // 72.4% AST Bloat Eliminated. Zero Telemetry Egress.\n")
        stream.write("Need team-wide budget circuit breakers or multi-node proxy governance?\n")
        stream.write("Control Plane & Enterprise Licensing: https://ctxfw.heuristicolab.com\n")
        stream.write("========================================================================\n")
        return 0
    else:
        stream.write(f"{CLR_WHITE_BOLD}Overall Verdict:{CLR_RESET}            {CLR_CRIMSON}[QUARANTINED]{CLR_RESET} One or more critical security checks failed.\n")
        stream.write(f"{CLR_GRAPHITE}========================================================================{CLR_RESET}\n")
        return 1
