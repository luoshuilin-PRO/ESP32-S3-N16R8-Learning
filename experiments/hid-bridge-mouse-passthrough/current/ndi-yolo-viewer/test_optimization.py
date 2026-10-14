import unittest
import numpy as np
from detector import letterbox, resolve_layout
from performance import Timings


class OptimizationTests(unittest.TestCase):
    def test_layout(self):
        self.assertEqual(resolve_layout((1,6300,7),2),"v5")
        self.assertEqual(resolve_layout((1,84,8400),80),"v8")
        with self.assertRaises(ValueError):
            resolve_layout((1,6300,6),1)

    def test_fp16(self):
        tensor, transform = letterbox(np.full((20,40,3),255,np.uint8),64,64,np.float16)
        self.assertEqual(tensor.dtype,np.float16)
        self.assertEqual(tensor.shape,(1,3,64,64))
        self.assertEqual(float(tensor.max()),1)
        self.assertEqual(transform,(1.6,0,16))

    def test_bounded_timings(self):
        timings=Timings(2)
        for q,p in ((100,100),(1,3),(2,4)):
            timings.add(q,p)
        report=timings.summary()
        self.assertEqual(report["samples"],2)
        self.assertEqual(report["local_p50_ms"],5)


if __name__ == "__main__":
    unittest.main()
