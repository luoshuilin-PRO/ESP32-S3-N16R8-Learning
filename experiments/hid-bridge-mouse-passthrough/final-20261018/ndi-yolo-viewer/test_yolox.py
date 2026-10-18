"""YOLOX raw grid decoding and preprocessing checks; no hardware input."""
import unittest

import numpy as np
from detector import decode_yolox, parse_output, yolox_input


class YoloXTests(unittest.TestCase):
    def test_grid_decode_and_class_score(self):
        raw = np.zeros((1, 21, 9), np.float32)  # 32x32: 4x4 + 2x2 + 1x1
        raw[0, 1, :4] = (0.5, 0.5, np.log(2), 0)
        raw[0, 1, 4] = .8
        raw[0, 1, 5:] = (.1, .1, .9, .1)
        decoded = decode_yolox(raw, 32, 32, 4)
        np.testing.assert_allclose(decoded[0, 1, :4], (12, 4, 16, 8))
        boxes = parse_output(raw, "yolox", 4, .25, .45, (1, 0, 0),
                             (32, 32), set(), (32, 32))
        self.assertEqual(len(boxes), 1)
        self.assertEqual(boxes[0]["class"], 2)
        np.testing.assert_allclose(boxes[0]["box"], (4, 0, 20, 8))
        self.assertAlmostEqual(boxes[0]["score"], .72, places=5)

    def test_bgr_no_normalization_and_top_left_padding(self):
        rgb = np.array([[[255, 0, 0], [0, 255, 0]]], np.uint8)
        tensor, transform = yolox_input(rgb, 4, 4)
        self.assertEqual(transform, (2.0, 0, 0))
        self.assertEqual(tensor.dtype, np.float32)
        self.assertEqual(tensor[0, 2, 0, 0], 255)
        self.assertEqual(tensor[0, :, 3, 0].tolist(), [114, 114, 114])

    def test_wrong_grid_count_rejected(self):
        with self.assertRaisesRegex(ValueError, "网格数量"):
            decode_yolox(np.zeros((1, 20, 9), np.float32), 32, 32, 4)


if __name__ == "__main__":
    unittest.main()
