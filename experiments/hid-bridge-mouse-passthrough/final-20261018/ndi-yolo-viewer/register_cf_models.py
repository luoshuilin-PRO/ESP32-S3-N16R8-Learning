"""Inventory local ONNX artifacts and add missing models/profiles by SHA256."""
import ast
import hashlib
import json
import shutil
from pathlib import Path

import numpy as np
import onnx
from detector import Detector

ROOT = Path(__file__).resolve().parent
SOURCE = Path(r"C:\123pan\Downloads\模型区\cf模型")


def digest(path):
    """Return the file SHA256 used for deduplication and copy verification."""
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    """Inspect source models, copy absent hashes, create missing profiles, save evidence."""
    existing = {digest(p): p for p in (ROOT / "models").glob("*.onnx")}
    base = json.loads((ROOT / "profiles/CF480-YOLOv8.json").read_text(encoding="utf-8"))
    rows = []
    for source in sorted(SOURCE.glob("*.onnx")):
        sha = digest(source)
        graph = onnx.load(str(source))
        onnx.checker.check_model(graph)
        meta = {x.key: x.value for x in graph.metadata_props}
        labels = ast.literal_eval(meta["names"])
        shape = [d.dim_value for d in graph.graph.input[0].type.tensor_type.shape.dim]
        nodes = [n.name for n in graph.graph.node]
        if "YOLO11" in meta.get("description", "") and any("attn" in n for n in nodes):
            family = "YOLO11"
            evidence = "YOLO11 metadata and attention graph"
        elif any("/model.22/dfl/" in n for n in nodes) and not any("attn" in n for n in nodes):
            family = "YOLOv8"
            evidence = "C2f/SPPF/DFL graph matches YOLOv8 topology"
        else:
            family, evidence = "unknown", "requires further graph analysis"
        suffix = f"{family}-{shape[2]}-{len(labels)}class"
        copied = sha not in existing
        if copied:
            destination = ROOT / "models" / f"cf-{suffix}.onnx"
            if destination.exists():
                raise FileExistsError(destination)
            shutil.copy2(source, destination)
            assert digest(destination) == sha
            existing[sha] = destination
            profile = dict(base)
            profile["output_parameters"] = dict(base["output_parameters"])
            profile.update(model=destination.relative_to(ROOT).as_posix(), classes=len(labels), red_only=False)
            profile["output_parameters"].update(head_class=0, teammate_class=-1)
            profile_path = ROOT / "profiles" / f"CF-{suffix}.json"
            if profile_path.exists():
                raise FileExistsError(profile_path)
            profile_path.write_text(json.dumps(profile, ensure_ascii=False, indent=2), encoding="utf-8")
        destination = existing[sha]
        detector = Detector(str(destination), "DmlExecutionProvider", "v8", classes=len(labels))
        _, infer_ms, total_ms = detector.detect(np.zeros((640,640,3),np.uint8), .25, set())
        rows.append(dict(source=str(source), model=str(destination), sha256=sha, copied=copied,
                         family=family, family_evidence=evidence, input=shape,
                         output=detector.session.get_outputs()[0].shape, labels=labels,
                         metadata=meta, providers=detector.providers,
                         smoke_infer_ms=infer_ms, smoke_total_ms=total_ms,
                         semantic_accuracy_verified=False))
    output = ROOT / "model-reports/cf-model-inventory.json"
    output.write_text(json.dumps(rows, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps([dict(model=Path(x["model"]).name, copied=x["copied"], family=x["family"],
                           labels=x["labels"], input=x["input"]) for x in rows], ensure_ascii=True, indent=2))


if __name__ == "__main__":
    main()
