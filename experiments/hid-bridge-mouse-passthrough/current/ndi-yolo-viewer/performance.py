"""有界本地耗时统计，不代表游戏到 HID 的端到端耗时。"""
from collections import deque
import numpy as np


class Timings:
    def __init__(self, capacity=240):
        self.values = deque(maxlen=capacity)

    def add(self, queue_ms, processing_ms):
        """输入本地等待和处理毫秒数，保存一条新帧测量。"""
        self.values.append((queue_ms, processing_ms))

    def summary(self):
        """输出窗口内本地接收至处理完成耗时 p50/p95。"""
        if not self.values:
            return {}
        values = np.asarray(self.values).sum(axis=1)
        p50, p95 = np.percentile(values, [50, 95])
        return {"samples":len(values), "local_p50_ms":float(p50), "local_p95_ms":float(p95)}
