"""Inspect the local CF480 model and saved frames without hardware or network input."""
import hashlib
import json
from collections import Counter
from pathlib import Path
import statistics

import numpy as np
import onnx
from PIL import Image, ImageDraw
from detector import Detector


def main():
    """Read the copied model and local PNGs; save structural and inference evidence."""
    root = Path(__file__).resolve().parent
    path = root / "models/cf-enemy-v8-480.onnx"
    out = root / "model-reports/cf480"
    out.mkdir(parents=True, exist_ok=True)
    model = onnx.load(str(path))
    onnx.checker.check_model(model)
    detector = Detector(str(path), "DmlExecutionProvider", "v8", classes=1)
    report = {
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
        "bytes": path.stat().st_size,
        "metadata": dict(detector.session.get_modelmeta().custom_metadata_map),
        "inputs": [[x.name, x.shape, x.type] for x in detector.session.get_inputs()],
        "outputs": [[x.name, x.shape, x.type] for x in detector.session.get_outputs()],
        "opset": [[x.domain, x.version] for x in model.opset_import],
        "operators": dict(Counter(x.op_type for x in model.graph.node)),
        "first_conv_shapes": [[x.name, list(x.dims)] for x in model.graph.initializer
                              if x.name in ("model.0.conv.weight", "model.1.conv.weight")],
        "providers": detector.providers,
        "semantic_accuracy_verified": False,
        "samples": [],
    }
    for sample in sorted((root / "samples").glob("*-frame.png")):
        rgb = np.array(Image.open(sample).convert("RGB"))
        runs = [detector.detect(rgb, .25, set()) for _ in range(3)]
        boxes = runs[-1][0]
        annotated = Image.fromarray(rgb)
        draw = ImageDraw.Draw(annotated)
        for box in boxes:
            draw.rectangle(box["box"], outline="lime", width=2)
            draw.text(box["box"][:2], f"st {box['score']:.2f}", fill="yellow")
        annotated.save(out / sample.name)
        report["samples"].append({"file": sample.name, "size": list(annotated.size),
                                  "boxes": boxes,
                                  "inference_median_ms": statistics.median(x[1] for x in runs)})
    (out / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"providers": report["providers"], "first_conv_shapes": report["first_conv_shapes"],
                      "samples": [{"file": s["file"], "detections": len(s["boxes"]),
                                   "inference_ms": s["inference_median_ms"]} for s in report["samples"]]}, indent=2))


if __name__ == "__main__":
    main()
