"""Offline model and red-name smoke test; no network, COM, or HID access."""
import json
from pathlib import Path

import numpy as np
from PIL import Image

from detector import Detector
from red_detector import detect_red

root = Path(__file__).resolve().parent
cases = (
    ("1791869812607756200-frame.png", True),
    ("1791870144176117900-frame.png", False),
)
detector = Detector(str(root / "models" / "cf.onnx"), "CPUExecutionProvider", "v5", classes=2)
report = {"provider": detector.providers, "samples": [], "hardware_output": False}
for filename, expected_red in cases:
    image = np.asarray(Image.open(root / "samples" / filename).convert("RGB"))
    boxes, infer_ms, processing_ms = detector.detect(image, .25, set())
    red = detect_red(image)
    report["samples"].append({"name": filename, "boxes": len(boxes), "red_hit": red["hit"],
                              "expected_red_hit": expected_red, "infer_ms": infer_ms,
                              "processing_ms": processing_ms})
print(json.dumps(report, ensure_ascii=False, indent=2))
raise SystemExit(0 if all(item["red_hit"] == item["expected_red_hit"] for item in report["samples"]) else 1)
