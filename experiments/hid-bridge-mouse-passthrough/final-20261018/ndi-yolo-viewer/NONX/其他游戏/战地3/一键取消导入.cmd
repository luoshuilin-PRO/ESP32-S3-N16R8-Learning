@echo off
chcp 65001 >nul
setlocal
for %%I in ("%~dp0..\..") do set "NONX_ROOT=%%~fI"
set "VIEWER=%NONX_ROOT%\.."
if not exist "%VIEWER%\detector.py" set "VIEWER=%NONX_ROOT%\..\ndi-yolo-viewer"
set "PY=%VIEWER%\.venv\Scripts\python.exe"
if not exist "%PY%" (
  echo Project Python not found. Run ndi-yolo-viewer\install.cmd first.
  pause
  exit /b 1
)
set "EXTRA="
if "%NONX_DRY_RUN%"=="1" set "EXTRA=--dry-run"
"%PY%" "%NONX_ROOT%\import_manager.py" remove --group "其他游戏\战地3" %EXTRA%
set "RESULT=%ERRORLEVEL%"
if "%NONX_DRY_RUN%"=="1" exit /b %RESULT%
pause
exit /b %RESULT%
