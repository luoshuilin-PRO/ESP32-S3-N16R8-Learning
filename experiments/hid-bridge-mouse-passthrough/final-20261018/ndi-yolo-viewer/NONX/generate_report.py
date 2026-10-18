"""Summarize model origins and viewer compatibility from the catalog."""
import json
from collections import Counter
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main():
    models = json.loads((ROOT / "model-catalog.json").read_text(encoding="utf-8"))["models"]
    families = Counter((m.get("family", "invalid"), m.get("family_confidence", "none")) for m in models)
    compatible = sum(m.get("layout") in ("v5", "v8", "xyxy", "yolox") for m in models)
    lines = ["# NONX 模型检查结果", "", f"共 {len(models)} 个模型；静态布局可建立项目配置 {compatible} 个，其余 {len(models)-compatible} 个仅可复制文件，需进一步适配或验证。", "",
             "版本证据优先取 ONNX 内的 description。`unknown` 表示没有足够证据确认 YOLO 代际；`candidate` 仅凭文件名或路径猜测。输出布局 `v8` 只说明张量为 `[1,4+C,N]`，不能证明模型是 YOLOv8。", "",
             "| 版本判断 | 数量 |", "| --- | ---: |"]
    lines += [f"| {name} ({confidence}) | {count} |" for (name, confidence), count in sorted(families.items())]
    lines += ["", "| 游戏目录 / 模型 | 判断 | 证据 | 输入 | 输出 | 类别 | 项目布局 |", "| --- | --- | --- | --- | --- | ---: | --- |"]
    for item in models:
        inputs = item.get("inputs") or []
        outputs = item.get("outputs") or []
        inp = str(inputs[0]["shape"]) if inputs else "?"
        out = str(outputs[0]["shape"]) if outputs else "?"
        path = item["path"].replace("|", "\\|")
        lines.append(f"| {path} | {item.get('family','ERROR')} | {item.get('family_evidence','parse error')} | {inp} | {out} | {item.get('classes','?')} | {item.get('layout','-')} |")
    lines += ["", "完整 SHA-256、元数据、类别标签和算子计数见 `model-catalog.json`。这份检查不等于游戏内准确率测试，也不证明某类别是敌人或头部。"]
    (ROOT / "模型清单.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    print("Wrote 模型清单.md")


if __name__ == "__main__":
    main()
