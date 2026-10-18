"""Read-only CPU compatibility check against the existing viewer Detector."""
import json
import sys
import gc
from pathlib import Path

sys.dont_write_bytecode = True
ROOT = Path(__file__).resolve().parent
from import_manager import VIEWER
sys.path.insert(0, str(VIEWER))
from detector import Detector


def main():
    models = json.loads((ROOT / "model-catalog.json").read_text(encoding="utf-8"))["models"]
    results = []
    for item in models:
        result = {"path": item["path"], "sha256": item["sha256"], "layout": item["layout"]}
        if item["layout"] not in ("v5", "v8", "xyxy", "yolox"):
            result["status"] = "not-tested-unsupported-or-ambiguous"
        else:
            try:
                detector = Detector(str(ROOT / item["path"]), "CPUExecutionProvider", item["layout"], classes=item["classes"])
                result.update(status="CPU-load-zero-inference-parser-PASS", size=[detector.w, detector.h])
                del detector
                gc.collect()
            except Exception as exc:
                result.update(status="FAIL", error=f"{type(exc).__name__}: {exc}")
        results.append(result)
        print(len(results), result["status"], flush=True)
        (ROOT / "compatibility-audit.json").write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")


if __name__ == "__main__":
    main()
