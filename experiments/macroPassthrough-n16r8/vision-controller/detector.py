"""Pure image analysis: input RGB image, output mask statistics and decision."""
import numpy as np

DEFAULTS = {'h_min': 3.0, 'h_max': 12.0, 's_min': 150, 'v_min': 140,
            'min_pixels': 20, 'max_fraction': 0.65, 'min_width': 5, 'min_height': 3,
            'confirm_frames': 2, 'interval_ms': 20}


def detect(image, config):
    """Calculate HSV (OpenCV scale) and a loose text-sized color mask; no OCR."""
    rgb = np.asarray(image.convert('RGB'), dtype=np.float32) / 255
    maximum, minimum = rgb.max(axis=2), rgb.min(axis=2)
    delta = maximum - minimum
    saturation = np.divide(delta, maximum, out=np.zeros_like(delta), where=maximum > 0)
    safe = np.where(delta > 0, delta, 1)
    r, g, b = rgb[:, :, 0], rgb[:, :, 1], rgb[:, :, 2]
    hue = np.select([maximum == r, maximum == g],
                    [((g-b)/safe) % 6, (b-r)/safe+2], default=(r-g)/safe+4) * 30
    hue[delta == 0] = 0
    mask = ((hue >= config['h_min']) & (hue <= config['h_max']) &
            (saturation*255 >= config['s_min']) & (maximum*255 >= config['v_min']))
    count = int(mask.sum())
    ys, xs = np.nonzero(mask)
    width = int(xs.max()-xs.min()+1) if count else 0
    height = int(ys.max()-ys.min()+1) if count else 0
    fraction = count / mask.size
    hit = (count >= config['min_pixels'] and fraction <= config['max_fraction'] and
           width >= config['min_width'] and height >= config['min_height'])
    return {'hit': bool(hit), 'pixels': count, 'fraction': fraction,
            'width': width, 'height': height, 'mask': mask}


class Confirmation:
    """Require consecutive hits to start; one negative stops immediately."""
    def __init__(self):
        self.count = 0

    def update(self, hit, required=2):
        self.count = self.count + 1 if hit else 0
        return self.count >= required
