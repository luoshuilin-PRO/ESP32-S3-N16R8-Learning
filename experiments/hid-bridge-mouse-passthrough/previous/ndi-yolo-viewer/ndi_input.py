"""cyndilib NDI 接收接口；仅订阅视频，不发送控制、音频或输入设备命令。"""
import time
import numpy as np
from cyndilib.finder import Finder
from cyndilib.receiver import Receiver, ReceiveFrameType
from cyndilib.video_frame import VideoRecvFrame
from cyndilib.wrapper.ndi_recv import RecvColorFormat
from core import Frame, ndi_rgb


def scan():
    """扫描最多 3 秒，输出 NDI 来源名称列表，关闭临时 Finder。"""
    with Finder() as finder:
        finder.wait_for_sources(timeout=3)
        return list(finder.get_source_names())


def receive(name, stop, latest, status, stream):
    """输入来源、停止事件与最新帧容器；发布 RGB 帧，断流清空，定期重新连接。"""
    with Finder() as finder:
        finder.wait_for_sources(timeout=3)
        source = finder.get_source(name)
        if source is None:
            raise RuntimeError("NDI 来源已离线，请刷新来源")
        receiver = Receiver(color_format=RecvColorFormat.RGBX_RGBA, allow_video_fields=False)
        video = VideoRecvFrame(max_buffers=2)
        receiver.set_video_frame(video)
        receiver.set_source(source)
        count = sequence = 0
        start = last = retry = time.monotonic()
        offline = True
        status("等待 NDI 视频帧")
        try:
            while not stop.is_set():
                # 此包装器同步接收可能占住 GIL；限制等待并在空轮询后让出线程。
                kind = receiver.receive(ReceiveFrameType.recv_video, 5)
                now = time.monotonic()
                if kind & ReceiveFrameType.recv_video:
                    # 0.1.3 在只有一帧时 skip_frames(True) 也会移除该帧。
                    if video.get_buffer_depth() > 1:
                        video.skip_frames(eager=True)
                    raw = np.frombuffer(video, dtype=np.uint8).copy()
                    rgb = ndi_rgb(raw, video.xres, video.yres, video.get_line_stride(), video.get_fourcc().name)
                    rgb.flags.writeable = False
                    count += 1
                    sequence += 1
                    latest.put(Frame(sequence, rgb, now, stream))
                    last = now
                    if offline:
                        status(f"NDI 已连接：{video.xres}×{video.yres}")
                        offline = False
                else:
                    stop.wait(.002)
                if now - last > 2:
                    latest.put(None)
                    if not offline:
                        status("NDI 断流／等待恢复，旧画面停止用于识别")
                        offline = True
                    if now - retry > 5:
                        receiver.reconnect()
                        retry = now
                if now - start >= 1:
                    status(("fps", count / (now - start)))
                    start, count = now, 0
        finally:
            receiver.disconnect()
            latest.put(None)
