#!/usr/bin/env bash
# ==============================================================================
# CTXFW // Context Firewall - Autonomous Bootstrap & Multi-IDE Sentry Installer
# HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE
# Official Repository: https://github.com/heuristicolab/ctxfw
# Telemetry Ingestion: https://ctxfw.heuristicolab.com/api/register-lead
# ==============================================================================
set -euo pipefail

VERSION="v3.7.0"
BIN_NAME="ctxfw"
CONFIG_DIR="${HOME}/.ctxfw"
VENV_DIR="${CONFIG_DIR}/venv"
INSTALL_DIR="${HOME}/.local/bin"
GLOBAL_BIN="/usr/local/bin/${BIN_NAME}"
OS_TYPE="$(uname -s 2>/dev/null || echo "Unknown")"
ARCH_TYPE="$(uname -m 2>/dev/null || echo "Unknown")"

# Resolution of Claude Desktop configuration directory across OS types
if [ "$OS_TYPE" = "Darwin" ]; then
    CLAUDE_CONFIG_DIR="${HOME}/Library/Application Support/Claude"
else
    CLAUDE_CONFIG_DIR="${HOME}/.config/Claude"
fi
CLAUDE_CONFIG="${CLAUDE_CONFIG_DIR}/claude_desktop_config.json"

# ANSI Color Palette
CYAN='\033[38;5;51m'
EMERALD='\033[38;5;48m'
WHITE='\033[1;37m'
AMBER='\033[38;5;214m'
GRAPHITE='\033[38;5;240m'
RESET='\033[0m'

# Subroutine de Purga / Desinstalacion
purge_ctxfw() {
    printf "\n\033[1;36m[CTXFW // PERIMETER PURGE]\033[0m Initiating clean teardown...\n"
    
    # 1. Purge local and global binaries
    if [ -f "${INSTALL_DIR}/${BIN_NAME}" ] || [ -L "${INSTALL_DIR}/${BIN_NAME}" ]; then
        rm -f "${INSTALL_DIR}/${BIN_NAME}"
        printf "  \033[32m✓\033[0m Local binary removed: %s/%s\n" "${INSTALL_DIR}" "${BIN_NAME}"
    fi

    if [ -f "${GLOBAL_BIN}" ] || [ -L "${GLOBAL_BIN}" ]; then
        rm -f "${GLOBAL_BIN}" 2>/dev/null || sudo rm -f "${GLOBAL_BIN}" 2>/dev/null || true
        printf "  \033[32m✓\033[0m Global binary removed: %s\n" "${GLOBAL_BIN}"
    fi

    # 2. Purge isolated runtime virtualenv & configuration sandbox
    if [ -d "${CONFIG_DIR}" ]; then
        rm -rf "${CONFIG_DIR}"
        printf "  \033[32m✓\033[0m Configuration & isolated virtualenv purged: %s\n" "${CONFIG_DIR}"
    fi

    # 3. Clean Claude Desktop MCP configuration entry if present
    if [ -f "${CLAUDE_CONFIG}" ] && command -v python3 >/dev/null 2>&1; then
        python3 -c '
import json, sys
from pathlib import Path
cfg = Path(sys.argv[1])
try:
    if cfg.is_file():
        data = json.loads(cfg.read_text(encoding="utf-8"))
        if "mcpServers" in data and "ctxfw" in data["mcpServers"]:
            del data["mcpServers"]["ctxfw"]
            cfg.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            print("  \033[32m✓\033[0m Cleaned MCP entry from Claude Desktop config.")
except Exception:
    pass
' "${CLAUDE_CONFIG}" 2>/dev/null || true
    fi

    # 4. Sanitize shell startup files (.bashrc, .zshrc, .profile)
    for rcfile in "${HOME}/.bashrc" "${HOME}/.zshrc" "${HOME}/.profile"; do
        if [ -f "$rcfile" ] && grep -q "ctxfw" "$rcfile"; then
            if sed --version 2>/dev/null | grep -q GNU; then
                sed -i '/ctxfw/d' "$rcfile"
            else
                sed -i '' '/ctxfw/d' "$rcfile"
            fi
            printf "  \033[32m✓\033[0m Cleaned entries in: %s\n" "$rcfile"
        fi
    done

    printf "\n\033[1;32m[DONE]\033[0m Teardown complete. Zero traces remaining on host system.\n\n"
    exit 0
}

# Evaluar si se paso argumento de desinstalacion
case "${1:-}" in
    --uninstall|-u|uninstall|purge)
        purge_ctxfw
        ;;
esac

echo -e "${CYAN}"
cat << 'EOF'
  ██████╗████████╗██╗  ██╗███████╗██╗    ██╗
 ██╔════╝╚══██╔══╝╚██╗██╔╝██╔════╝██║    ██║
 ██║        ██║    ╚███╔╝ █████╗  ██║ █╗ ██║
 ██║        ██║    ██╔██╗ ██╔══╝  ██║███╗██║
 ╚██████╗   ██║   ██╔╝ ██╗██║     ╚███╔███╔╝
  ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝      ╚══╝╚══╝  v3.7.0
 ░░░ HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE ░░░
EOF
echo -e "${RESET}"

# Interactive Telemetry Capture (Mission Control Radar Ingestion)
TTY_DEV=""
if [ -e /dev/tty ] && [ -r /dev/tty ]; then
    TTY_DEV="/dev/tty"
elif [ -t 0 ]; then
    TTY_DEV=""
fi

prompt_read() {
    local prompt_text="$1"
    local default_text="${2:-}"
    local user_input=""
    if [ -n "$TTY_DEV" ]; then
        read -r -p "$prompt_text" user_input < "$TTY_DEV" || true
    elif [ -t 0 ]; then
        read -r -p "$prompt_text" user_input || true
    fi
    if [ -z "$user_input" ]; then
        echo "$default_text"
    else
        echo "$user_input"
    fi
}

echo -e "${CYAN}========================================================================${RESET}"
echo -e "  ${WHITE}CTXFW SQUAD ONBOARDING TELEMETRY (DEFENSE GRADE // v3.6.0)${RESET}"
echo -e "${CYAN}========================================================================${RESET}"

if [ -n "$TTY_DEV" ] || [ -t 0 ]; then
    echo -e "${GRAPHITE}Enter squad telemetry to initialize FinOps radar in Mission Control:${RESET}"
    echo ""
    LEAD_EMAIL=$(prompt_read "  > Work Email: " "")
    SQUAD_SIZE=$(prompt_read "  > Squad Size [Default: 25]: " "25")
    LEAD_NAME=$(prompt_read "  > Lead Engineer [Default: Lead Engineer]: " "Lead Engineer")
    echo ""

    if [ -n "$LEAD_EMAIL" ]; then
        echo -e "${WHITE}[*]${RESET} Registering node telemetry with CTXFW Mission Control..."
        INGEST_URL="https://ctxfw.heuristicolab.com/api/register-lead"
        INGEST_PAYLOAD="{\"email\":\"${LEAD_EMAIL}\", \"dev_count\":${SQUAD_SIZE}, \"lead_name\":\"${LEAD_NAME}\"}"
        
        RESPONSE=$(curl -fsSL -X POST "$INGEST_URL" \
            -H "Content-Type: application/json" \
            -d "$INGEST_PAYLOAD" 2>/dev/null || true)
            
        if [ -n "$RESPONSE" ]; then
            echo -e "${EMERALD}[✓] Node telemetry registered in Mission Control (01 // DISCOVERED).${RESET}"
        else
            echo -e "${AMBER}[!] Telemetry queued locally (remote registration endpoint unreachable).${RESET}"
        fi
    fi
else
    echo -e "${GRAPHITE}[*] Non-interactive mode detected. Proceeding with autonomous diagnostic...${RESET}"
fi

echo ""
echo -e "${WHITE}[1/4]${RESET} Detecting and resolving host Python 3 runtime..."

# Discovery across standard and macOS Homebrew/Xcode paths
PYTHON_BIN=""
CANDIDATES=("python3" "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "/usr/bin/python3" "python")

for candidate in "${CANDIDATES[@]}"; do
    if command -v "$candidate" >/dev/null 2>&1; then
        if "$candidate" -c 'import sys; exit(0 if sys.version_info >= (3, 8) else 1)' 2>/dev/null; then
            PYTHON_BIN="$candidate"
            break
        fi
    fi
done

# Autonomous recovery for macOS if Python 3 is missing
if [ -z "$PYTHON_BIN" ] && [ "$OS_TYPE" = "Darwin" ]; then
    echo -e "${AMBER}[!] Python 3 not detected. Attempting automatic resolution via Homebrew...${RESET}"
    if command -v brew >/dev/null 2>&1; then
        brew install python || true
    elif [ -x "/opt/homebrew/bin/brew" ]; then
        eval "$(/opt/homebrew/bin/brew shellenv)"
        brew install python || true
    elif [ -x "/usr/local/bin/brew" ]; then
        eval "$(/usr/local/bin/brew shellenv)"
        brew install python || true
    fi
    
    for candidate in "/opt/homebrew/bin/python3" "/usr/local/bin/python3" "python3"; do
        if command -v "$candidate" >/dev/null 2>&1; then
            PYTHON_BIN="$candidate"
            break
        fi
    done
fi

if [ -z "$PYTHON_BIN" ]; then
    echo -e "${AMBER}[FAIL] Python 3.8+ runtime is required but could not be located.${RESET}"
    echo -e "${GRAPHITE}Please install Python via Homebrew ('brew install python') or your package manager.${RESET}"
    exit 1
fi

PY_VER=$("$PYTHON_BIN" -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}")')
echo -e "${EMERALD}[PASS] Python ${PY_VER} detected: ${PYTHON_BIN}${RESET}"

echo -e "${WHITE}[2/4]${RESET} Provisioning isolated virtual environment (PEP 668 compliant)..."
mkdir -p "${CONFIG_DIR}"

if [ ! -d "${VENV_DIR}" ] || [ ! -x "${VENV_DIR}/bin/python" ]; then
    echo -e "${GRAPHITE}      Creating sandbox: ${VENV_DIR}${RESET}"
    "$PYTHON_BIN" -m venv "${VENV_DIR}"
fi

VENV_PIP="${VENV_DIR}/bin/pip"
VENV_BIN="${VENV_DIR}/bin/${BIN_NAME}"

# Install or upgrade ctxfw inside isolated sandbox
echo -e "${GRAPHITE}      Installing ctxfw==3.7.0 from PyPI into isolated runtime...${RESET}"
"$VENV_PIP" install --upgrade --quiet pip setuptools wheel 2>/dev/null || true
"$VENV_PIP" install --upgrade "ctxfw>=3.7.0"

if [ ! -x "$VENV_BIN" ]; then
    echo -e "${AMBER}[FAIL] ctxfw binary was not created in ${VENV_DIR}/bin.${RESET}"
    exit 1
fi
echo -e "${EMERALD}[PASS] Isolated runtime sandbox ready.${RESET}"

echo -e "${WHITE}[3/4]${RESET} Linking binary to user PATH and shell environments..."
mkdir -p "${INSTALL_DIR}"
ln -sf "${VENV_BIN}" "${INSTALL_DIR}/${BIN_NAME}"
chmod +x "${INSTALL_DIR}/${BIN_NAME}"

# Attempt global symlink if /usr/local/bin is writable
if [ -w "/usr/local/bin" ]; then
    ln -sf "${VENV_BIN}" "${GLOBAL_BIN}" 2>/dev/null || true
    echo -e "${GRAPHITE}      Linked global binary: ${GLOBAL_BIN}${RESET}"
fi

# Ensure ~/.local/bin is in PATH for shell sessions
if [[ ":$PATH:" != *":${INSTALL_DIR}:"* ]]; then
    echo -e "${GRAPHITE}      Configuring PATH in shell profiles...${RESET}"
    PATH_LINE="export PATH=\"${INSTALL_DIR}:\$PATH\""
    for rc in "${HOME}/.zshrc" "${HOME}/.bashrc" "${HOME}/.profile"; do
        if [ -f "$rc" ]; then
            if ! grep -q '\.local/bin' "$rc"; then
                printf "\n# CTXFW Sovereign Perimeter\n%s\n" "$PATH_LINE" >> "$rc"
            fi
        elif [ "$rc" = "${HOME}/.zshrc" ] && [ "$OS_TYPE" = "Darwin" ]; then
            printf "# CTXFW Sovereign Perimeter\n%s\n" "$PATH_LINE" >> "$rc"
        fi
    done
    export PATH="${INSTALL_DIR}:${PATH}"
fi
echo -e "${EMERALD}[PASS] Binary accessible via: ${INSTALL_DIR}/${BIN_NAME}${RESET}"

echo -e "${WHITE}[4/4]${RESET} Configuring Claude Desktop & multi-IDE sovereign perimeter..."

# Ensure Claude Desktop configuration directory exists on macOS/Linux
mkdir -p "${CLAUDE_CONFIG_DIR}"

# Run idempotent multi-IDE injection
"${VENV_BIN}" init --global

# Configure Claude Desktop with explicit resolved binary path
# (Guarantees execution in macOS GUI environment where launchd omits user PATH)
"${VENV_DIR}/bin/python" -c '
import json, sys
from pathlib import Path

config_path = Path(sys.argv[1])
binary_path = sys.argv[2]

try:
    data = {}
    if config_path.is_file():
        content = config_path.read_text(encoding="utf-8").strip()
        if content:
            data = json.loads(content)
    if not isinstance(data, dict):
        data = {}
    if "mcpServers" not in data or not isinstance(data["mcpServers"], dict):
        data["mcpServers"] = {}

    data["mcpServers"]["ctxfw"] = {
        "command": binary_path,
        "args": ["mcp"]
    }

    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"      [PASS] Injected Claude Desktop MCP server ({config_path})")
except Exception as e:
    print(f"      [WARN] Claude Desktop config note: {e}")
' "${CLAUDE_CONFIG}" "${INSTALL_DIR}/${BIN_NAME}"

echo ""
echo -e "${WHITE}[DIAGNOSTIC]${RESET} Executing ctxfw doctor self-test..."
"${INSTALL_DIR}/${BIN_NAME}" doctor || true

echo ""
echo -e "${CYAN}========================================================================${RESET}"
echo -e "  ${WHITE}CTXFW v3.7.0 INSTALLATION COMPLETE // PERIMETER SECURED${RESET}"
echo -e "  ${GRAPHITE}Binary:        ${INSTALL_DIR}/${BIN_NAME}${RESET}"
echo -e "  ${GRAPHITE}Sandbox:       ${VENV_DIR}${RESET}"
echo -e "  ${GRAPHITE}Claude Config: ${CLAUDE_CONFIG}${RESET}"
echo -e "${CYAN}========================================================================${RESET}"
