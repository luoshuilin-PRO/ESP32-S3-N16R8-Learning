"""Offline checks; this file never opens a serial port or sends HID input."""
import json
from pathlib import Path
import unittest

import numpy as np
from PIL import Image

from detector import detect, detect_bgrx, Confirmation
from serial_link import packet
from timing import validate_timing


BASE = Path(__file__).resolve().parent
SAMPLES = BASE.parent / 'material-capture' / 'samples'


class FastTests(unittest.TestCase):
    def setUp(self):
        self.config = json.loads((BASE / 'config.json').read_text(encoding='utf-8'))

    def test_new_cropped_samples(self):
        paths = sorted(SAMPLES.glob('*/20261009_*.json'))
        self.assertEqual(len(paths), 11)
        counts = {'positive': 0, 'interference': 0, 'negative': 0}
        for path in paths:
            meta = json.loads(path.read_text(encoding='utf-8'))
            self.assertEqual(meta['source'], 'desktop')
            self.assertEqual(meta['roi'], self.config['roi'])
            with Image.open(path.with_suffix('.png')) as image:
                rgb = np.asarray(image.convert('RGB'))
                bgrx = np.empty((*rgb.shape[:2], 4), dtype=np.uint8)
                bgrx[:, :, :3] = rgb[:, :, ::-1]
                bgrx[:, :, 3] = 255
                live = detect_bgrx(bgrx, self.config)
                saved = detect(image, self.config)
            self.assertEqual(live['pixels'], saved['pixels'])
            self.assertEqual(live['hit'], saved['hit'])
            self.assertEqual(live['hit'], path.parent.name != 'negative', str(path))
            counts[path.parent.name] += 1
        self.assertEqual(counts, {'positive': 4, 'interference': 4, 'negative': 3})

    def test_empty_and_uniform_red_are_not_names(self):
        for color in ((0, 0, 0), (242, 74, 23), (255, 255, 255)):
            image = Image.new('RGB', (16, 21), color)
            self.assertFalse(detect(image, self.config)['hit'])

    def test_confirmation_and_timing(self):
        self.assertEqual(validate_timing(10, 1), (10, 1))
        confirmation = Confirmation()
        self.assertTrue(confirmation.update(True, 1))
        self.assertFalse(confirmation.update(False, 1))
        self.assertTrue(confirmation.update(True, 1))

    def test_protocol_unchanged(self):
        self.assertEqual(len(packet(123, 1)), 16)
        self.assertEqual(packet(123, 1)[:4], b'VC1!')


if __name__ == '__main__':
    unittest.main()
