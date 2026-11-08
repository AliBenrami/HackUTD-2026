"""RGB tabletop change detection. No Panda objects are accessed by this worker.

All positions are in the existing marker-centred table XY frame (metres).
Plane warping is NOT 3D reconstruction: tall objects have parallax and their
reported footprint is approximate. Only near-overhead, well-covered views are
accepted; calibrated intrinsics/extrinsics give the best results.
"""
from __future__ import annotations

from dataclasses import dataclass, replace
import math
import queue
import threading
import time

import cv2
import numpy as np

import pose_math
import tabletop


@dataclass(frozen=True)
class Footprint:
    id: int
    x: float
    y: float
    width: float
    length: float
    angle: float = 0.0
    confidence: float = 0.0
    stamp: float = 0.0
    kind: str = "rock"


def project_table(frame, K, dist, camera_pose, anchor_pose, width, length,
                  pixels_per_m=500, max_tilt_deg=40):
    """Undistort and warp the plane into table XY. Return image, validity mask.

    Camera pose and anchor pose are world-space (pos, Hamilton quat). The
    rectified image has +X right and +Y up (image row decreases with +Y).
    """
    cw, ch = max(1, round(width * pixels_per_m)), max(1, round(length * pixels_per_m))
    cp, cq = camera_pose
    ap, aq = anchor_pose
    c_inv = tabletop.rigid_inv(cp, cq)
    origin = tabletop.rigid_apply(*c_inv, ap)
    F = np.diag([1., -1., -1.])
    c_origin = F @ np.asarray(origin)
    normal = F @ np.asarray(pose_math.quat_rotate(
        c_inv[1], pose_math.quat_rotate(aq, (0, 0, 1))))
    facing = float(np.dot(normal, -c_origin) / max(1e-9, np.linalg.norm(c_origin)))
    if c_origin[2] <= 0 or facing < math.cos(math.radians(max_tilt_deg)):
        return None
    corners = [(-width / 2, length / 2, 0), (width / 2, length / 2, 0),
               (width / 2, -length / 2, 0), (-width / 2, -length / 2, 0)]
    points = []
    for p in corners:
        world = tabletop.rigid_apply(ap, aq, p)
        cam = tabletop.rigid_apply(*c_inv, world)
        cv = F @ np.asarray(cam)
        if cv[2] <= 0.05:
            return None
        points.append((K[0, 0] * cv[0] / cv[2] + K[0, 2],
                       K[1, 1] * cv[1] / cv[2] + K[1, 2]))
    undistorted = cv2.undistort(frame, K, dist)
    destination = np.float32([(0, 0), (cw - 1, 0),
                              (cw - 1, ch - 1), (0, ch - 1)])
    H = cv2.getPerspectiveTransform(np.float32(points), destination)
    image = cv2.warpPerspective(undistorted, H, (cw, ch))
    valid = cv2.warpPerspective(np.full(frame.shape[:2], 255, np.uint8),
                                H, (cw, ch), flags=cv2.INTER_NEAREST) > 0
    return image, valid


def foreground(baseline, image, valid, permanent=None, threshold=27):
    """Normalize global exposure, suppress dark-only shadows and tiny noise."""
    allowed = valid.copy()
    if permanent is not None:
        allowed &= ~permanent
    if not np.any(allowed):
        return np.zeros(valid.shape, np.uint8)
    a = cv2.cvtColor(baseline, cv2.COLOR_BGR2LAB).astype(np.float32)
    b = cv2.cvtColor(image, cv2.COLOR_BGR2LAB).astype(np.float32)
    # A uniform auto-exposure / white-balance change is not an object.
    shift = np.median(b[allowed] - a[allowed], axis=0)
    delta = b - shift - a
    chroma = np.linalg.norm(delta[:, :, 1:], axis=2)
    light = delta[:, :, 0]
    # Shadows generally darken with little chroma change. A genuinely dark
    # same-colour object is consequently a known false negative.
    mask = allowed & ((chroma > threshold * .55) |
                      (light > threshold) |
                      ((light < -threshold) & (chroma > threshold * .35)))
    out = (mask.astype(np.uint8) * 255)
    out = cv2.morphologyEx(out, cv2.MORPH_OPEN,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (3, 3)))
    return cv2.morphologyEx(out, cv2.MORPH_CLOSE,
                           cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5)))


def find_footprints(mask, valid, width, length, stamp=0., min_area_m2=.00015,
                    padding=.006):
    """Reject boundary/partial regions; approximate contact by lower edge.

    The image row closest to the camera is NOT necessarily the ground contact;
    use the component's table-plane centroid and mark it approximate instead.
    """
    h, w = mask.shape
    contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    results = []
    for contour in contours:
        if cv2.contourArea(contour) * width * length / (w * h) < min_area_m2:
            continue
        x, y, bw, bh = cv2.boundingRect(contour)
        if x <= 2 or y <= 2 or x + bw >= w - 2 or y + bh >= h - 2:
            continue
        region = valid[max(0, y-2):min(h, y+bh+2), max(0, x-2):min(w, x+bw+2)]
        if np.mean(region) < .95:
            continue
        (cx, cy), (rw, rh), angle = cv2.minAreaRect(contour)
        if min(rw, rh) < 3:
            continue
        results.append(Footprint(0, (cx / (w-1) - .5) * width,
                                 (.5 - cy / (h-1)) * length,
                                 rw * width / w + padding * 2,
                                 rh * length / h + padding * 2,
                                 -angle, min(1., cv2.contourArea(contour) / (rw*rh)), stamp))
    return results


def overlaps(a, b):
    return (abs(a.x - b.x) < max(a.width, b.width) * .65 + .012 and
            abs(a.y - b.y) < max(a.length, b.length) * .65 + .012)


class ObstacleTracker:
    """Stable tabletop association. Confirmed records never follow observations."""

    def __init__(self, stable_frames=5, missing_frames=8):
        self.stable_frames = stable_frames
        self.missing_frames = missing_frames
        self.candidates = {}  # id -> (footprint, count)
        self.anchored = {}
        self.absent = {}
        self.next_id = 1

    def observe(self, detections, visible=None, automatic=True):
        events = []
        seen = set()
        for d in detections:
            existing = next((i for i, a in self.anchored.items() if overlaps(d, a)), None)
            if existing is not None:
                seen.add(existing)
                self.absent[existing] = 0
                continue
            choices = ((math.hypot(d.x-a.x, d.y-a.y), i)
                       for i, (a, _) in self.candidates.items()
                       if i not in seen and overlaps(d, a))
            match = min(choices, default=(0, None))[1]
            if match is None:
                match = self.next_id
                self.next_id += 1
                self.candidates[match] = (replace(d, id=match), 0)
            prior, count = self.candidates[match]
            count += 1
            self.candidates[match] = (replace(d, id=match,
                x=(prior.x * (count-1) + d.x)/count,
                y=(prior.y * (count-1) + d.y)/count), count)
            seen.add(match)
            if count >= self.stable_frames and automatic:
                obj = self.confirm(match)
                events.append(("add", obj))
        for i in list(self.candidates):
            if i not in seen:
                a, count = self.candidates[i]
                if count <= 1:
                    del self.candidates[i]
                else:
                    self.candidates[i] = (a, count-1)
        for i, a in list(self.anchored.items()):
            if not automatic:
                continue
            if i in seen or visible is None:
                continue
            # Only positive evidence of an EMPTY, fully-visible region removes.
            h, w = visible.shape
            px = round((a.x / self.width + .5) * (w-1))
            py = round((.5 - a.y / self.length) * (h-1))
            rx = max(3, round(a.width / self.width * w / 2))
            ry = max(3, round(a.length / self.length * h / 2))
            if px-rx < 0 or py-ry < 0 or px+rx >= w or py+ry >= h or not np.all(
                    visible[py-ry:py+ry+1, px-rx:px+rx+1]):
                continue
            self.absent[i] = self.absent.get(i, 0) + 1
            if self.absent[i] >= self.missing_frames:
                events.append(("remove", self.anchored.pop(i)))
                del self.absent[i]
        return events

    def confirm(self, id):
        a, count = self.candidates[id]
        if count < self.stable_frames:
            return None
        del self.candidates[id]
        self.anchored[id] = a
        self.absent[id] = 0
        return a

    def remove(self, id):
        self.candidates.pop(id, None)
        self.absent.pop(id, None)
        return self.anchored.pop(id, None)


class ObstacleWorker:
    """Single-slot mailbox. Render thread submits bytes/immutable pose snapshots."""

    def __init__(self, width, length, resolution=500, debug=False):
        self.width, self.length = width, length
        self.resolution = resolution
        self.debug = debug
        self.inbox = queue.Queue(maxsize=1)
        self.events = queue.Queue()
        self.commands = queue.Queue()
        self.tracker = ObstacleTracker()
        self.tracker.width, self.tracker.length = width, length
        self.baseline = None
        self.baseline_valid = None
        self.baseline_frames = []
        self.capture = False
        self.auto = True  # idle until a deliberate empty-table baseline exists
        self.scan = False
        self.permanent = None
        self.rejected = {}  # candidate id -> (footprint, consecutive empty views)
        self.running = True
        self.last_debug = None
        self.thread = threading.Thread(target=self._run, name="obstacle-cv", daemon=True)
        self.thread.start()

    def submit(self, item):
        try:
            self.inbox.put_nowait(item)
        except queue.Full:
            pass

    def command(self, name, *args):
        self.commands.put((name, args))

    def drain(self):
        out = []
        while True:
            try:
                out.append(self.events.get_nowait())
            except queue.Empty:
                return out

    def stop(self):
        self.running = False
        self.thread.join(timeout=2)
        if self.debug and self.last_debug is not None:
            try:
                cv2.destroyWindow("Table obstacles (laptop)")
            except cv2.error:
                pass

    def _run(self):
        while self.running:
            while not self.commands.empty():
                name, args = self.commands.get_nowait()
                if name == "capture":
                    self.capture = True
                    self.baseline_frames.clear()
                    self.rejected.clear()
                elif name == "invalidate":
                    self.baseline = None
                    self.baseline_valid = None
                    self.baseline_frames.clear()
                    self.capture = False
                    self.tracker.candidates.clear()
                    self.rejected.clear()
                elif name == "auto":
                    self.auto = args[0]
                elif name == "scan":
                    self.scan = args[0]
                elif name == "confirm":
                    obj = self.tracker.confirm(args[0])
                    if obj is not None:
                        self.events.put(("add", obj))
                elif name == "remove":
                    self.tracker.remove(args[0])
                elif name == "reject":
                    candidate = self.tracker.candidates.pop(args[0], None)
                    if candidate:
                        self.rejected[args[0]] = (candidate[0], 0)
                elif name == "clear":
                    self.tracker.candidates.clear()
                    self.tracker.anchored.clear()
                    self.tracker.absent.clear()
                    self.rejected.clear()
                elif name == "restore":
                    obj = args[0]
                    self.tracker.anchored[obj.id] = obj
                    self.tracker.absent[obj.id] = 0
                    self.tracker.next_id = max(self.tracker.next_id, obj.id + 1)
                elif name == "edit":
                    obj = args[0]
                    self.tracker.anchored[obj.id] = obj
                    self.tracker.absent[obj.id] = 0
                elif name == "mask":
                    x, y, rw, rh = args
                    if self.permanent is not None:
                        h, w = self.permanent.shape
                        cx = round((x / self.width + .5) * w)
                        cy = round((.5 - y / self.length) * h)
                        dx = round(rw / self.width * w / 2)
                        dy = round(rh / self.length * h / 2)
                        self.permanent[max(0,cy-dy):min(h,cy+dy+1),
                                       max(0,cx-dx):min(w,cx+dx+1)] = True
            try:
                item = self.inbox.get(timeout=.1)
            except queue.Empty:
                continue
            started = time.monotonic()
            try:
                self._process(item)
            except Exception as exc:
                self.events.put(("error", str(exc)))
            if self.debug and self.last_debug is not None:
                try:
                    cv2.imshow("Table obstacles (laptop)", self.last_debug)
                    cv2.waitKey(1)
                except cv2.error:
                    self.debug = False
            if time.monotonic() - started > .2:
                self.events.put(("latency", round((time.monotonic()-started)*1000)))

    def _process(self, item):
        jpeg, K, dist, camera, anchor, stamp, hand = item
        frame = cv2.imdecode(np.frombuffer(jpeg, np.uint8), cv2.IMREAD_COLOR)
        if frame is None:
            return
        warped = project_table(frame, K, dist, camera, anchor,
                               self.width, self.length, self.resolution)
        if warped is None:
            return
        image, valid = warped
        h, w = valid.shape
        if self.permanent is None:
            self.permanent = np.zeros((h, w), bool)
            # Marker centre: keep a margin around the printed target.
            mx = round(.07 / self.width * w)
            my = round(.07 / self.length * h)
            self.permanent[h//2-my:h//2+my, w//2-mx:w//2+mx] = True
        allowed = valid & ~self.permanent
        coverage = np.mean(allowed)
        if hand or coverage < .65:
            return
        if self.debug and self.baseline is None:
            blank = np.zeros_like(image)
            self.last_debug = np.hstack((cv2.resize(frame, (w, h)), image,
                                         blank, blank.copy()))
        if self.capture:
            if not self.baseline_frames:
                self.baseline = None
                self.tracker.candidates.clear()
            self.baseline_frames.append((image, valid))
            if len(self.baseline_frames) >= 7:
                common = np.logical_and.reduce(
                    [v for _, v in self.baseline_frames])
                if np.mean(common & ~self.permanent) < .60:
                    self.baseline_frames.pop(0)
                    return  # move closer / look more directly down
                self.baseline = np.median([a for a, _ in self.baseline_frames],
                                          axis=0).astype(np.uint8)
                self.baseline_valid = common
                self.baseline_frames.clear()
                self.capture = False
                self.events.put(("baseline", coverage))
            return
        if self.baseline is None or not (self.auto or self.scan):
            return
        allowed &= self.baseline_valid
        mask = foreground(self.baseline, image, allowed, self.permanent)
        detections = find_footprints(mask, allowed, self.width, self.length, stamp)
        for id, (obj, empty_count) in list(self.rejected.items()):
            if any(overlaps(d, obj) for d in detections):
                self.rejected[id] = (obj, 0)
            else:
                self.rejected[id] = (obj, empty_count+1)
                if empty_count+1 >= 8:
                    del self.rejected[id]
        detections = [d for d in detections if not any(
            overlaps(d, obj) for obj, _ in self.rejected.values())]
        # Removal only if the object's previous region is fully in view and
        # now looks like baseline; occluded/changed regions never prove absence.
        empty = allowed & (mask == 0)
        for event in self.tracker.observe(detections, empty, self.auto):
            self.events.put(event)
        if self.scan:
            self.events.put(("candidates", dict(self.tracker.candidates)))
        if self.debug:
            panel = []
            for tile in (cv2.resize(frame, (w, h)), image,
                         self.baseline, cv2.cvtColor(mask, cv2.COLOR_GRAY2BGR)):
                panel.append(tile)
            for d in detections:
                x = round((d.x / self.width + .5) * w)
                y = round((.5 - d.y / self.length) * h)
                cv2.circle(panel[1], (x, y), 5, (0, 255, 255), 2)
            for id, (obj, count) in self.tracker.candidates.items():
                x = round((obj.x / self.width + .5) * w)
                y = round((.5 - obj.y / self.length) * h)
                cv2.putText(panel[1], f"C{id}:{count}", (x, y),
                            cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 240, 255), 1)
            for id, obj in self.tracker.anchored.items():
                x = round((obj.x / self.width + .5) * w)
                y = round((.5 - obj.y / self.length) * h)
                cv2.circle(panel[1], (x, y), 6, (0, 255, 0), 2)
                cv2.putText(panel[1], f"#{id}", (x+7, y),
                            cv2.FONT_HERSHEY_SIMPLEX, .35, (0, 255, 0), 1)
            self.last_debug = np.hstack(panel)
