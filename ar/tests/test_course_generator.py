"""Render-independent continuous cyberpunk terrain generation tests."""
import json
import math
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from course_generator import (DIFFICULTIES, generate, height_and_slope,
                              route_search, signature, terrain_height, validate)
from golf_specs import BALL_DIAMETER_M, COURSE_SCALE


class CyberTerrainGeneratorTests(unittest.TestCase):
    def test_determinism_serialization_and_variation(self):
        a = generate(9876, .6, .4, "hard")
        self.assertEqual(a, generate(9876, .6, .4, "hard"))
        self.assertEqual(a, json.loads(json.dumps(a)))
        self.assertNotEqual(signature(a), signature(generate(9877, .6, .4, "hard")))

    def test_100_seeds_each_difficulty(self):
        limits = {"easy": .60, "medium": .85, "hard": 1.15}
        for difficulty in DIFFICULTIES:
            signatures, archetypes = set(), set()
            for seed in range(100):
                layout = generate(seed, .6, .4, difficulty)
                valid, report = validate(layout)
                self.assertTrue(valid, (difficulty, seed, report))
                self.assertIsNotNone(route_search(layout))
                self.assertLessEqual(report["max_route_slope"], limits[difficulty])
                self.assertEqual(report["terrain_m"], [.54, .34])
                self.assertEqual(report["ball_diameter_m"], .022)
                signatures.add(signature(layout))
                archetypes.add(layout["archetype"])
            self.assertEqual(len(signatures), 100)
            self.assertGreaterEqual(len(archetypes), 2)

    def test_difficulty_changes_geometry_and_interference(self):
        easy = generate(77, .6, .4, "easy")
        medium = generate(77, .6, .4, "medium")
        hard = generate(77, .6, .4, "hard")
        self.assertGreater(easy["fairway_width_m"], medium["fairway_width_m"])
        self.assertGreater(medium["fairway_width_m"], hard["fairway_width_m"])
        self.assertEqual(len(easy["obstacles"]), 0)
        self.assertGreaterEqual(len(medium["obstacles"]), 1)
        self.assertGreaterEqual(len(hard["obstacles"]), 2)
        self.assertGreater(hard["terrain"]["height_amplitude_m"],
                           easy["terrain"]["height_amplitude_m"])
        self.assertIn("partially obstructing", medium["validation"]["interference"])
        self.assertIn("directly obstructing", hard["validation"]["interference"])
        self.assertAlmostEqual(easy["fairway_width_m"]*easy["course_scale"], .120)
        self.assertAlmostEqual(medium["fairway_width_m"]*medium["course_scale"], .090)
        self.assertAlmostEqual(hard["fairway_width_m"]*hard["course_scale"], .065)

    def test_height_query_is_finite_continuous_and_shared(self):
        layout = generate(123, .6, .4, "hard")
        last = None
        for i in range(65):
            x = -layout["terrain"]["width_m"]/2 + i*layout["terrain"]["width_m"]/64
            z, slope = height_and_slope(layout, x, 0)
            self.assertTrue(math.isfinite(z+slope))
            if last is not None:
                self.assertLess(abs(z-last), .16)
            last = z
        sx, sy = layout["start"]
        hx, hy = layout["hole"]
        self.assertAlmostEqual(terrain_height(layout, sx, sy),
                               layout["terrain"]["base_height_m"], places=5)
        self.assertAlmostEqual(terrain_height(layout, hx, hy),
                               layout["terrain"]["base_height_m"], places=5)

    def test_physical_scale_bounds_and_ball_clearance(self):
        for scale in (.20, COURSE_SCALE, .40):
            layout = generate(9, .6, .4, "medium", course_scale=scale)
            self.assertTrue(validate(layout)[0])
            self.assertAlmostEqual(layout["terrain"]["width_m"]*scale, .54)
            self.assertAlmostEqual(layout["terrain"]["length_m"]*scale, .34)
            self.assertGreater(layout["fairway_width_m"]*scale,
                               BALL_DIAMETER_M+2*.003)

    def test_reserved_footprints_and_failure_paths(self):
        reserved = [(0.22, .12, .025, .025)]
        for seed in range(20):
            layout = generate(seed, .6, .4, "medium", reserved=reserved)
            for item in layout["objects"]:
                x, y, _ = item["position"]
                x *= layout["course_scale"]; y *= layout["course_scale"]
                radius = item.get("footprint_m", 0)*layout["course_scale"]/2
                self.assertFalse(abs(x-.22) < radius+.025 and
                                 abs(y-.12) < radius+.025)
        with self.assertRaises(ValueError): generate(0, .15, .12, "hard")
        with self.assertRaises(ValueError): generate(0, .6, .4, "unknown")
        with self.assertRaises(ValueError): generate(0, .6, .4, "easy", grid_size=64)
        with self.assertRaises(ValueError): generate(0, .6, .4, "easy", ball_diameter_m=.019)
        with self.assertRaises(ValueError): generate(0, .6, .4, "easy", ball_diameter_m=.044)

    def test_configured_ball_drives_clearance_and_validation(self):
        for diameter in (.020, .022, .043):
            layout = generate(18, .6, .4, "easy", ball_diameter_m=diameter)
            valid, report = validate(layout)
            self.assertTrue(valid, report)
            self.assertEqual(report["ball_diameter_m"], diameter)
            self.assertGreater(report["fairway_width_m"], diameter*2)

    def test_layout_contains_no_legacy_assets(self):
        encoded = json.dumps(generate(3, .6, .4, "hard"))
        for legacy in ("golf_", "nature_", "grab3d", "pond", "windmill"):
            self.assertNotIn(legacy, encoded)


if __name__ == "__main__":
    unittest.main()
