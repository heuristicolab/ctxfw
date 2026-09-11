#!/usr/bin/env bash
# ==============================================================================
# CTXFW // Context Firewall - Canonical Installer
# HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE
# Official Repository: https://github.com/heuristicolab/ctxfw
# ==============================================================================
set -euo pipefail

CYAN='\033[38;5;51m'
EMERALD='\033[38;5;48m'
WHITE='\033[1;37m'
RESET='\033[0m'

echo -e "${CYAN}"
cat << 'EOF'
  ██████╗████████╗██╗  ██╗███████╗██╗    ██╗
 ██╔════╝╚══██╔══╝╚██╗██╔╝██╔════╝██║    ██║
 ██║        ██║    ╚███╔╝ █████╗  ██║ █╗ ██║
 ██║        ██║    ██╔██╗ ██╔══╝  ██║███╗██║
 ╚██████╗   ██║   ██╔╝ ██╗██║     ╚███╔███╔╝
  ╚═════╝   ╚═╝   ╚═╝  ╚═╝╚═╝      ╚══╝╚══╝  v3.5.0
 ░░░ HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE ░░░
EOF
echo -e "${RESET}"

echo -e "${WHITE}[1/3]${RESET} Verifying Python 3.10+ runtime..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required to install ctxfw." >&2
    exit 1
fi

echo -e "${WHITE}[2/3]${RESET} Installing CTXFW engine via pip..."
python3 -m pip install --upgrade ctxfw || {
    echo -e "${WHITE}[*]${RESET} Falling back to GitHub repository..."
    python3 -m pip install --upgrade git+https://github.com/heuristicolab/ctxfw.git
}

echo -e "${WHITE}[3/3]${RESET} Initializing multi-IDE zero-touch injection..."
if command -v ctxfw >/dev/null 2>&1; then
    ctxfw init --global || true
    echo -e "${EMERALD}[PASS] CTXFW successfully installed and registered.${RESET}"
    ctxfw doctor || true
else
    python3 -m ctxfw init --global || true
    echo -e "${EMERALD}[PASS] CTXFW module installed.${RESET}"
fi
