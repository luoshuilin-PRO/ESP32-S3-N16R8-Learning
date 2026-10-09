@echo off
cd /d "%~dp0"
if not exist "build\Release\vision_dxgi.exe" (
  echo Program not built. Run build.ps1 first.
  pause
  exit /b 1
)
echo This mode sends VC1 ACTIVE to COM4 while red pixels are detected.
echo B native USB must be connected to the computer. Press Ctrl+C to stop.
choice /C YN /M "Run 30-second click test"
if errorlevel 2 exit /b 0
echo Switch to the game window now. Starting in 3 seconds...
timeout /t 3 /nobreak >nul
"build\Release\vision_dxgi.exe" --click --port COM4 --seconds 30
pause
