"""最新帧缓冲、预览坐标与 NDI 像素转换；不涉及任何输入设备。"""
import math
import threading
from dataclasses import dataclass
import numpy as np


@dataclass(frozen=True)
class Frame:
    sequence: int
    rgb: np.ndarray
    received: float
    stream: int


class Latest:
    """输入任意对象，仅保留最新一项；输出不可变帧引用，不建立待处理队列。"""
    def __init__(self):
        self.lock = threading.Lock()
        self.item = None

    def put(self, value):
        with self.lock:
            self.item = value

    def get(self):
        with self.lock:
            return self.item


def fit(width, height, canvas_w, canvas_h):
    """输入原图及画布尺寸，输出显示尺寸和居中偏移，保持宽高比。"""
    scale = min(canvas_w / width, canvas_h / height)
    w, h = max(1, round(width * scale)), max(1, round(height * scale))
    return w, h, (canvas_w - w) // 2, (canvas_h - h) // 2


def selection(start, end, image_size, canvas_size):
    """输入拖框两端与尺寸，输出原图 (x,y,w,h)，裁剪黑边，空区域返回 None。"""
    iw, ih = image_size
    w, h, ox, oy = fit(iw, ih, *canvas_size)
    x1, x2 = sorted((start[0], end[0]))
    y1, y2 = sorted((start[1], end[1]))
    x1, x2 = max(ox, x1), min(ox + w, x2)
    y1, y2 = max(oy, y1), min(oy + h, y2)
    if x2 <= x1 or y2 <= y1:
        return None
    left, top = math.floor((x1 - ox) * iw / w), math.floor((y1 - oy) * ih / h)
    right, bottom = math.ceil((x2 - ox) * iw / w), math.ceil((y2 - oy) * ih / h)
    return left, top, right - left, bottom - top


def crop_rect(roi, width, height):
    """输入保存区域及当前分辨率，输出合法裁剪框；超出范围拒绝而非偷偷缩放。"""
    if roi is None:
        return 0, 0, width, height
    x, y, w, h = map(int, roi)
    if x < 0 or y < 0 or w <= 0 or h <= 0 or x + w > width or y + h > height:
        raise ValueError("识别区域超出当前视频，请重新框选")
    return x, y, w, h


def ndi_rgb(data, width, height, stride, fourcc):
    """输入 NDI 四通道缓冲及真实行步长，输出独立 RGB 拷贝，拒绝未知格式。"""
    if width <= 0 or height <= 0 or stride < width * 4 or len(data) < height * stride:
        raise ValueError("NDI 分辨率、步长或缓冲长度非法")
    rows = np.frombuffer(data, dtype=np.uint8, count=height * stride).reshape(height, stride)
    pixels = rows[:, :width * 4].reshape(height, width, 4)
    if fourcc not in ("RGBX", "RGBA", "BGRX", "BGRA"):
        raise ValueError(f"不支持 NDI 像素格式 {fourcc}")
    rgb = pixels[:, :, :3]
    if fourcc.startswith("BGR"):
        rgb = rgb[:, :, ::-1]
    return np.ascontiguousarray(rgb).copy()
