"""Stage/object manipulation driven by pinch gestures (or keys).

Scene layout (GL frame, metres):

    render
      +-- <head cameras>            (driven by head tracking; never moved here)
      +-- stage_root               (everything the user may move)
            +-- <object nodes>...  (individual targets)

Moving stage_root repositions the whole environment. Moving an object
changes only its local transform. Head tracking is never touched.

Grab semantics: on grab, intersect the pointer ray with a camera-facing
plane through the grab point; while dragging, move the target by the
*delta* of the intersection (grab offset preserved -- objects never
snap to the pointer). All motion derives from live frames only: when
tracking is lost the drag freezes, and on release the position commits
exactly where it is. No jumps, ever.
"""

from __future__ import annotations

import math

STAGE = "stage"
OBJECT = "object"

SELECT_CONE_DEG = 4.0
NUDGE_STEP_M = 0.05
YAW_STEP_DEG = 5.0
UNDO_DEPTH = 50
# Depth of the stage manipulation plane ahead of the head (m). The
# plane must NOT pass through the head: a plane containing the ray
# origin intersects every ray at t=0 and nothing can ever move.
STAGE_PLANE_DEPTH = 2.0
# Grabs closer than this to the ray origin are rejected (degenerate).
MIN_GRAB_DISTANCE = 0.3


class SceneManipulator:
    def __init__(self, stage_root, objects: dict, render_root,
                 pointer, select_cone_deg: float = SELECT_CONE_DEG,
                 sensitivity: float = 1.0) -> None:
        """
        stage_root: NodePath parent of every movable object.
        objects:    {name: NodePath} with stage_root as parent.
        render_root: world frame for ray/plane math (Panda render).
        pointer:    SpatialPointer used to build rays from NDC positions.
        """
        self._stage = stage_root
        self._objects = dict(objects)
        self._render = render_root
        self._pointer = pointer
        self._select_cos = math.cos(math.radians(select_cone_deg))
        self.sensitivity = sensitivity

        self.enabled = False
        self.mode = STAGE  # or OBJECT
        self.selected: str | None = None  # object name in OBJECT mode
        self.hover_target: str | None = None
        self.grabbed: str | None = None  # "stage" or object name
        self.last_ray = None  # (origin, dir) world, for the indicator

        self._drag_plane = None   # (point, normal) world
        self._grab_hit = None     # world point where the grab landed
        self._start_pos = None     # target local pos at grab
        self._start_quat = None
        self._undo: list = []
        self._head_pos = (0.0, 0.0, 0.0)
        self._head_quat = (1.0, 0.0, 0.0, 0.0)

    # -- configuration ----------------------------------------------------
    def set_enabled(self, on: bool) -> None:
        on = bool(on)
        if self.enabled and not on and self.grabbed is not None:
            self._cancel_drag()  # disabling never modifies the scene
        self.enabled = on
        if not on:
            self.grabbed = None
            self.hover_target = None

    def set_mode(self, mode: str) -> None:
        assert mode in (STAGE, OBJECT)
        if self.grabbed is not None:
            self._cancel_drag()
        self.mode = mode
        self.hover_target = None

    def cycle_object(self) -> str | None:
        names = sorted(self._objects.keys())
        if not names:
            return None
        if self.selected not in names:
            self.selected = names[0]
        else:
            self.selected = names[(names.index(self.selected) + 1) % len(names)]
        return self.selected

    # -- per-frame ----------------------------------------------------------
    def update(self, gesture, head_pos, head_quat) -> None:
        """Advance one frame. gesture: GestureState (or None = no hand)."""
        from pose_math import quat_rotate

        self._head_pos = tuple(head_pos)
        self._head_quat = tuple(head_quat)
        if not self.enabled or gesture is None:
            return

        fwd_gl = quat_rotate(head_quat, (0.0, 0.0, -1.0))
        fwd = (fwd_gl[0], -fwd_gl[2], fwd_gl[1])  # GL -> Panda world
        ray = self._pointer.ray_world(*gesture.pos, head_pos, head_quat)
        ray_o, ray_d = self._to_panda_ray(ray)
        self.last_ray = (ray_o, ray_d)

        if self.mode == OBJECT:
            self.hover_target = self._pick_object(ray_o, ray_d)
            if self.selected is None:
                self.selected = self.hover_target
        else:
            self.hover_target = None

        if gesture.just_grabbed:
            self._begin_drag(gesture, ray_o, ray_d, fwd)
        if gesture.state == "drag" and self.grabbed is not None:
            self._continue_drag(ray_o, ray_d)
        if gesture.just_released and self.grabbed is not None:
            self._end_drag()

    # -- selection ------------------------------------------------------------
    def _pick_object(self, ray_o, ray_d):
        """Nearest object within the selection cone around the ray."""
        best = None
        best_dot = -2.0
        best_dist = float("inf")
        for name, node in self._objects.items():
            p = node.get_pos(self._render)
            v = (p[0] - ray_o[0], p[1] - ray_o[1], p[2] - ray_o[2])
            n = math.sqrt(sum(c * c for c in v))
            if n < 1e-9:
                continue
            dot = sum((a / n) * b for a, b in zip(v, ray_d))
            if dot > self._select_cos and (dot > best_dot or
                                           (dot == best_dot and
                                            n < best_dist)):
                best, best_dot, best_dist = name, dot, n
        return best

    # -- drag lifecycle -------------------------------------------------------
    def _target_node(self, key):
        if key == "stage":
            return self._stage
        return self._objects.get(key)

    def _begin_drag(self, gesture, ray_o, ray_d, fwd) -> None:
        from pointer import intersect_plane

        if self.mode == OBJECT:
            target = self.hover_target or self.selected
            if target is None or target not in self._objects:
                return  # grabbed empty space in object mode: ignore
            node = self._objects[target]
            plane_point = tuple(node.get_pos(self._render))
        else:
            target = "stage"
            node = self._stage
            # Camera-facing plane at a comfortable depth ahead of the
            # head -- never through the head itself (a plane containing
            # the ray origin intersects every ray at t=0).
            plane_point = (ray_o[0] + fwd[0] * STAGE_PLANE_DEPTH,
                           ray_o[1] + fwd[1] * STAGE_PLANE_DEPTH,
                           ray_o[2] + fwd[2] * STAGE_PLANE_DEPTH)
        if node is None:
            return
        plane = (plane_point, (-fwd[0], -fwd[1], -fwd[2]))
        hit = intersect_plane(ray_o, ray_d, *plane)
        if hit is None:
            return
        if math.hypot(hit[0] - ray_o[0], hit[1] - ray_o[1],
                      hit[2] - ray_o[2]) < MIN_GRAB_DISTANCE:
            return  # degenerate grab: too close to the eye
        self.grabbed = target
        self._drag_plane = plane
        self._grab_hit = hit
        parent = node.get_parent()
        self._start_pos = tuple(node.get_pos(parent))
        self._start_quat = self._quat_tuple(node.get_quat(parent))
        self._push_undo(target)

    def _continue_drag(self, ray_o, ray_d) -> None:
        from pointer import intersect_plane

        assert self.grabbed is not None and self._drag_plane is not None
        node = self._target_node(self.grabbed)
        if node is None:
            self.grabbed = None
            return
        hit = intersect_plane(ray_o, ray_d, *self._drag_plane)
        if hit is None or self._grab_hit is None:
            return  # parallel/behind: freeze, do not move
        dx = [(h - g) * self.sensitivity
              for h, g in zip(hit, self._grab_hit)]
        parent = node.get_parent()
        try:
            move = parent.get_relative_vector(self._render, tuple(dx))
        except Exception:
            return
        node.set_pos(parent,
                     self._start_pos[0] + move[0],
                     self._start_pos[1] + move[1],
                     self._start_pos[2] + move[2])

    def _end_drag(self) -> None:
        self.grabbed = None
        self._drag_plane = None
        self._grab_hit = None

    @staticmethod
    def _quat_tuple(q):
        """LQuaternionf -> (w, x, y, z) tuple."""
        return (q.get_w(), q.get_x(), q.get_y(), q.get_z())

    @staticmethod
    def _set_node_quat(node, parent, quat) -> None:
        from panda3d.core import LQuaternionf

        w, x, y, z = quat
        node.set_quat(parent, LQuaternionf(x, y, z, w))

    def _cancel_drag(self) -> None:
        if self.grabbed is None:
            return
        node = self._target_node(self.grabbed)
        if node is not None and self._start_pos is not None:
            parent = node.get_parent()
            node.set_pos(parent, *self._start_pos)
            if self._start_quat is not None:
                self._set_node_quat(node, parent, self._start_quat)
        # Cancel rewinds to (and including) the grab entry.
        while self._undo and self._undo[-1][0] != "grab":
            self._undo.pop()
        if self._undo:
            self._undo.pop()
        self._end_drag()

    # -- undo / reset ---------------------------------------------------------
    def _push_undo(self, target, origin="op") -> None:
        node = self._target_node(target)
        parent = node.get_parent()
        self._undo.append((origin, target, tuple(node.get_pos(parent)),
                           self._quat_tuple(node.get_quat(parent))))
        if len(self._undo) > UNDO_DEPTH:
            self._undo.pop(0)

    def undo(self) -> bool:
        if not self._undo:
            return False
        _origin, target, pos, quat = self._undo.pop()
        node = self._target_node(target)
        if node is None:
            return False
        parent = node.get_parent()
        node.set_pos(parent, *pos)
        self._set_node_quat(node, parent, quat)
        if self.grabbed == target:
            self._end_drag()
        return True

    def reset_stage(self) -> None:
        node = self._stage
        parent = node.get_parent()
        self._push_undo("stage", "reset")
        node.set_pos(parent, 0.0, 0.0, 0.0)
        self._set_node_quat(node, parent, (1.0, 0.0, 0.0, 0.0))
        if self.grabbed == "stage":
            self._end_drag()

    # -- keyboard nudging -------------------------------------------------------
    def nudge_selected(self, dx: float, dy: float, dz: float) -> bool:
        """Move the selection in view axes (right/up/forward), metres."""
        from pose_math import quat_rotate

        target = "stage" if self.mode == STAGE else self.selected
        if target is None:
            return False
        node = self._target_node(target)
        if node is None:
            return False
        q = self._head_quat
        right = quat_rotate(q, (1.0, 0.0, 0.0))
        up = quat_rotate(q, (0.0, 1.0, 0.0))
        back = quat_rotate(q, (0.0, 0.0, 1.0))
        # GL -> Panda world mapping.
        def conv(v):
            return (v[0], -v[2], v[1])
        right, up, back = conv(right), conv(up), conv(back)
        delta = (dx * right[0] + dy * up[0] + dz * back[0],
                 dx * right[1] + dy * up[1] + dz * back[1],
                 dx * right[2] + dy * up[2] + dz * back[2])
        parent = node.get_parent()
        try:
            move = parent.get_relative_vector(self._render, delta)
        except Exception:
            return False
        self._push_undo(target)
        p = node.get_pos(parent)
        node.set_pos(parent, p[0] + move[0], p[1] + move[1], p[2] + move[2])
        return True

    def yaw_selected(self, degrees: float) -> bool:
        target = "stage" if self.mode == STAGE else self.selected
        if target is None:
            return False
        node = self._target_node(target)
        if node is None:
            return False
        parent = node.get_parent()
        try:
            h, p, r = node.get_hpr(parent)
        except Exception:
            return False
        self._push_undo(target)
        node.set_hpr(parent, h + degrees, p, r)
        return True

    # -- helpers ------------------------------------------------------------------
    def _to_panda_ray(self, ray):
        """GL-frame ray -> Panda world ray (render frame)."""
        (ox, oy, oz), (dx, dy, dz) = ray
        return (ox, -oz, oy), (dx, -dz, dy)
