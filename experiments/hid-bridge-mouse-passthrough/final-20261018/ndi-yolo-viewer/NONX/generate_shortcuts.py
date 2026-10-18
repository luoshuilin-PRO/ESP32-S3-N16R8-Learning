"""Generate two Windows launchers for each folder that directly contains ONNX models."""
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    catalog = json.loads((ROOT / "model-catalog.json").read_text(encoding="utf-8"))
    folders = sorted({Path(item["path"]).parent for item in catalog["models"]})
    for folder in folders:
        climb = "\\".join(".." for _ in folder.parts)
        group = str(folder).replace("/", "\\")
        for action, filename in (("import", "一键导入.cmd"), ("remove", "一键取消导入.cmd")):
            script = ("@echo off\r\nchcp 65001 >nul\r\nsetlocal\r\n"
                      f'for %%I in ("%~dp0{climb}") do set "NONX_ROOT=%%~fI"\r\n'
                      'set "VIEWER=%NONX_ROOT%\\.."\r\n'
                      'if not exist "%VIEWER%\\detector.py" set "VIEWER=%NONX_ROOT%\\..\\ndi-yolo-viewer"\r\n'
                      'set "PY=%VIEWER%\\.venv\\Scripts\\python.exe"\r\n'
                      'if not exist "%PY%" (\r\n'
                      '  echo Project Python not found. Run ndi-yolo-viewer\\install.cmd first.\r\n'
                      '  pause\r\n  exit /b 1\r\n)\r\n'
                      'set "EXTRA="\r\n'
                      'if "%NONX_DRY_RUN%"=="1" set "EXTRA=--dry-run"\r\n'
                      f'"%PY%" "%NONX_ROOT%\\import_manager.py" {action} --group "{group}" %EXTRA%\r\n'
                      'set "RESULT=%ERRORLEVEL%"\r\n'
                      'if "%NONX_DRY_RUN%"=="1" exit /b %RESULT%\r\n'
                      'pause\r\nexit /b %RESULT%\r\n')
            target = ROOT / folder / filename
            target.write_bytes(script.encode("utf-8"))
    print(f"Created {2 * len(folders)} launchers in {len(folders)} game folders.")


if __name__ == "__main__":
    main()
