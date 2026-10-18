# CS2敌我.onnx 接入记录

来源：`C:\123pan\Downloads\模型区\cs\CS2敌我.onnx`。复制到 `models/cs2-yolox-416.onnx`，SHA256 两份一致：`B23518B2AE35454EA1459D8B958B711CB314DCEF00BD8FD9F45B9488B52C0703`。原文件 20,132,614 字节。

## 模型类型和参数

这个模型属于 **YOLOX**，不是 YOLOv5、YOLOv8、YOLO11 或 YOLOv12。ONNX 未携带类别和版本元数据，但保留了 `head.cls_preds`、`head.reg_preds`、`head.obj_preds` 三组 YOLOX 检测头权重，以及 YOLOX 风格的未解码预测。参考原项目的 [YOLOX 检测头](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/yolox/models/yolo_head.py) 与 [ONNX 推理示例](https://github.com/Megvii-BaseDetection/YOLOX/blob/main/demo/ONNXRuntime/onnx_inference.py)。具体 YOLOX 规模、训练来源和四类标签无法仅从这份导出文件确认。

| 参数 | 实测 |
|---|---|
| 输入 | `images [1,3,416,416]` FP32 |
| 输出 | `[1,3549,9]`，原始 xywh、objectness、4 类分数 |
| 多尺度网格 | `52² + 26² + 13² = 3549`，步长 8/16/32 |
| ONNX | IR 7，opset 12，producer `onnx.utils.extract_model` |
| 类别数 | 4，文件无类别名称 |
| 后处理 | YOLOX 网格与步长解码、objectness×类别分数、NMS |

预处理按 YOLOX 官方流程使用 BGR、左上对齐填充值 114、FP32 原始 0～255，项目另设 `yolox` 输出布局；直接选 `v5` 虽然输出宽度一样，却会把未解码的原始值当作像素坐标，框位置错误。输入仍可接 640×640 OBS 视频，程序会缩放到 416×416 并映射回原尺寸。

## 手动加载

`CS2-YOLOX-416` 游戏配置已移除。模型文件仍在 `models/cs2-yolox-416.onnx`；如需只读查看，可在界面手动选择该模型，设置布局 `yolox`、类别数 `4`、置信度 `0.25` 后加载。

在已有的 CrossFire 画面样本中，类别 0 框住人物身体、类别 1 框住头部。这是跨游戏样本观察，尚不能证明 CS2 的敌我编号，也不能证明类别 2/3 的含义。先在 CS2 的队友、敌人、并排及遮挡画面上只读检查 0～3 类，再考虑设置目标和队友类别。现有红名区域仍是 CF 640×640 坐标 `(268,377,90,24)`，尚未按 CS2 UI 校准。

## 验证

- ONNX checker 通过；副本哈希一致。
- DirectML 加载和真实推理成功，已有 CF 样本 3/6 张检出类别 0、1；其余样本零检测属于跨游戏样本结果。
- 关键样本标注图显示类别 0 身体、类别 1 头部；类别 2/3 未在这些样本检出。
- 当前未验证 CS2 游戏内分类准确率、敌我语义、鼠标输出或端到端延迟。

离线检查脚本 `check_cs2_model.py`，报告及标注图见 `model-reports/cs2-yolox-416/`。
