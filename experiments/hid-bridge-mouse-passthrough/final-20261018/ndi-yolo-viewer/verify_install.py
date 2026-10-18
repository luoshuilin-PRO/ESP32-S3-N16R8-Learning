"""Read-only relocation and dependency check; never scans NDI or opens COM."""
import importlib
import json
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parent
report = {
    "python": sys.version,
    "x64": struct.calcsize("P") == 8,
    "imports": {},
    "models": {},
    "providers": [],
    "hardware_output": False,
}
for name in ("tkinter", "numpy", "PIL", "cv2", "serial", "cyndilib", "onnxruntime", "esptool", "hid_bridge.controller", "output_control", "ndi_input"):
    try:
        importlib.import_module(name)
        report["imports"][name] = "OK"
    except Exception as error:
        report["imports"][name] = str(error)

if report["imports"].get("onnxruntime") == "OK":
    import onnxruntime as ort
    report["providers"] = ort.get_available_providers()
    try:
        session = ort.InferenceSession(str(root / "models" / "cf.onnx"), providers=["CPUExecutionProvider"])
        report["models"]["cf.onnx"] = {"input": session.get_inputs()[0].shape, "output": session.get_outputs()[0].shape}
    except Exception as error:
        report["models"]["cf.onnx"] = str(error)

if report["imports"].get("esptool") == "OK":
    import esptool
    report["esptool_version"] = esptool.__version__
    try:
        sys.path.insert(0, str(root / "firmware-tool"))
        from flasher import firmware_plan
        report["firmware"] = "OK" if len(firmware_plan()) == 3 else "unexpected segment count"
    except Exception as error:
        report["firmware"] = str(error)

for path in sorted((root / "profiles").glob("*.json")):
    try:
        value = json.loads(path.read_text(encoding="utf-8"))["model"]
        model = Path(value)
        if not model.is_absolute():
            model = root / model
        if not model.is_file():
            report["models"][f"profile:{path.name}"] = f"missing: {value}"
    except Exception as error:
        report["models"][f"profile:{path.name}"] = str(error)

(root / "install-report.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
print(json.dumps(report, ensure_ascii=False, indent=2))
ok = report["x64"] and all(x == "OK" for x in report["imports"].values())
ok &= isinstance(report["models"].get("cf.onnx"), dict)
ok &= report.get("esptool_version") == "5.1.0" and report.get("firmware") == "OK"
ok &= not any(key.startswith("profile:") for key in report["models"])
raise SystemExit(0 if ok else 1)
