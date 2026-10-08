"""Validated sampling controls and measured loop rate, independent of GUI/serial."""
from collections import deque


def validate_timing(interval_ms, confirm_frames):
    """Return integer settings; reject fractions and values outside safe UI bounds."""
    interval = int(str(interval_ms))
    frames = int(str(confirm_frames))
    if not 10 <= interval <= 100:
        raise ValueError('采样间隔必须为 10～100ms 的整数')
    if not 1 <= frames <= 3:
        raise ValueError('确认帧数必须为 1～3 的整数')
    return interval, frames


class FrameRate:
    """Rolling measured capture-loop frequency, including sleep and serial waits."""
    def __init__(self):
        self.starts = deque(maxlen=60)

    def record(self, now):
        self.starts.append(now)
        if len(self.starts) < 2:
            return 0.0
        elapsed = self.starts[-1] - self.starts[0]
        return (len(self.starts)-1)/elapsed if elapsed > 0 else 0.0
