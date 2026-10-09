@echo off
cd /d "%~dp0"
if not exist "build\Release\vision_dxgi.exe" (
  echo Program not built. Run build.ps1 first.
  pause
  exit /b 1
)
echo Read-only DXGI detector. Switch to the game window now.
"build\Release\vision_dxgi.exe" --seconds 30
pause
