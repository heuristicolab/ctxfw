#!/usr/bin/env bash
set -e
echo "=========================================="
echo "   SATELLITE CHECKPOINT & QA PROTOCOL     "
echo "=========================================="

PYTHON_CMD="python3"
if [ -f ".venv/bin/python" ]; then
    PYTHON_CMD=".venv/bin/python"
elif [ -f ".venv/Scripts/python.exe" ]; then
    PYTHON_CMD=".venv/Scripts/python.exe"
fi

echo -e "\n[1/2] Executing automated verification matrix..."
$PYTHON_CMD -m pytest tests/ -v

echo "[2/2] Telemetry emitted to tests/test_report.json."
echo "=========================================="
echo "   CHECKPOINT ATTESTED & VERIFIED         "
echo "=========================================="
