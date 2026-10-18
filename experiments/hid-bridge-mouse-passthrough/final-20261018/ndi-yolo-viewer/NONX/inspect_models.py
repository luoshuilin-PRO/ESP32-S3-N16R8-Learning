"""Read ONNX metadata and graph signatures without running model code."""
import ast
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

import onnx
import numpy as np
import onnxruntime as ort


ROOT = Path(__file__).resolve().parent


def dims(value):
    return [d.dim_value if d.HasField("dim_value") else d.dim_param or None
            for d in value.type.tensor_type.shape.dim]


def labels_from_meta(meta):
    raw = meta.get("names") or meta.get("classes")
    if not raw:
        return None
    try:
        value = ast.literal_eval(raw)
        if isinstance(value, dict):
            return {str(k): str(v) for k, v in value.items()}
        if isinstance(value, (list, tuple)):
            return {str(i): str(v) for i, v in enumerate(value)}
    except (ValueError, SyntaxError):
        pass
    return None


def classify(meta, producer, nodes, path):
    strong = " ".join([producer, meta.get("description", "").split(" trained on ")[0], meta.get("model_type", ""),
                       meta.get("version", "")]).lower()
    names = " ".join(n.name.lower() for n in nodes)
    for pattern, family in ((r"\byolo(?:v)?26[nsmlx]?\b", "YOLO26"),
                            (r"\byolo(?:v)?12[nsmlx]?\b", "YOLOv12"),
                            (r"\byolo(?:v)?11[nsmlx]?\b", "YOLO11"),
                            (r"\byolo(?:v)?8[nsmlx]?\b", "YOLOv8"),
                            (r"\byolo(?:v)?5[nsmlx]?\b", "YOLOv5"),
                            (r"\byolox\b", "YOLOX")):
        if re.search(pattern, strong):
            return family, "ONNX metadata/producer", "high"
    if "yolov8" in meta.get("description", "").lower():
        return "YOLOv8 candidate", "training path in metadata", "medium"
    weak = path.name.lower()
    for pattern, family in ((r"(?:yolo)?v?26[nsmlx]?(?=[_.\s-]|$)", "YOLO26 candidate"),
                            (r"(?:yolo)?v?12[nsmlx]?(?=[_.\s-]|$)", "YOLOv12 candidate"),
                            (r"(?:yolo)?v?11[nsmlx]?(?=[_.\s-]|$)", "YOLO11 candidate"),
                            (r"(?:yolo)?v?8[nsmlx]?(?=[_.\s-]|$)", "YOLOv8 candidate"),
                            (r"(?:yolo)?v?5[nsmlx]?(?=[_.\s-]|$)", "YOLOv5 candidate"),
                            (r"yolox", "YOLOX candidate")):
        if re.search(pattern, weak):
            return family, "filename only", "low"
    return "unknown", "no version signature", "none"


def layout_from_shape(shape, count):
    if len(shape) != 3 or count is None:
        return "unsupported/uncertain"
    if shape[2] == 5 + count and shape[2] == 6:
        return "ambiguous v5/xyxy"
    if shape[2] == 5 + count:
        return "v5"
    if shape[1] == 4 + count:
        return "v8"
    return "unsupported/uncertain"


def inspect(path):
    with path.open("rb") as source:
        checksum = hashlib.file_digest(source, "sha256").hexdigest()
    record = {"path": str(path.relative_to(ROOT)).replace("\\", "/"),
              "bytes": path.stat().st_size,
              "sha256": checksum}
    try:
        model = onnx.load(str(path), load_external_data=False)
        graph = model.graph
        meta = {p.key: p.value for p in model.metadata_props}
        labels = labels_from_meta(meta)
        inputs = [{"name": x.name, "shape": dims(x), "type": x.type.tensor_type.elem_type} for x in graph.input]
        outputs = [{"name": x.name, "shape": dims(x), "type": x.type.tensor_type.elem_type} for x in graph.output]
        family, evidence, confidence = classify(meta, model.producer_name, graph.node, path)
        weights = " ".join(x.name for x in graph.initializer)
        yolox = all(name in weights for name in ("head.cls_preds", "head.reg_preds", "head.obj_preds"))
        if yolox:
            family, evidence, confidence = "YOLOX", "cls/reg/obj head initializer names", "high"
        count = len(labels) if labels else None
        shape = outputs[0]["shape"] if len(outputs) == 1 else []
        if count is None and len(shape) == 3:
            if isinstance(shape[1], int) and 5 <= shape[1] <= 1004 and shape[2] != 6:
                count = shape[1] - 4
            elif isinstance(shape[2], int) and 6 <= shape[2] <= 1005:
                count = shape[2] - 5
        layout = "xyxy" if meta.get("end2end") == "True" and len(shape) == 3 and shape[2] == 6 else layout_from_shape(shape, count)
        if yolox:
            layout = "yolox"
        runtime_shape = None
        if (layout == "unsupported/uncertain" and count is not None and len(inputs) == 1 and
                len(outputs) == 1 and all(not isinstance(d, int) for d in shape)):
            fixed = inputs[0]["shape"]
            if len(fixed) == 4 and all(isinstance(d, int) and 1 <= d <= 4096 for d in fixed) and inputs[0]["type"] == 1:
                session = ort.InferenceSession(str(path), providers=["CPUExecutionProvider"])
                runtime_shape = list(session.run(None, {inputs[0]["name"]: np.zeros(fixed, np.float32)})[0].shape)
                layout = layout_from_shape(runtime_shape, count)
        ops = Counter(n.op_type for n in graph.node)
        record.update(producer=model.producer_name, producer_version=model.producer_version,
                      ir_version=model.ir_version, opsets=[{"domain": o.domain, "version": o.version} for o in model.opset_import],
                      metadata=meta, labels=labels, inputs=inputs, outputs=outputs,
                      family=family, family_evidence=evidence, family_confidence=confidence,
                      classes=count, layout=layout, runtime_shape=runtime_shape, op_counts=dict(ops),
                      node_names=[n.name for n in graph.node[:12]])
    except Exception as exc:
        record["error"] = f"{type(exc).__name__}: {exc}"
    return record


def main():
    records = [inspect(path) for path in sorted(ROOT.rglob("*.onnx"))]
    target = ROOT / "model-catalog.json"
    target.write_text(json.dumps({"schema": 1, "models": records}, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"{len(records)} models -> {target}")
    for item in records:
        print(item["path"], item.get("family", "ERROR"), item.get("layout", ""), item.get("classes", ""))


if __name__ == "__main__":
    main()
