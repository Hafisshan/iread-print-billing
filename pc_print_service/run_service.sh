#!/usr/bin/env bash
# Iread PC Thermal Print Service Launcher for macOS & Linux
DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )" && pwd )"
cd "$DIR"

echo "=========================================================="
echo " Starting Iread PC Thermal Print Service..."
echo "=========================================================="

if [ -f "../.venv/bin/python3" ]; then
    PYTHON_BIN="../.venv/bin/python3"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
else
    PYTHON_BIN="python"
fi

"$PYTHON_BIN" -m pip install -q -r requirements.txt 2>/dev/null
"$PYTHON_BIN" pc_print_service.py "$@"
