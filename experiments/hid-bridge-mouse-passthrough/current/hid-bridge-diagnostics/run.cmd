@echo off
cd /d "%~dp0"
set "PYTHON_EXE=.venv\Scripts\python.exe"
if exist "%PYTHON_EXE%" (
    "%PYTHON_EXE%" main.py
) else (
    py -3 main.py
)
if errorlevel 1 pause
