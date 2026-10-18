import unittest
import numpy as np
from core import Frame
from output_control import Engine, Settings, nearest_head


def box(cls, coords):
    return {"class": cls, "box": coords, "score": .9}


class TeammateTests(unittest.TestCase):
    def test_head_zero_and_body_ignored(self):
        head = box(0, [45, 45, 55, 55])
        self.assertIs(nearest_head([head, box(1,[40,40,60,80])],100,100,150,0,2),head)

    def test_friend_overlap_rejected(self):
        self.assertIsNone(nearest_head([box(0,[45,45,55,55]),box(2,[50,40,80,90])],100,100,150,0,2))

    def test_separate_friend_preserves_head(self):
        head = box(0,[45,45,55,55])
        self.assertIs(nearest_head([head,box(2,[70,40,90,90])],100,100,150,0,2),head)

    def test_friend_conflict_releases_immediately(self):
        engine = Engine(Settings(head_class=0,teammate_class=2,move=True))
        result = {"frame":Frame(1,np.zeros((100,100,3),np.uint8),0,1),
                  "boxes":[box(0,[45,45,55,55])],"red":{"hit":True},"epoch":1}
        self.assertEqual(engine.step(result,0,True)[0],1)
        result["frame"] = Frame(2,np.zeros((100,100,3),np.uint8),.01,1)
        result["boxes"].append(box(2,[40,40,70,90]))
        self.assertEqual(engine.step(result,.01,True),(0,0,0,False))

    def test_legacy_default(self):
        head = box(1,[45,45,55,55])
        self.assertIs(nearest_head([head],100,100,150),head)


if __name__ == "__main__":
    unittest.main()
