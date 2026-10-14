"""受限 ONNX YOLO 检测器：v5/v8 原始输出或已做 NMS 的 xyxy 六列。"""
import ast
import time
import threading
import cv2
import numpy as np
import onnxruntime as ort


def letterbox(rgb, width, height, dtype=np.float32):
    """输入 RGB 图和模型尺寸，输出 NCHW float32 及比例/偏移。"""
    h, w = rgb.shape[:2]
    ratio = min(width / w, height / h)
    nw, nh = max(1, round(w * ratio)), max(1, round(h * ratio))
    left, top = (width - nw) // 2, (height - nh) // 2
    padded = np.full((height, width, 3), 114, np.uint8)
    padded[top:top + nh, left:left + nw] = cv2.resize(rgb, (nw, nh))
    tensor = np.ascontiguousarray(padded.transpose(2, 0, 1)[None], dtype=dtype)
    tensor /= dtype(255)
    return tensor, (ratio, left, top)


def resolve_layout(shape, classes):
    """输入实际输出尺寸和类别数；输出唯一匹配布局，歧义要求手动选择。"""
    if len(shape) != 3 or shape[0] != 1:
        raise ValueError(f"不支持的检测输出：{shape}")
    candidates = []
    if shape[2] == 5 + classes:
        candidates.append("v5")
    if shape[1] == 4 + classes:
        candidates.append("v8")
    # 六列可能是单类 v5 或已做 NMS 的 xyxy，形状不足以确定语义。
    if shape[2] == 6:
        candidates.append("xyxy")
    if len(candidates) != 1:
        raise ValueError(f"输出 {shape} 布局不明确，请手动选择 v5/v8/xyxy")
    return candidates[0]


def parse_output(output, layout, classes, confidence, iou, transform, image_size, allowed):
    """输入模型数组与明确布局，输出 ROI 内 xyxy/score/class；按类别做 NMS。"""
    a = np.asarray(output)
    if a.ndim != 3 or a.shape[0] != 1:
        raise ValueError(f"仅支持 batch=1 单输出检测张量，实际 {a.shape}")
    a = a[0]
    if layout == "v8":
        if a.shape[0] != 4 + classes:
            raise ValueError("v8 需要 [1,4+类别数,N]")
        a = a.T
    elif layout == "v5":
        if a.shape[1] != 5 + classes:
            raise ValueError("v5 需要 [1,N,5+类别数]")
    elif layout == "xyxy":
        if a.shape[1] != 6:
            raise ValueError("xyxy 需要 [1,N,6]，像素坐标、置信度、类别")
    else:
        raise ValueError("请选择输出布局")
    a = a[np.isfinite(a).all(axis=1)]
    if not len(a):
        return []
    if layout == "xyxy":
        boxes, scores, ids = a[:, :4].copy(), a[:, 4], a[:, 5].astype(int)
    else:
        offset = 5 if layout == "v5" else 4
        ids = np.argmax(a[:, offset:], axis=1)
        scores = a[np.arange(len(a)), offset + ids]
        if layout == "v5":
            scores = scores * a[:, 4]
        boxes = np.column_stack((a[:, 0] - a[:, 2] / 2, a[:, 1] - a[:, 3] / 2,
                                 a[:, 0] + a[:, 2] / 2, a[:, 1] + a[:, 3] / 2))
    mask = (scores >= confidence) & (scores <= 1) & (ids >= 0) & (ids < classes)
    if allowed:
        mask &= np.isin(ids, list(allowed))
    boxes, scores, ids = boxes[mask], scores[mask], ids[mask]
    scale, left, top = transform
    boxes[:, [0, 2]] = (boxes[:, [0, 2]] - left) / scale
    boxes[:, [1, 3]] = (boxes[:, [1, 3]] - top) / scale
    boxes[:, [0, 2]] = boxes[:, [0, 2]].clip(0, image_size[0])
    boxes[:, [1, 3]] = boxes[:, [1, 3]].clip(0, image_size[1])
    result = []
    for cls in np.unique(ids):
        indices = np.flatnonzero(ids == cls)
        valid = (boxes[indices, 2] > boxes[indices, 0]) & (boxes[indices, 3] > boxes[indices, 1])
        indices = indices[valid]
        if not len(indices):
            continue
        rects = boxes[indices].copy()
        rects[:, 2:] -= rects[:, :2]
        keep = cv2.dnn.NMSBoxes(rects.tolist(), scores[indices].tolist(), confidence, iou)
        for k in np.asarray(keep).reshape(-1):
            j = indices[int(k)]
            result.append({"box": boxes[j].tolist(), "score": float(scores[j]), "class": int(ids[j])})
    return sorted(result, key=lambda item: item["score"], reverse=True)[:100]


class Detector:
    def __init__(self, path, provider, layout, size=320, classes=2):
        """输入模型路径和执行配置，创建会话并核对 I/O；不加载未知自定义代码。"""
        options = ort.SessionOptions()
        options.enable_mem_pattern = False
        options.execution_mode = ort.ExecutionMode.ORT_SEQUENTIAL
        available = ort.get_available_providers()
        if provider not in available:
            raise RuntimeError(f"执行提供者未安装：{provider}，可用 {available}")
        self.session = ort.InferenceSession(path, sess_options=options, providers=[provider, "CPUExecutionProvider"] if provider != "CPUExecutionProvider" else [provider])
        self.run_lock = threading.Lock()
        self.providers = self.session.get_providers()
        if provider not in self.providers:
            raise RuntimeError(f"请求的提供者未启用，实际 {self.providers}")
        inputs, outputs = self.session.get_inputs(), self.session.get_outputs()
        if len(inputs) != 1 or len(outputs) != 1 or inputs[0].type not in ("tensor(float)", "tensor(float16)"):
            raise ValueError("支持单输入 FP32/FP16、单输出 ONNX 检测模型")
        self.dtype = np.float16 if inputs[0].type == "tensor(float16)" else np.float32
        shape = inputs[0].shape
        if len(shape) != 4 or shape[1] != 3 or isinstance(shape[0], int) and shape[0] != 1:
            raise ValueError(f"模型需要 batch=1 NCHW RGB，实际 {shape}")
        self.h = shape[2] if isinstance(shape[2], int) else size
        self.w = shape[3] if isinstance(shape[3], int) else size
        if not 16 <= self.w <= 4096 or not 16 <= self.h <= 4096:
            raise ValueError("模型输入尺寸非法")
        self.name = inputs[0].name
        self.layout, self.classes = layout, classes
        self.labels = {}
        metadata = self.session.get_modelmeta().custom_metadata_map
        if "names" in metadata:
            names = ast.literal_eval(metadata["names"])
            self.labels = {int(k): str(v) for k, v in names.items()} if isinstance(names, dict) else dict(enumerate(names))
            if len(self.labels) != classes:
                raise ValueError(f"类别数设置 {classes} 与模型元数据 {len(self.labels)} 不一致")
        dummy = np.zeros((1, 3, self.h, self.w), self.dtype)
        output = self.session.run(None, {self.name: dummy})[0]
        if layout == "auto":
            self.layout = resolve_layout(output.shape, classes)
        parse_output(output, self.layout, classes, 0.25, 0.45, (1, 0, 0), (self.w, self.h), set())

    def detect(self, rgb, confidence, allowed):
        """输入 RGB ROI、置信度和类别集合，输出检测列表及本机处理/推理耗时。"""
        start = time.perf_counter()
        tensor, transform = letterbox(rgb, self.w, self.h, self.dtype)
        before = time.perf_counter()
        with self.run_lock:
            output = self.session.run(None, {self.name: tensor})[0]
        after = time.perf_counter()
        result = parse_output(output, self.layout, self.classes, confidence, 0.45, transform,
                              (rgb.shape[1], rgb.shape[0]), allowed)
        return result, (after - before) * 1000, (time.perf_counter() - start) * 1000
