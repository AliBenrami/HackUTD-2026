"""Cyberpunk archive, mesh, collision and atomic scene-swap checks."""
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class CyberAssetsTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from panda3d.core import loadPrcFileData
        loadPrcFileData("", "window-type none\naudio-library-name null")
        from direct.showbase.ShowBase import ShowBase
        cls.base = ShowBase()

    @classmethod
    def tearDownClass(cls): cls.base.destroy()

    def test_manifest_is_cyberpunk_only_and_license_recorded(self):
        from golf_assets import MANIFEST
        data = json.loads(MANIFEST.read_text())
        self.assertEqual(set(data["sources"]), {"cyberpunk"})
        self.assertEqual(len(data["models"]), 23)
        self.assertTrue(all(name.startswith("cyber_") for name in data["models"]))
        text = (ROOT / "assets/CYBERPUNK_ASSET_LICENSE.md").read_text()
        self.assertIn("redistributed", text)
        encoded = json.dumps(data).lower()
        for legacy in ("kenney", "nature-kit", "minigolf", "grab3d"):
            self.assertNotIn(legacy, encoded)

    def test_all_real_glbs_load_with_contact_pivots(self):
        from golf_assets import AssetManager
        manager = AssetManager(self.base.loader)
        for name in manager.available():
            with self.subTest(name=name):
                node = manager.load(name, target=("max", .10))
                lo, hi = node.get_tight_bounds()
                self.assertAlmostEqual(lo[2], 0, delta=1e-5)
                self.assertGreater(hi[2], 0)
                self.assertAlmostEqual(max(node.get_python_tag("dimensions_m")),
                                       .10, delta=.0001)

    def test_continuous_mesh_winding_normals_and_bullet_shape(self):
        from course_generator import generate
        from golf_assets import AssetManager
        from golf_scene import build_course
        layout = generate(42, .6, .4, "medium")
        parent = self.base.render.attach_new_node("course-scale-root")
        parent.set_scale(layout["course_scale"])
        course, objects = build_course(parent, AssetManager(self.base.loader),
                                       .6, .4, layout=layout)
        terrain = course.find("**/cyber-terrain")
        geom = terrain.node().get_geom(0)
        self.assertEqual(geom.get_num_primitives(), 1)
        n = layout["terrain"]["grid_size"]
        self.assertEqual(geom.get_primitive(0).get_num_primitives(),
                         (n-1)*(n-1)*2)
        from panda3d.core import GeomVertexReader
        normals = GeomVertexReader(geom.get_vertex_data(), "normal")
        for _ in range(min(200, geom.get_vertex_data().get_num_rows())):
            normal = normals.get_data3()
            self.assertAlmostEqual(normal.length(), 1.0, delta=1e-4)
            self.assertGreater(normal[2], 0)
        self.assertFalse(course.find("**/cyber-terrain-static-body").is_empty())
        lo, hi = terrain.get_tight_bounds()
        self.assertGreater(hi[2], lo[2])
        self.assertAlmostEqual((hi[0]-lo[0])*layout["course_scale"], .54, places=4)
        self.assertFalse(course.find("**/neon-fairway").is_empty())
        self.assertFalse(course.find("**/plasma-pool-0").is_empty())
        self.assertFalse(course.find("**/cyber-target").is_empty())
        parent.remove_node()

    def test_ball_size_independent_and_terrain_uses_scale_once(self):
        from course_generator import generate
        from golf_assets import AssetManager
        from golf_scene import build_course
        from golf_specs import BALL_DIAMETER_M
        layout = generate(5, .6, .4, "easy", course_scale=.25)
        parent = self.base.render.attach_new_node("course-scale-root")
        parent.set_scale(.25)
        course, _ = build_course(parent, AssetManager(self.base.loader), .6, .4,
                                 layout=layout, course_scale=.25)
        ball = course.find("**/cyber-ball")
        dims = ball.get_python_tag("dimensions_m")
        self.assertAlmostEqual(dims[0]*ball.get_scale()[0]*parent.get_scale()[0],
                               BALL_DIAMETER_M, places=6)
        self.assertAlmostEqual(ball.get_python_tag("collision_radius_m")*2,
                               BALL_DIAMETER_M, places=6)
        parent.remove_node()

    def test_atomic_swap_preserves_anchor_and_physical_obstacles(self):
        from ar_poc import VitureARApp
        from course_generator import generate
        from golf_assets import AssetManager
        from golf_scene import build_course
        table = self.base.render.attach_new_node("table")
        table.set_pos(.4, .2, -.8)
        stage = table.attach_new_node("stage")
        golf = stage.attach_new_node("golf-stage-root")
        scale_root = golf.attach_new_node("course-scale-root")
        physical = table.attach_new_node("physical-obstacles")
        manager = AssetManager(self.base.loader)
        first_layout = generate(1, .6, .4, "easy")
        first, _ = build_course(scale_root, manager, .6, .4, first_layout)
        app = SimpleNamespace(golf_stage=golf, golf_scale_root=scale_root,
                              golf_course=first, golf_objects=[], golf_assets=manager,
                              course_scale=.25, course_layout=first_layout,
                              course_previous=None, course_seed=1,
                              course_difficulty="easy", ball_diameter=.022,
                              golf_offset=[0,0,0,0,.25],
                              _log_course_dims=lambda why: None,
                              _log_generation_report=lambda layout: None,
                              args=SimpleNamespace(table_w=.6, table_l=.4))
        anchor_pos = tuple(table.get_pos())
        VitureARApp._course_swap(app, generate(2, .6, .4, "hard"))
        self.assertTrue(first.is_empty())
        self.assertEqual(tuple(table.get_pos()), anchor_pos)
        self.assertFalse(physical.is_empty())
        self.assertEqual(len(scale_root.find_all_matches("**/golf-course")), 1)
        self.assertEqual(len(scale_root.find_all_matches("**/cyber-terrain-static-body")), 1)
        table.remove_node()


if __name__ == "__main__": unittest.main()
