"""640×640 串流中准星下方固定红名检测；与 YOLO 裁剪区独立。"""
from dataclasses import dataclass
import cv2
import numpy as np
from core import crop_rect


@dataclass(frozen=True)
class RedSettings:
    roi: tuple = (268,377,90,24)
    size: tuple = (640,640)
    hue_max: int = 12
    saturation_min: int = 150
    value_min: int = 140
    min_pixels: int = 20

    def validate(self):
        if tuple(self.size)!=(640,640) or not 0<=self.hue_max<=179 or not 0<=self.saturation_min<=255 or not 0<=self.value_min<=255:
            raise ValueError("红名尺寸或 HSV 参数非法")
        x,y,w,h=crop_rect(self.roi,*self.size)
        if not 1<=self.min_pixels<=w*h:
            raise ValueError("红名像素阈值非法")


def detect_red(rgb, settings=RedSettings()):
    """输入完整 RGB 帧与固定区域，输出命中、像素数与颜色分布，不生成输入。"""
    settings.validate()
    h,w = rgb.shape[:2]
    if (w,h) != settings.size:
        raise ValueError("红名配置仅适用于 640×640 串流，请重新核对区域")
    x,y,rw,rh = crop_rect(settings.roi,w,h)
    hsv = cv2.cvtColor(rgb[y:y+rh,x:x+rw],cv2.COLOR_RGB2HSV)
    mask = ((hsv[:,:,0] <= settings.hue_max) & (hsv[:,:,1] >= settings.saturation_min)
            & (hsv[:,:,2] >= settings.value_min))
    count = int(mask.sum())
    ys,xs = np.where(mask)
    span_w = int(xs.max()-xs.min()+1) if count else 0
    span_h = int(ys.max()-ys.min()+1) if count else 0
    hit = count >= settings.min_pixels and span_w >= 12 and span_h >= 3 and count/(rw*rh) <= .65
    return {"hit":bool(hit),"pixels":count,"span":[span_w,span_h],"roi":list(settings.roi)}
