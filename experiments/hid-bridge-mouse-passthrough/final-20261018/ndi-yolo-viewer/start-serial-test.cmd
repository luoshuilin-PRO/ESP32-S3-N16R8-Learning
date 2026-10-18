@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Run install.cmd first.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" "hid-bridge-python\main.py"
if errorlevel 1 pause
