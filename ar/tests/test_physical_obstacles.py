"""Synthetic, camera-independent obstacle regression checks."""
from dataclasses import replace
import unittest

import cv2
import numpy as np

from physical_obstacles import (Footprint, ObstacleTracker, find_footprints,
                                ObstacleWorker, foreground, project_table)


class ImageTests(unittest.TestCase):
    def setUp(self):
        self.base = np.full((200, 300, 3), (110, 135, 155), np.uint8)
        self.valid = np.ones((200, 300), bool)

    def test_empty_and_exposure(self):
        self.assertFalse(np.any(foreground(self.base, self.base, self.valid)))
        lighter = np.clip(self.base.astype(int) + 18, 0, 255).astype(np.uint8)
        self.assertFalse(np.any(foreground(self.base, lighter, self.valid)))

    def test_object_and_boundary_and_mask(self):
        image = self.base.copy()
        cv2.rectangle(image, (60, 55), (95, 90), (20, 40, 225), -1)
        cv2.rectangle(image, (0, 0), (20, 20), (20, 40, 225), -1)
        mask = foreground(self.base, image, self.valid)
        detected = find_footprints(mask, self.valid, .6, .4)
        self.assertEqual(len(detected), 1)
        self.assertAlmostEqual(detected[0].x, -.145, delta=.01)
        permanent = np.zeros(self.valid.shape, bool)
        permanent[50:100, 55:100] = True
        self.assertEqual(find_footprints(foreground(self.base, image, self.valid,
                         permanent), self.valid, .6, .4), [])

    def test_projection_motion_compensation(self):
        # Camera translations move raw pixels but the tabletop image stays put.
        K = np.array([[300., 0, 150], [0, 300., 100], [0, 0, 1.]])
        anchor = ((0, 0, 0), (1, 0, 0, 0))
        patches = []
        for x in (0., .04):
            frame = self.base.copy()
            cx = round(150 - x * 300)
            cv2.rectangle(frame, (cx+35, 75), (cx+55, 95), (20, 40, 225), -1)
            warped = project_table(frame, K, np.zeros(5),
                    ((x, 0, 1), (1, 0, 0, 0)), anchor, .6, .4, 300)
            self.assertIsNotNone(warped)
            image, valid = warped
            self.assertGreater(valid.mean(), .8)
            patches.append(image)
        # Same object appears at same table-local coordinates (interp error < 1cm).
        hsv_centres = []
        for image in patches:
            yy, xx = np.where(image[:, :, 2] > 195)
            hsv_centres.append((xx.mean(), yy.mean()))
        self.assertLess(abs(hsv_centres[0][0] - hsv_centres[1][0]), 4)

    def test_end_to_end_jpeg_baseline_and_new_obstacle(self):
        worker = ObstacleWorker(.6, .4, resolution=300)
        worker.stop()  # drive the same worker computation synchronously
        worker.capture = True
        K = np.array([[300., 0, 150], [0, 300., 100], [0, 0, 1.]])
        camera = ((0, 0, 1), (1, 0, 0, 0))
        anchor = ((0, 0, 0), (1, 0, 0, 0))

        def feed(image, stamp):
            jpeg = cv2.imencode(".jpg", image)[1].tobytes()
            worker._process((jpeg, K, np.zeros(5), camera, anchor, stamp, False))

        for i in range(7):
            feed(self.base, i)
        self.assertIsNotNone(worker.baseline)
        self.assertTrue(any(e[0] == "baseline" for e in worker.drain()))
        image = self.base.copy()
        cv2.rectangle(image, (192, 75), (216, 100), (20, 40, 225), -1)
        for i in range(5):
            feed(image, 10+i)
        added = [e[1] for e in worker.drain() if e[0] == "add"]
        self.assertEqual(len(added), 1)
        self.assertAlmostEqual(added[0].x, .18, delta=.01)
        self.assertEqual(len(worker.tracker.anchored), 1)


class TrackerTests(unittest.TestCase):
    def setUp(self):
        self.tracker = ObstacleTracker(stable_frames=3, missing_frames=3)
        self.tracker.width, self.tracker.length = .6, .4
        self.a = Footprint(0, -.15, 0, .05, .05, confidence=.8)
        self.b = Footprint(0, .15, 0, .05, .05, confidence=.8)
        self.empty = np.ones((200, 300), bool)

    def test_stability_multiple_objects_and_world_lock(self):
        for _ in range(2):
            self.assertEqual(self.tracker.observe([self.a, self.b], automatic=True), [])
        events = self.tracker.observe([self.a, self.b])
        self.assertEqual(len(events), 2)
        ids = {a.id for _, a in events}
        self.assertEqual(len(ids), 2)
        original = dict(self.tracker.anchored)
        self.tracker.observe([replace(self.a, x=-.13), self.b])
        self.assertEqual(self.tracker.anchored, original)
        self.assertEqual(len(self.tracker.anchored), 2)
        self.assertEqual(self.tracker.observe([], visible=None), [])
        self.assertEqual(self.tracker.anchored, original)

    def test_removal_needs_visible_empty_region_and_hysteresis(self):
        for _ in range(3):
            self.tracker.observe([self.a])
        hidden = self.empty.copy()
        hidden[:, :100] = False
        for _ in range(5):
            self.assertFalse(self.tracker.observe([], hidden))
        self.assertEqual(len(self.tracker.anchored), 1)
        for _ in range(2):
            self.assertFalse(self.tracker.observe([], self.empty))
        self.assertEqual(len(self.tracker.observe([], self.empty)), 1)
        self.assertFalse(self.tracker.anchored)

    def test_manual_confirmation(self):
        for _ in range(3):
            self.assertFalse(self.tracker.observe([self.a], automatic=False))
        self.assertEqual(len(self.tracker.candidates), 1)
        id = next(iter(self.tracker.candidates))
        self.assertEqual(self.tracker.confirm(id).id, id)


if __name__ == "__main__":
    unittest.main()
