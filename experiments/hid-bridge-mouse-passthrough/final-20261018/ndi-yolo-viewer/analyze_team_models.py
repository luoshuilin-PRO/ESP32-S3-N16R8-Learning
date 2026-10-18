"""Offline model comparison on user-labeled police/bandit screenshots; never opens COM."""
import ast
import hashlib
import json
from collections import Counter
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from detector import Detector


ROOT = Path(__file__).resolve().parent
SAMPLES = Path(r"C:\Users\Administrator\Desktop\新建文件夹 (3)")
OUTPUT = ROOT / "model-reports/team-comparison"


def draw_boxes(rgb, boxes, path):
    """Save a copy with model boxes and class IDs; input screenshot stays untouched."""
    image = Image.fromarray(rgb)
    canvas = ImageDraw.Draw(image)
    for box in boxes:
        x1, y1, x2, y2 = box["box"]
        color = (30, 255, 80) if box["class"] % 2 == 0 else (255, 230, 20)
        canvas.rectangle((x1, y1, x2, y2), outline=color, width=3)
        canvas.text((x1, max(0, y1-13)), f"{box['class']} {box['score']:.2f}", fill=color)
    path.parent.mkdir(parents=True, exist_ok=True)
    image.save(path)


def main():
    """Run every supported non-YOLOX model on whole and center-cropped images."""
    OUTPUT.mkdir(parents=True, exist_ok=True)
    records = []
    samples = [(folder.name, path) for folder in (SAMPLES / "警", SAMPLES / "匪")
               for path in sorted(folder.glob("*.bmp"))]
    if not samples:
        raise RuntimeError("没有警／匪 BMP 样本")
    for model in sorted((ROOT / "models").glob("*.onnx")):
        if model.name == "cs2-yolox-416.onnx":
            continue
        layout = "v5" if model.name == "cf.onnx" else "v8"
        metadata = __import__("onnxruntime").InferenceSession(
            str(model), providers=["CPUExecutionProvider"]).get_modelmeta().custom_metadata_map
        labels = ast.literal_eval(metadata["names"])
        count = len(labels)
        detector = Detector(str(model), "DmlExecutionProvider", layout, classes=count)
        model_record = {
            "model": model.name, "sha256": hashlib.sha256(model.read_bytes()).hexdigest(),
            "layout": layout, "input": [detector.w, detector.h], "labels": labels,
            "provider": detector.providers, "confidence": .25, "samples": [],
        }
        for group, path in samples:
            rgb = np.asarray(Image.open(path).convert("RGB"))
            height, width = rgb.shape[:2]
            if (width, height) != (1920, 1080):
                raise ValueError(f"意外截图尺寸：{path} {width}x{height}")
            x, y = (width - 640) // 2, (height - 640) // 2
            views = {"full": rgb, "center640": rgb[y:y+640, x:x+640]}
            row = {"group": group, "file": path.name, "views": {}}
            for view, pixels in views.items():
                boxes, inference, processing = detector.detect(pixels, .25, set())
                counts = dict(sorted(Counter(str(b["class"]) for b in boxes).items()))
                row["views"][view] = {"counts": counts, "boxes": boxes,
                                      "inference_ms": inference, "processing_ms": processing}
                draw_boxes(pixels, boxes, OUTPUT / model.stem / view / group / f"{path.stem}.png")
            model_record["samples"].append(row)
        records.append(model_record)
        print(json.dumps({"model": model.name, "labels": labels,
                          "police_full": [r["views"]["full"]["counts"] for r in model_record["samples"] if r["group"] == "警"],
                          "bandit_full": [r["views"]["full"]["counts"] for r in model_record["samples"] if r["group"] == "匪"]},
                         ensure_ascii=True))
    (OUTPUT / "results.json").write_text(json.dumps(records, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
