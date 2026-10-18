"""Inspect the imported YOLOX model on saved frames; does not open NDI or COM."""
import hashlib
import json
from pathlib import Path

import numpy as np
import onnx
from PIL import Image, ImageDraw
from detector import Detector


def main():
    """Write model metadata and annotated PNGs for offline review."""
    root = Path(__file__).resolve().parent
    model = root / "models/cs2-yolox-416.onnx"
    output = root / "model-reports/cs2-yolox-416"
    output.mkdir(parents=True, exist_ok=True)
    graph = onnx.load(str(model))
    onnx.checker.check_model(graph)
    detector = Detector(str(model), "DmlExecutionProvider", "yolox", classes=4)
    report = {"model": str(model), "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
              "producer": graph.producer_name, "metadata": dict(detector.session.get_modelmeta().custom_metadata_map),
              "input": [detector.h, detector.w], "output": detector.session.get_outputs()[0].shape,
              "layout": "YOLOX raw [xywh,obj,4 class scores]", "providers": detector.providers,
              "class_names_verified": False, "samples": []}
    for path in sorted((root / "samples").glob("*-frame.png")):
        rgb = np.asarray(Image.open(path).convert("RGB"))
        boxes, infer_ms, total_ms = detector.detect(rgb, .25, set())
        image = Image.fromarray(rgb)
        draw = ImageDraw.Draw(image)
        for box in boxes:
            draw.rectangle(box["box"], outline="lime", width=2)
            draw.text(box["box"][:2], f"{box['class']} {box['score']:.2f}", fill="yellow")
        image.save(output / path.name)
        report["samples"].append({"file": path.name, "boxes": boxes,
                                  "inference_ms": infer_ms, "processing_ms": total_ms})
    (output / "analysis.json").write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([{"sample": x["file"], "classes": [b["class"] for b in x["boxes"]]}
                      for x in report["samples"]], ensure_ascii=False))


if __name__ == "__main__":
    main()
