"""Real licensed archive and Panda loader checks (no VITURE hardware needed)."""
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))


class GolfAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from panda3d.core import loadPrcFileData

        loadPrcFileData("", "window-type none\naudio-library-name null")
        from direct.showbase.ShowBase import ShowBase
        cls.base = ShowBase()

    @classmethod
    def tearDownClass(cls):
        cls.base.destroy()

    def test_catalog_matches_archives_and_license(self):
        import catalog_golf_assets
        from golf_assets import MANIFEST

        if not catalog_golf_assets.ROOT.is_dir() or not all(
            (catalog_golf_assets.ROOT / name).is_file()
            for name in catalog_golf_assets.PACKS
        ):
            self.skipTest("original downloaded archives are not present")

        expected = catalog_golf_assets.generate()
        self.assertEqual(expected, json.loads(MANIFEST.read_text()))
        self.assertEqual(len(expected["models"]), 489)
        self.assertNotIn("drive", expected["sources"])

    def test_loaded_models_texture_contact_and_cache(self):
        from golf_assets import AssetManager

        manager = AssetManager(self.base.loader)
        with self.assertRaisesRegex(KeyError, "Unknown golf asset"):
            manager.load("not-an-asset")
        for name in ("golf_start", "golf_ball-red", "nature_tree_default",
                     "grab3d_pond"):
            model = manager.load(name)
            lo, hi = model.get_tight_bounds()
            self.assertAlmostEqual(lo[2], 0, delta=1e-5, msg=name)
            self.assertLessEqual(max(model.get_python_tag("dimensions_m")), .22)
            self.assertGreater(hi[2], 0)
            self.assertIs(manager._models[name], manager._models[name])
        self.assertGreater(manager._models["golf_start"].find_all_textures().get_num_textures(), 0)
        self.assertGreater(manager._models["grab3d_pond"].find_all_textures().get_num_textures(), 0)
        a = manager.load("nature_tree_default")
        b = manager.load("nature_tree_default")
        a.set_pos(.12, .03, 0)
        self.assertEqual(tuple(b.get_pos()), (0, 0, 0))

    def test_course_anchored_metric_fit_and_independent_stage(self):
        from golf_assets import AssetManager
        from golf_scene import build_course

        manager = AssetManager(self.base.loader)
        anchor = self.base.render.attach_new_node("table-root")
        adjust = anchor.attach_new_node("table-adjust")
        stage = adjust.attach_new_node("table-stage")
        golf = stage.attach_new_node("golf-stage-root")
        course, placed = build_course(golf, manager, .60, .40)
        self.assertEqual(len(placed), 16)
        for node in placed:
            x, y, z = node.get_pos(course)
            dx, dy, dz = node.get_python_tag("dimensions_m")
            s = node.get_scale()[0]
            self.assertLessEqual(abs(x) + max(dx, dy) * s / 2, .30 + .01)
            self.assertLessEqual(abs(y) + max(dx, dy) * s / 2, .20 + .01)
            self.assertGreaterEqual(z, 0)
        original = placed[0].get_pos(course)
        golf.set_pos(.02, 0, .01)
        golf.set_h(15)
        golf.set_scale(.9)
        self.assertEqual(placed[0].get_pos(course), original)
        self.assertEqual(tuple(anchor.get_pos()), (0, 0, 0))
        self.assertEqual(tuple(adjust.get_pos()), (0, 0, 0))
        small, _ = build_course(golf, manager, .30, .20)
        self.assertAlmostEqual(small.get_scale()[0], .5)
        anchor.remove_node()


if __name__ == "__main__":
    unittest.main()
