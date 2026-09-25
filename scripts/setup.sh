#!/usr/bin/env bash
# setup.sh — 1-Click Bootstrap Installer for POSIX/Linux/macOS (Hermetic Toolchain v3.4.0)
set -euo pipefail

echo -e "\033[36m======================================================\033[0m"
echo -e "\033[36m   CTXFW HERMETIC TOOLCHAIN -- 1-CLICK BOOTSTRAP      \033[0m"
echo -e "\033[36m======================================================\033[0m"

VENV_DIR=".venv"
VENV_PYTHON="$VENV_DIR/bin/python"
VENV_PIP="$VENV_DIR/bin/pip"

# 1. Virtual Environment Setup
if [ ! -f "$VENV_PYTHON" ]; then
    echo -e "\n\033[33m[1/4] Creating virtual environment (.venv)...\033[0m"
    python3 -m venv "$VENV_DIR"
else
    echo -e "\n\033[32m[1/4] Virtual environment (.venv) already exists.\033[0m"
fi

# 2. Dependencies & Editable Package Installation
echo -e "\n\033[33m[2/4] Installing dependencies & registering ctxfw in .venv...\033[0m"
"$VENV_PYTHON" -m pip install --upgrade pip --quiet
"$VENV_PYTHON" -m pip install -e . --quiet

# 3. Test Certification
echo -e "\n\033[33m[3/4] Certifying 51 TDD tests with .venv test runner...\033[0m"
"$VENV_PYTHON" -m pytest tests/ -q

# 4. Generate Root Executable Wrappers (ctxfw and firewall)
echo -e "\n\033[33m[4/4] Generating root CLI wrappers (ctxfw and firewall)...\033[0m"
cat << 'EOF' > ctxfw
#!/usr/bin/env bash
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec "$DIR/.venv/bin/python" -m ctxfw "$@"
EOF
chmod +x ctxfw
cp ctxfw firewall
chmod +x firewall

echo -e "\n\033[32m======================================================\033[0m"
echo -e "\033[32m   BOOTSTRAP COMPLETE & CERTIFIED (51/51 PASSED)      \033[0m"
echo -e "\033[32m======================================================\033[0m"
echo -e "You can now execute directly from anywhere in the repo:"
echo -e "  ./ctxfw contracts.py"
echo -e "  ./ctxfw mcp           (Stdio JSON-RPC daemon)"
echo -e "  ./ctxfw proxy         (Reverse proxy perimetral)"
echo -e "  ./ctxfw ci            (Gatekeeper & PR Impact)\n"
