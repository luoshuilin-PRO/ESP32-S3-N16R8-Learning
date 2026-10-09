"""Read-only comparison of old and new ROI capture on the current desktop."""
import json
from pathlib import Path
from statistics import median
from time import perf_counter

from PIL import ImageGrab

from capture import Capture
from detector import detect_bgrx


def measure(action, repeats=30):
    times = []
    for _ in range(repeats):
        begin = perf_counter()
        action()
        times.append((perf_counter() - begin) * 1000)
    times.sort()
    return median(times), times[int(0.95 * (len(times) - 1))]


def main():
    cfg = json.loads((Path(__file__).parent / 'config.json').read_text(encoding='utf-8'))
    a = cfg['roi']
    bbox = (a['x'], a['y'], a['x'] + a['width'], a['y'] + a['height'])
    with_roi = lambda: ImageGrab.grab(bbox=bbox, all_screens=True)
    old = measure(with_roi)
    capture = Capture(*bbox[:2], a['width'], a['height'])
    try:
        new = measure(capture.grab)
        combo = measure(lambda: detect_bgrx(capture.grab(), cfg))
    finally:
        capture.close()
    print(f"ROI {a['width']}x{a['height']} at ({a['x']},{a['y']})")
    print(f'Pillow capture median/p95: {old[0]:.2f}/{old[1]:.2f} ms')
    print(f'GDI capture median/p95:    {new[0]:.2f}/{new[1]:.2f} ms')
    print(f'GDI + detect median/p95:  {combo[0]:.2f}/{combo[1]:.2f} ms')
    print('Screen grab timing only; does not measure target appearance or USB click.')


if __name__ == '__main__':
    main()
