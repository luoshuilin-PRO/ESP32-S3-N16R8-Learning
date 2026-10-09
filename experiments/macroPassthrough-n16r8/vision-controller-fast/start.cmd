@echo off
setlocal
cd /d "%~dp0"
set "PYTHON=%USERPROFILE%\.cache\codex-runtimes\codex-primary-runtime\dependencies\python\python.exe"
if exist "%PYTHON%" (
  "%PYTHON%" main.py
) else (
  py -3 main.py
)
if errorlevel 1 pause
