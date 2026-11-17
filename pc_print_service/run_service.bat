@echo off
REM Iread PC Thermal Print Service Launcher for Windows
echo ==========================================================
echo  Starting Iread PC Thermal Print Service on Windows...
echo ==========================================================
cd /d "%~dp0"
python -m pip install -q -r requirements.txt
python pc_print_service.py %*
pause
