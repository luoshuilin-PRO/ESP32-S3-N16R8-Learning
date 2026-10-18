@echo off
cd /d "%~dp0"
if not exist ".venv\Scripts\python.exe" (
    echo Missing local Python environment. See README.md.
    pause
    exit /b 1
)
".venv\Scripts\python.exe" main.py --profile CF480-YOLOv8
if errorlevel 1 pause
