"""Camera-to-world ray casting for hand-pointer interaction.

The glasses' RGB camera is NOT at the eye and its exact intrinsics and
extrinsics are unpublished. Everything here is an explicitly APPROXIMATE
calibration, clearly labelled as such:

* Intrinsics: pinhole model with the principal point at the image
  centre, square pixels, and a configurable horizontal FOV
  (default 70 deg -- a plausible webcam-class value, NOT measured).
* Extrinsics: the camera is assumed to sit AT the head origin, axes
  aligned with the head frame (x right, y up, z backward). A
  configurable translation offset exists for later calibration.
* Orientation/mirroring of the sensor stream is configurable
  (flip_x / flip_y); defaults assume the image arrives upright and
  unmirrored (world-facing camera, not a selfie camera).

Do NOT treat MediaPipe landmarks as metric positions: only the
normalized 2D pointer is used, turned into a world-space RAY. All
subsequent interaction (hover, grab, drag) happens along that ray or
on planes derived from it.
"""

from __future__ import annotations

import math


class ApproxCamera:
    def __init__(self, width: int, height: int, hfov_deg: float = 70.0,
                 flip_x: bool = False, flip_y: bool = False) -> None:
        self.width = width
        self.height = height
        self.hfov_deg = hfov_deg
        self.flip_x = flip_x
        self.flip_y = flip_y
        half_w = math.tan(math.radians(hfov_deg) / 2.0)
        # Focal length in pixels (square pixels assumed).
        self.fx = (width / 2.0) / half_w if half_w > 0 else width / 2.0
        self.fy = self.fx

    def ray_camera_frame(self, nx: float, ny: float):
        """Normalized coords (x right, y DOWN, 0..1) -> (origin, dir).

        Camera frame: x right, y down, z forward (out of the lens).
        """
        if self.flip_x:
            nx = 1.0 - nx
        if self.flip_y:
            ny = 1.0 - ny
        dx = (nx - 0.5) * self.width / self.fx
        dy = (ny - 0.5) * self.height / self.fy
        inv = 1.0 / math.sqrt(dx * dx + dy * dy + 1.0)
        return (0.0, 0.0, 0.0), (dx * inv, dy * inv, inv)


def cam_to_gl(vec):
    """Camera frame (x right, y down, z fwd) -> GL (x right, y up, z back)."""
    return (vec[0], -vec[1], -vec[2])


class SpatialPointer:
    """Turns a normalized pointer into a world-space ray."""

    def __init__(self, camera: ApproxCamera,
                 cam_offset=(0.0, 0.0, 0.0)) -> None:
        self.camera = camera
        self.cam_offset = tuple(cam_offset)

    def ray_world(self, nx: float, ny: float, head_pos, head_quat):
        """Return (origin, dir) in the GL world frame.

        head_pos/head_quat use the SDK convention (GL frame, Hamilton).
        The (approximate) camera-to-head transform is identity rotation
        plus a configurable translation offset.
        """
        from pose_math import quat_rotate

        _o, d_cam = self.camera.ray_camera_frame(nx, ny)
        d_gl = cam_to_gl(d_cam)
        o_gl = cam_to_gl((0.0, 0.0, 0.0))
        direction = quat_rotate(head_quat, d_gl)
        origin = quat_rotate(head_quat, self.cam_offset)
        origin = (head_pos[0] + origin[0],
                  head_pos[1] + origin[1],
                  head_pos[2] + origin[2])
        return origin, direction


def intersect_plane(ray_o, ray_d, plane_p, plane_n):
    """Ray-plane intersection; None when parallel or behind the ray."""
    denom = sum(d * n for d, n in zip(ray_d, plane_n))
    if abs(denom) < 1e-9:
        return None
    t = sum((p - o) * n for p, o, n in zip(plane_p, ray_o, plane_n)) / denom
    if t < 0.0:
        return None
    return tuple(o + t * d for o, d in zip(ray_o, ray_d))


def angle_between(a, b) -> float:
    """Angle in radians between two vectors."""
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0.0 or nb == 0.0:
        return math.pi
    c = max(-1.0, min(1.0, dot / (na * nb)))
    return math.acos(c)
