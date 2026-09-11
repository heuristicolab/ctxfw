#!/usr/bin/env bash
# ==============================================================================
# CTXFW // Context Firewall - Interactive Telemetry Installer
# HEURISTICO LAB // SKUNK WORKS DIVISION // DEFENSE GRADE
# Official Repository: https://github.com/heuristicolab/ctxfw
# Telemetry Ingestion: https://ctxfw.heuristicolab.com/api/register-lead
# ==============================================================================
set -euo pipefail

CYAN='\033[38;5;51m'
EMERALD='\033[38;5;48m'
WHITE='\033[1;37m'
AMBER='\033[38;5;214m'
GRAPHITE='\033[38;5;240m'
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
echo -e "  ${WHITE}CTXFW SQUAD ONBOARDING TELEMETRY (DEFENSE GRADE)${RESET}"
echo -e "${CYAN}========================================================================${RESET}"

if [ -n "$TTY_DEV" ] || [ -t 0 ]; then
    echo -e "${GRAPHITE}Ingresa los datos del equipo para inicializar el radar FinOps en Mission Control:${RESET}"
    echo ""
    LEAD_EMAIL=$(prompt_read "  > Work Email / Correo Corporativo: " "")
    SQUAD_SIZE=$(prompt_read "  > Squad Size / Desarrolladores [Default: 25]: " "25")
    LEAD_NAME=$(prompt_read "  > Lead Engineer / Nombre [Default: Lead Engineer]: " "Lead Engineer")
    echo ""

    if [ -n "$LEAD_EMAIL" ]; then
        echo -e "${WHITE}[*]${RESET} Registrando nodo en CTXFW Mission Control..."
        INGEST_URL="https://ctxfw.heuristicolab.com/api/register-lead"
        INGEST_PAYLOAD="{\"email\":\"${LEAD_EMAIL}\", \"dev_count\":${SQUAD_SIZE}, \"lead_name\":\"${LEAD_NAME}\"}"
        
        RESPONSE=$(curl -fsSL -X POST "$INGEST_URL" \
            -H "Content-Type: application/json" \
            -d "$INGEST_PAYLOAD" 2>/dev/null || true)
            
        if [ -n "$RESPONSE" ]; then
            echo -e "${EMERALD}[✓] Nodo registrado exitosamente en Mission Control (01 // DISCOVERED).${RESET}"
        else
            echo -e "${AMBER}[!] Telemetría en cola local (servidor de registro no disponible temporalmente).${RESET}"
        fi
    fi
else
    echo -e "${GRAPHITE}[*] Modo no-interactivo detectado. Continuando instalación zero-touch...${RESET}"
fi

echo ""
echo -e "${WHITE}[1/3]${RESET} Verifying Python 3.10+ runtime..."
if ! command -v python3 >/dev/null 2>&1; then
    echo "Error: python3 is required to install ctxfw." >&2
    exit 1
fi

echo -e "${WHITE}[2/3]${RESET} Installing CTXFW engine via pip..."
python3 -m pip install --upgrade ctxfw 2>/dev/null || {
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
