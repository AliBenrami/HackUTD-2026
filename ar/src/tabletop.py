"""Tabletop AR anchoring on the physical table surface.

Frames (all right-handed):
  W = VIO world frame (GL: x right, y up, z backward). Head poses from
      the SDK live here. Persistent across a session; reset by VIO
      origin changes (recenter / tracking loss).
  H = headset (body) frame. SDK pose is T_W_H (body-to-world).
  C = RGB camera frame (OpenCV: x right, y down, z forward).
  T = tabletop frame, anchored by the printed marker. x = marker-right,
      y = marker-up direction on the table, z = table normal (up).
      The marker sits centred on the table unless table_offset is set.

The anchor chain is::

    T_W_T = T_W_H @ T_H_C @ T_C_M

  T_W_H : 6DoF VIO pose (live head tracking, interpolated to the
           camera frame timestamp).
  T_H_C : camera-to-head extrinsics. Calibrated via hand-eye
           (see solve_hand_eye) or approximate fallback
           (identity rotation with GL<->OpenCV axis flip, zero
           translation -- EXPLICITLY labelled approximate).
  T_C_M : marker pose from solvePnP (IPPE_SQUARE when available).

All transforms are stored as (pos, quat) with pos a 3-tuple in metres
and quat a Hamilton (w, x, y, z) body-to-world quaternion. Numpy is
used internally for hand-eye only; the hot path is pure stdlib.

Nothing here touches Panda3D or the display: the app maps the anchor
into gl_space itself (table_root.set_pos/set_quat with the GL values).
"""

from __future__ import annotations

import collections
import json
import math
import os
import statistics
import sys
import threading
import time

import pose_math

# ---------------------------------------------------------------------------
# Small rigid-body helpers (GL frame, Hamilton quats, row-major matrices)


def quat_normalize(q):
    w, x, y, z = q
    n = math.sqrt(w * w + x * x + y * y + z * z)
    if n < 1e-12:
        return (1.0, 0.0, 0.0, 0.0)
    return (w / n, x / n, y / n, z / n)


def quat_conjugate(q):
    w, x, y, z = q
    return (w, -x, -y, -z)


def quat_from_mat3(m):
    """Row-major 3x3 rotation -> Hamilton quat (inverse of quat_to_mat3).

    m is row-major with v' = v M (pose_math convention). We run
    Shepperd's method on C = M^T (column-major, p' = C p):
      tr>0: w=sqrt(1+tr)/2, x=(C21-C12)/4w, y=(C02-C20)/4w, z=(C10-C01)/4w
    with C[i][j] = m[3*j+i], then normalize.
    """
    # Column-major entries of C = M^T.
    c00, c10, c20 = m[0], m[1], m[2]
    c01, c11, c21 = m[3], m[4], m[5]
    c02, c12, c22 = m[6], m[7], m[8]
    tr = c00 + c11 + c22
    if tr > 0.0:
        s = 0.5 / math.sqrt(tr + 1.0)  # 1/(4w)
        w = 0.25 / s
        x = (c21 - c12) * s
        y = (c02 - c20) * s
        z = (c10 - c01) * s
    elif c00 > c11 and c00 > c22:
        s = 2.0 * math.sqrt(1.0 + c00 - c11 - c22)  # 4x
        w = (c21 - c12) / s
        x = 0.25 * s
        y = (c01 + c10) / s
        z = (c02 + c20) / s
    elif c11 > c22:
        s = 2.0 * math.sqrt(1.0 + c11 - c00 - c22)  # 4y
        w = (c02 - c20) / s
        x = (c01 + c10) / s
        y = 0.25 * s
        z = (c12 + c21) / s
    else:
        s = 2.0 * math.sqrt(1.0 + c22 - c00 - c11)  # 4z
        w = (c10 - c01) / s
        x = (c02 + c20) / s
        y = (c12 + c21) / s
        z = 0.25 * s
    return quat_normalize((w, x, y, z))


def quat_angle_between(a, b):
    """Smallest rotation angle (rad) between two unit quats."""
    dot = abs(a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3])
    return 2.0 * math.acos(min(1.0, dot))


def quat_mean(quats):
    """Markley average of unit quats (dominant eigenvector of sum q q^T)."""
    # Power iteration is plenty for small, clustered sets.
    import numpy as np

    acc = np.zeros((4, 4))
    q0 = np.asarray(quats[0], dtype=float)
    for q in quats:
        q = np.asarray(q, dtype=float)
        if float(np.dot(q, q0)) < 0.0:
            q = -q
        acc = acc + np.outer(q, q)
    vals, vecs = np.linalg.eigh(acc)
    q = vecs[:, int(np.argmax(vals))]
    q = q / np.linalg.norm(q)
    return (float(q[0]), float(q[1]), float(q[2]), float(q[3]))


def rigid_mul(a_pos, a_quat, b_pos, b_quat):
    """Compose T_a @ T_b (apply b first, then a)."""
    p = pose_math.quat_rotate(a_quat, b_pos)
    return ((a_pos[0] + p[0], a_pos[1] + p[1], a_pos[2] + p[2]),
            pose_math.quat_mul(a_quat, b_quat))


def rigid_inv(pos, quat):
    """Inverse of a rigid transform."""
    qi = quat_conjugate(quat)
    p = pose_math.quat_rotate(qi, (-pos[0], -pos[1], -pos[2]))
    return (p, qi)


def rigid_apply(pos, quat, point):
    """Transform a point: p' = pos + quat * point."""
    r = pose_math.quat_rotate(quat, point)
    return (pos[0] + r[0], pos[1] + r[1], pos[2] + r[2])


def slerp(a, b, t):
    """Spherical interpolation of Hamilton unit quats."""
    dot = a[0] * b[0] + a[1] * b[1] + a[2] * b[2] + a[3] * b[3]
    b = tuple(b)
    if dot < 0.0:
        b = tuple(-x for x in b)
        dot = -dot
    dot = min(1.0, dot)
    if dot > 0.9995:
        out = tuple(x + t * (y - x) for x, y in zip(a, b))
        return quat_normalize(out)
    theta = math.acos(dot)
    s = math.sin(theta)
    wa = math.sin((1.0 - t) * theta) / s
    wb = math.sin(t * theta) / s
    out = tuple(wa * x + wb * y for x, y in zip(a, b))
    return quat_normalize(out)


# ---------------------------------------------------------------------------
# Frames

# OpenCV camera frame (x right, y DOWN, z forward) to GL frame
# (x right, y up, z backward): flip y and z. det = +1 (proper rotation).
F_CV2GL = (1.0, 0.0, 0.0,
           0.0, -1.0, 0.0,
           0.0, 0.0, -1.0)

GL_UP = (0.0, 1.0, 0.0)


def cv_pose_to_gl(rvec, tvec):
    """OpenCV (R, t) with x-right/y-down/z-forward -> GL (pos, quat).

    Column-vector convention: p_cam = R p_obj + t, where p_obj uses
    our authored object frame (x right, y up-in-plane, z normal).
    GL camera axes relate by p_gl = F p_cv with F = diag(1,-1,-1), so
    R_gl = F R and t_gl = F t. (Face-on upright marker gives R = F,
    hence R_gl = I, as it should.)
    """
    import numpy as np

    import cv2

    r = np.asarray(rvec, dtype=float).reshape(3)
    t = np.asarray(tvec, dtype=float).reshape(3)
    R_cv, _ = cv2.Rodrigues(r)
    F = np.diag([1.0, -1.0, -1.0])
    R_gl_col = F @ R_cv  # still column-vector convention
    # Convert to row-major (pose_math convention: v' = v * M).
    R_gl_row = tuple(float(v) for v in R_gl_col.T.reshape(-1))
    q = quat_from_mat3(R_gl_row)
    t_gl = tuple(float(v) for v in (F @ t))
    return t_gl, q


def marker_object_points(size_m):
    """4x3 object points for a square marker, TL/TR/BR/BL order.

    Matches the IPPE_SQUARE convention required by OpenCV and the
    corner order returned by ArUco detectMarkers. Frame: x right,
    y up-in-plane, z normal out of the table.
    """
    s = size_m / 2.0
    return [(-s, s, 0.0), (s, s, 0.0), (s, -s, 0.0), (-s, -s, 0.0)]


# ---------------------------------------------------------------------------
# TableAnchor: the persistent world-space tabletop pose


class TableAnchor:
    """World-space anchor for the physical tabletop (GL frame).

    tracking_state is one of UNINITIALIZED, ACQUIRING, LOCKED,
    DEGRADED, LOST, APPROX (approximate calibration in use).
    """

    def __init__(self, pos=(0.0, 0.0, 0.0), quat=(1.0, 0.0, 0.0, 0.0),
                 width_m=0.60, length_m=0.40):
        self.pos = tuple(pos)
        self.quat = quat_normalize(tuple(quat))
        self.width_m = float(width_m)
        self.length_m = float(length_m)
        self.confidence = 0.0
        self.tracking_state = "UNINITIALIZED"
        self.last_observed_at = 0.0
        self.obs_count = 0
        self.reproj_err_px = float("inf")

    # -- frame helpers (GL in, GL out) -------------------------------------
    def world_from_table(self, p):
        return rigid_apply(self.pos, self.quat, tuple(p))

    def table_from_world(self, p):
        ip, iq = rigid_inv(self.pos, self.quat)
        return rigid_apply(ip, iq, tuple(p))

    def normal_world(self):
        """Table normal (+Z local) expressed in world coords."""
        return pose_math.quat_rotate(self.quat, (0.0, 0.0, 1.0))

    def upright_error_rad(self):
        """Angle between table normal and world +Y (gravity-anchored up)."""
        n = self.normal_world()
        c = max(-1.0, min(1.0, n[1] / max(1e-12, math.sqrt(sum(v * v for v in n)))))
        return math.acos(c)

    def contains_xy(self, p, margin=0.0):
        """True if table-local (x, y) lies within the table rectangle."""
        x, y = p[0], p[1]
        return (abs(x) <= self.width_m / 2.0 + margin
                and abs(y) <= self.length_m / 2.0 + margin)

    def as_dict(self):
        return {"pos": list(self.pos), "quat": list(self.quat),
                "width_m": self.width_m, "length_m": self.length_m,
                "confidence": self.confidence,
                "tracking_state": self.tracking_state,
                "last_observed_at": self.last_observed_at,
                "obs_count": self.obs_count,
                "reproj_err_px": self.reproj_err_px}

    @classmethod
    def from_dict(cls, d):
        a = cls(tuple(d["pos"]), tuple(d["quat"]),
                d.get("width_m", 0.60), d.get("length_m", 0.40))
        a.confidence = float(d.get("confidence", 0.0))
        a.tracking_state = str(d.get("tracking_state", "UNINITIALIZED"))
        a.last_observed_at = float(d.get("last_observed_at", 0.0))
        a.obs_count = int(d.get("obs_count", 0))
        a.reproj_err_px = float(d.get("reproj_err_px", float("inf")))
        return a


# ---------------------------------------------------------------------------
# TimeSync: relate camera device timestamps to monotonic time

class TimeSync:
    """Estimate offset between camera device clock and time.monotonic().

    offset = median(arrival_mono - ts_sec) over a rolling window.
    to_mono() maps device timestamps into the monotonic domain.
    """

    def __init__(self, window: int = 30) -> None:
        self._pairs = collections.deque(maxlen=window)
        self._lock = threading.Lock()

    def feed(self, ts_ns: int, arrival_mono: float) -> None:
        if ts_ns and ts_ns > 0:
            with self._lock:
                self._pairs.append((float(ts_ns) * 1e-9, float(arrival_mono)))

    def offset(self):
        with self._lock:
            if len(self._pairs) < 3:
                return None
            offs = sorted(a - t for t, a in self._pairs)
        return offs[len(offs) // 2]

    def jitter(self):
        with self._lock:
            if len(self._pairs) < 3:
                return float("inf")
            offs = sorted(a - t for t, a in self._pairs)
        return offs[-1] - offs[0]

    def shared_clock_likely(self):
        """True when offset looks stable (same clock, fixed lag)."""
        off = self.offset()
        if off is None:
            return False
        return self.jitter() < 0.05

    def to_mono(self, ts_ns: int, arrival_mono: float):
        """Map a device timestamp to monotonic seconds."""
        off = self.offset()
        if off is None or not ts_ns:
            return arrival_mono  # documented fallback
        return float(ts_ns) * 1e-9 + off


# ---------------------------------------------------------------------------
# Head pose history with interpolation

class PoseHistory:
    """Thread-safe ring buffer of (mono_t, pos, quat, stable)."""

    def __init__(self, maxlen: int = 600) -> None:
        self._buf = collections.deque(maxlen=maxlen)
        self._lock = threading.Lock()

    def push(self, stamp: float, pos, quat, stable: bool) -> None:
        with self._lock:
            self._buf.append((float(stamp), tuple(pos), tuple(quat),
                              bool(stable)))

    def snapshot(self):
        with self._lock:
            return list(self._buf)

    def clear(self) -> None:
        with self._lock:
            self._buf.clear()

    def interpolate(self, t: float):
        """Pose at monotonic time t: (pos, quat, stable, extrapolated)."""
        with self._lock:
            buf = list(self._buf)
        if not buf:
            return None
        if t <= buf[0][0]:
            s = buf[0]
            return s[1], s[2], s[3], True
        if t >= buf[-1][0]:
            s = buf[-1]
            return s[1], s[2], s[3], True
        for i in range(len(buf) - 1):
            t0, p0, q0, s0 = buf[i][0], buf[i][1], buf[i][2], buf[i][3]
            t1, p1, q1, s1 = buf[i + 1][0], buf[i + 1][1], buf[i + 1][2], buf[i + 1][3]
            if t0 <= t <= t1:
                span = t1 - t0
                a = 0.0 if span <= 0.0 else (t - t0) / span
                pos = tuple(x0 + (x1 - x0) * a for x0, x1 in zip(p0, p1))
                quat = slerp(q0, q1, a)
                return pos, quat, (s0 and s1), False
        s = buf[-1]
        return s[1], s[2], s[3], True


# ---------------------------------------------------------------------------
# Marker pose estimation (OpenCV, IPPE_SQUARE with validation)

def estimate_marker_pose(corners_px, marker_size_m, K, dist, ippe=True):
    """Estimate marker pose from 4 ordered corners (TL,TR,BR,BL).

    Returns a list of dicts {rvec, tvec, reproj_err}, best first, or [].
    Uses IPPE_SQUARE (exact square prior) when available and numpy is
    present; else falls back to a single ITERATIVE solution flagged as
    ambiguous-unknown.
    """
    import numpy as np

    obj = np.array(marker_object_points(marker_size_m), dtype=np.float64)
    img = np.asarray(corners_px, dtype=np.float64).reshape(-1, 2)
    if img.shape != (4, 2):
        return []
    K = np.asarray(K, dtype=float).reshape(3, 3)
    dist = np.asarray(dist if dist is not None else [0, 0, 0, 0, 0],
                      dtype=float).reshape(-1)
    sols = []
    if ippe:
        try:
            import cv2

            n, rvecs, tvecs, errs = cv2.solvePnPGeneric(
                obj, img, K, dist, flags=cv2.SOLVEPNP_IPPE_SQUARE)
            for i in range(int(n)):
                r = np.asarray(rvecs[i], dtype=float).reshape(3)
                t = np.asarray(tvecs[i], dtype=float).reshape(3)
                e = float(np.asarray(errs[i]).reshape(-1)[0])
                sols.append({"rvec": r, "tvec": t, "reproj_err": e,
                             "method": "IPPE_SQUARE"})
        except Exception:
            sols = []
    if not sols:
        # Fallback: single ITERATIVE solution; ambiguity unknown.
        try:
            import cv2

            ok, rvec, tvec = cv2.solvePnP(obj, img, K, dist,
                                          flags=cv2.SOLVEPNP_ITERATIVE)
            if not ok:
                return []
            proj, _ = cv2.projectPoints(obj, rvec, tvec, K, dist)
            err = float(np.mean(np.linalg.norm(
                proj.reshape(-1, 2) - img, axis=1)))
            sols = [{"rvec": np.asarray(rvec).reshape(3),
                     "tvec": np.asarray(tvec).reshape(3),
                     "reproj_err": err,
                     "method": "ITERATIVE(fallback)"}]
        except Exception:
            return []
    sols.sort(key=lambda s: s["reproj_err"])
    return sols


# ---------------------------------------------------------------------------
# Calibration: intrinsics containers, hand-eye solver, file I/O

DEFAULT_TABLE_W_M = 0.60
DEFAULT_TABLE_L_M = 0.40
DEFAULT_MARKER_SIZE_M = 0.10
DEFAULT_MARKER_DICT = "DICT_6X6_250"
DEFAULT_MARKER_ID = 42


def approx_intrinsics(width: int, height: int, hfov_deg: float = 70.0):
    """Explicitly approximate pinhole model (unmarked lens, NO distortion).

    Marked APPROXIMATE everywhere it is used: fx from an assumed
    horizontal FOV, principal point at the image centre.
    """
    import math as _math

    fx = (width / 2.0) / _math.tan(_math.radians(hfov_deg) / 2.0)
    K = [[fx, 0.0, width / 2.0],
         [0.0, fx, height / 2.0],
         [0.0, 0.0, 1.0]]
    return {"K": K, "dist": [0.0, 0.0, 0.0, 0.0, 0.0],
            "width": width, "height": height,
            "method": f"approx-hfov-{hfov_deg}",
            "approx": True}


def load_calibration(path):
    """Load calibration JSON; returns dict (empty if missing/invalid)."""
    try:
        with open(path, "r") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def save_calibration(path, payload: dict) -> None:
    tmp = path + ".tmp"
    with open(tmp, "w") as f:
        json.dump(payload, f, indent=2)
    os.replace(tmp, path)


def solve_hand_eye(head_poses, marker_poses):
    """Solve T_head_cam from paired observations (Park-Martin, numpy).

    head_poses: list of (pos, quat) GL Hamilton = T_W_H.
    marker_poses: list of (R_col3x3, t) with p_cam = R p_obj + t,
      i.e. solvePnP output mapped to numpy column-major form.
    Returns ((pos, quat) T_H_C in GL/Hamilton, diagnostics dict).
    Raises ValueError on degenerate input.
    """
    import numpy as np

    if len(head_poses) != len(marker_poses):
        raise ValueError("head/marker pair count mismatch")
    n = len(head_poses)
    if n < 4:
        raise ValueError(f"need >= 4 pairs, have {n}")

    def h_to_col(pos, quat):
        # pose_math quat_to_mat3 is row-major; column-major = transpose.
        Rm = np.array(pose_math.quat_to_mat3(quat),
                      dtype=float).reshape(3, 3)
        return Rm.T.copy(), np.asarray(pos, dtype=float)

    G = [h_to_col(p, q) for p, q in head_poses]  # (R_W_H, t), col-major
    C = [(np.asarray(R, dtype=float).reshape(3, 3),
          np.asarray(t, dtype=float).reshape(3)) for R, t in marker_poses]

    def compose(Ra, ta, Rb, tb):
        return Ra @ Rb, Ra @ tb + ta

    def invert(R, t):
        Ri = R.T
        return Ri, -Ri @ t

    # Relative motions w.r.t. pair 0: A_i X = X B_i, where
    #   A_i = G_i^{-1} G_0  (relative gripper motion, base frame)
    #   B_i = C_i C_0^{-1}  (relative target motion, cam frame)
    # Derivation: G_0 X C_0 = G_i X C_i  =>  G_i^{-1} G_0 X = X C_i C_0^{-1}.
    A_R, A_t, B_R, B_t = [], [], [], []
    for i in range(1, n):
        Gi_R, Gi_t = invert(*G[i])
        Ra, ta = compose(Gi_R, Gi_t, *G[0])
        Rb, tb = compose(*C[i], *invert(*C[0]))
        # Skip near-identity motions (no information).
        ang_a = math.acos(min(1.0, max(-1.0, (np.trace(Ra) - 1.0) / 2.0)))
        ang_b = math.acos(min(1.0, max(-1.0, (np.trace(Rb) - 1.0) / 2.0)))
        if ang_a < math.radians(2.0) and np.linalg.norm(ta) < 0.01:
            continue
        A_R.append(Ra)
        A_t.append(ta)
        B_R.append(Rb)
        B_t.append(tb)
    m = len(A_R)
    if m < 3:
        raise ValueError(f"only {m} informative motions (need >= 3)")

    # Rotation: nullspace of stacked [kron(I, R_A) - kron(R_B^T, I)].
    # (vec identity: vec(R_A R_X) = vec(R_X R_B).)
    rows = []
    I3 = np.eye(3)
    for Ra, Rb in zip(A_R, B_R):
        rows.append(np.kron(I3, Ra) - np.kron(Rb.T, I3))
    M = np.vstack(rows)
    _, S_sv, Vt = np.linalg.svd(M)
    # Rotation needs a 1-D nullspace: motions about a single axis (or
    # pure translations) leave extra degrees unobservable. S[-2] ~ 0
    # means degenerate geometry -- refuse rather than return garbage.
    if S_sv[-2] < 1e-6:
        raise ValueError(
            "degenerate hand-eye motions (single-axis or too small); "
            "move the head through diverse rotations")
    x = Vt[-1, :]
    Rx = x.reshape(3, 3, order="F")  # column-stacking vec convention
    # Nullspace sign is arbitrary: -Rx is an equally valid null vector
    # but (as a reflection, det<0) orthonormalizes to a rotation 180 deg
    # off. The true solution scaled positively has det>0, so flip first.
    if np.linalg.det(Rx) < 0.0:
        Rx = -Rx
    # Orthonormalize (nearest rotation).
    U, _, Vt2 = np.linalg.svd(Rx)
    R = U @ Vt2
    if np.linalg.det(R) < 0.0:
        # Should not happen after the sign fix; bail rather than
        # silently returning a wrong rotation.
        raise ValueError("hand-eye rotation solve is degenerate")

    # Translation: (R_A - I) t_X = R_X t_B - t_A, stacked least squares.
    Ar, br = [], []
    for Ra, ta, Rb, tb in zip(A_R, A_t, B_R, B_t):
        Ar.append(Ra - np.eye(3))
        br.append(R @ tb - ta)
    Ar = np.vstack(Ar)
    br = np.concatenate(br)
    t, _, _, _ = np.linalg.lstsq(Ar, br, rcond=None)

    # Diagnostics: mean rotation + translation residuals.
    rot_err, tr_err = [], []
    for Ra, ta, Rb, tb in zip(A_R, A_t, B_R, B_t):
        dR = (Ra @ R).T @ (R @ Rb)
        rot_err.append(math.degrees(math.acos(
            min(1.0, max(-1.0, (np.trace(dR) - 1.0) / 2.0)))))
        tr_err.append(float(np.linalg.norm((Ra - np.eye(3)) @ t
                                          - (R @ tb - ta))))
    diag = {"pairs": n, "motions": m,
            "rot_resid_deg_mean": float(np.mean(rot_err)),
            "trans_resid_m_mean": float(np.mean(tr_err))}

    # Convert to GL (pos, Hamilton quat): row-major = transpose.
    R_row = tuple(float(v) for v in R.T.reshape(-1))
    q = quat_from_mat3(R_row)
    pos = tuple(float(v) for v in t)
    return (pos, q), diag


# ---------------------------------------------------------------------------
# TableCalibrator: acquire a validated anchor from live observations

class TableCalibrator:
    """Collect validated marker observations; lock a robust anchor.

    An observation is (head_pos, head_quat, rvec, tvec, reproj_err,
    frame_ts_mono). Each is validated (reprojection, gravity alignment,
    plausible distance); inliers accumulate in a window and the anchor
    locks once enough mutually-consistent samples exist.
    """

    def __init__(self, marker_size_m=DEFAULT_MARKER_SIZE_M,
                 table_w=DEFAULT_TABLE_W_M, table_l=DEFAULT_TABLE_L_M,
                 required=12, window_s=10.0, max_reproj_px=2.0,
                 max_gravity_deg=25.0, pos_gate_m=0.05, ang_gate_deg=10.0,
                 min_distance_m=0.3, max_distance_m=3.0):
        self.marker_size_m = float(marker_size_m)
        self.table_w = float(table_w)
        self.table_l = float(table_l)
        self.required = int(required)
        self.window_s = float(window_s)
        self.max_reproj_px = float(max_reproj_px)
        self.max_gravity_rad = math.radians(float(max_gravity_deg))
        self.pos_gate_m = float(pos_gate_m)
        self.ang_gate_rad = math.radians(float(ang_gate_deg))
        self.min_distance_m = float(min_distance_m)
        self.max_distance_m = float(max_distance_m)
        # (pos, quat, reproj, stamp, head_pos, head_quat)
        self._window: list = []
        self.locked_anchor: TableAnchor | None = None
        self.outliers = 0
        self.last_reject_reason = ""
        # hand-eye collection: list of (head_pos, head_quat, R_C_M, t_C_M)
        self._he_pairs: list = []
        self._he_last: tuple | None = None
        self.hand_eye = None  # (pos, quat) T_H_C or None
        self.hand_eye_diag: dict = {}

    def reset(self) -> None:
        self._window = []
        self.locked_anchor = None
        self.outliers = 0
        self.last_reject_reason = ""

    def reset_handeye(self) -> None:
        self._he_pairs = []
        self._he_last = None
        self.hand_eye = None
        self.hand_eye_diag = {}

    @property
    def count(self):
        return len(self._window)

    def best_estimate(self):
        """Median accepted observation: {pos, quat, reproj, stamp, count}."""
        med = self._window_median()
        if med is None:
            return None
        mpos, mquat = med
        errs = [e["reproj"] for e in self._window]
        return {"pos": mpos, "quat": mquat,
                "reproj": float(sum(errs) / len(errs)),
                "stamp": self._window[-1]["stamp"],
                "count": len(self._window)}

    def observe(self, head_pos, head_quat, rvec, tvec, reproj_err,
                stamp, hand_eye, approx_ok=True):
        """Feed one detection. Returns ("accepted"|reason, anchor|None).

        hand_eye = (pos, quat) T_H_C in GL (calibrated or approximate).
        """
        import numpy as np

        # 1. reprojection gate.
        if not (reproj_err <= self.max_reproj_px):
            self.last_reject_reason = "reproj"
            self.outliers += 1
            return "reject-reproj", self.locked_anchor
        # 2. Build T_W_T candidate: T_W_T = T_W_H @ T_H_C @ T_C_M.
        R_cv, _ = _rodrigues(rvec)
        t_cv = np.asarray(tvec, dtype=float).reshape(3)
        dist = float(np.linalg.norm(t_cv))
        if not (self.min_distance_m <= dist <= self.max_distance_m):
            self.last_reject_reason = "distance"
            self.outliers += 1
            return "reject-distance", self.locked_anchor
        q_cm = quat_from_mat3(tuple(
            float(v) for v in np.asarray(R_cv).reshape(3, 3).T.reshape(-1)))
        # NOTE: R_cv from Rodrigues is column-major; quat_from_mat3
        # expects row-major (pose_math convention), hence transpose.
        q_hc = hand_eye[1]
        t_hc = hand_eye[0]
        p1 = pose_math.quat_rotate(q_hc, tuple(float(v) for v in t_cv))
        p1 = (t_hc[0] + p1[0], t_hc[1] + p1[1], t_hc[2] + p1[2])
        q1 = pose_math.quat_mul(q_hc, q_cm)
        pos = pose_math.quat_rotate(quat_normalize(head_quat), p1)
        pos = (head_pos[0] + pos[0], head_pos[1] + pos[1],
               head_pos[2] + pos[2])
        quat = quat_normalize(pose_math.quat_mul(
            quat_normalize(head_quat), q1))

        # 3. gravity check: table normal (+Z local) must be ~world +Y.
        nw = pose_math.quat_rotate(quat, (0.0, 0.0, 1.0))
        nn = math.sqrt(sum(v * v for v in nw))
        if nn < 1e-9:
            self.last_reject_reason = "gravity"
            self.outliers += 1
            return "reject-gravity", self.locked_anchor
        if math.acos(max(-1.0, min(1.0, nw[1] / nn))) > self.max_gravity_rad:
            self.last_reject_reason = "gravity"
            self.outliers += 1
            return "reject-gravity", self.locked_anchor

        # 4. consistency vs running window (anchor stability gate).
        # In APPROX mode (uncalibrated extrinsics) multi-view observations
        # are systematically biased: relax the gates so the anchor keeps
        # tracking instead of freezing at the first lock pose.
        if approx_ok:
            pos_gate = max(self.pos_gate_m, 0.12)
            ang_gate = max(self.ang_gate_rad, math.radians(20.0))
            shape_pos, shape_ang = 0.05, math.radians(10.0)
        else:
            pos_gate = self.pos_gate_m
            ang_gate = self.ang_gate_rad
            shape_pos, shape_ang = 0.02, math.radians(5.0)
        if self._window and not self._consistent(pos, quat, pos_gate,
                                                 ang_gate):
            self.last_reject_reason = "inconsistent"
            self.outliers += 1
            return "reject-inconsistent", self.locked_anchor

        self._window.append({"pos": pos, "quat": quat,
                             "reproj": float(reproj_err), "stamp": stamp})
        # Prune by time.
        cutoff = stamp - self.window_s
        self._window = [e for e in self._window if e["stamp"] >= cutoff]
        if len(self._window) >= self.required and self._locked_shape_ok(
                shape_pos, shape_ang):
            self._lock_anchor(stamp, approx_ok)
        return "accepted", self.locked_anchor

    def _consistent(self, pos, quat, pos_gate, ang_gate) -> bool:
        med = self._window_median()
        if med is None:
            return True
        mpos, mquat = med
        d = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, mpos)))
        if d > pos_gate:
            return False
        if quat_angle_between(quat, mquat) > ang_gate:
            return False
        return True

    def _window_median(self):
        if not self._window:
            return None
        xs = sorted(e["pos"][0] for e in self._window)
        ys = sorted(e["pos"][1] for e in self._window)
        zs = sorted(e["pos"][2] for e in self._window)
        n = len(self._window)
        mid = n // 2
        if n % 2 == 1:
            med = (xs[mid], ys[mid], zs[mid])
        else:
            med = ((xs[mid - 1] + xs[mid]) / 2.0,
                   (ys[mid - 1] + ys[mid]) / 2.0,
                   (zs[mid - 1] + zs[mid]) / 2.0)
        return med, quat_mean([e["quat"] for e in self._window])

    def _locked_shape_ok(self, shape_pos=0.02, shape_ang=None) -> bool:
        if shape_ang is None:
            shape_ang = math.radians(5.0)
        med = self._window_median()
        if med is None:
            return False
        mpos, mquat = med
        max_dp = 0.0
        max_da = 0.0
        for e in self._window:
            max_dp = max(max_dp, math.sqrt(sum(
                (a - b) ** 2 for a, b in zip(e["pos"], mpos))))
            max_da = max(max_da, quat_angle_between(e["quat"], mquat))
        return max_dp <= shape_pos and max_da <= shape_ang

    def _lock_anchor(self, stamp, approx_ok):
        import numpy as np

        med = self._window_median()
        assert med is not None
        mpos, mquat = med
        errs = [e["reproj"] for e in self._window]
        spread = max(math.sqrt(sum(
            (a - b) ** 2 for a, b in zip(e["pos"], mpos)))
            for e in self._window)
        conf = max(0.0, min(1.0, 1.0 - spread / 0.05)) * 0.6 + 0.4 * min(
            1.0, len(self._window) / max(1, self.required))
        anchor = TableAnchor(mpos, mquat, self.table_w, self.table_l)
        anchor.confidence = conf
        anchor.tracking_state = "LOCKED" if not approx_ok else "APPROX"
        anchor.last_observed_at = stamp
        anchor.obs_count = len(self._window)
        anchor.reproj_err_px = float(np.mean(errs))
        self.locked_anchor = anchor

    # -- hand-eye collection -------------------------------------------------
    def collect_handeye(self, head_pos, head_quat, rvec, tvec,
                        min_trans_m=0.05, min_rot_deg=10.0) -> bool:
        """Store a (head pose, marker pose) pair if it adds viewpoint.

        Returns True when the pair was kept.
        """
        import numpy as np

        R_cv, _ = _rodrigues(rvec)
        t_cv = tuple(float(v) for v in np.asarray(tvec).reshape(3))
        R_cv = tuple(float(v) for v in np.asarray(R_cv).reshape(-1))
        if self._he_last is not None:
            lp, lq = self._he_last
            dp = math.sqrt(sum((a - b) ** 2 for a, b in zip(head_pos, lp)))
            da = math.degrees(quat_angle_between(
                quat_normalize(head_quat), lq))
            if dp < min_trans_m and da < min_rot_deg:
                return False
        self._he_pairs.append((tuple(head_pos),
                              quat_normalize(tuple(head_quat)),
                              R_cv, t_cv))
        self._he_last = (tuple(head_pos), quat_normalize(tuple(head_quat)))
        return True

    @property
    def handeye_count(self) -> int:
        return len(self._he_pairs)

    def solve_hand_eye(self):
        """Solve T_H_C from collected pairs. Returns ((pos, quat), diag)."""
        if len(self._he_pairs) < 4:
            raise ValueError(
                f"need >= 4 hand-eye pairs, have {len(self._he_pairs)}")
        heads = [(p, q) for (p, q, _R, _t) in self._he_pairs]
        marks = [(R, t) for (_p, _q, R, t) in self._he_pairs]
        (pos, quat), diag = solve_hand_eye(heads, marks)
        self.hand_eye = (pos, quat)
        self.hand_eye_diag = diag
        return (pos, quat), diag


def _rodrigues(rvec):
    """cv2.Rodrigues wrapper returning (3x3 np array, jacobian-or-None)."""
    import cv2
    import numpy as np

    R, _ = cv2.Rodrigues(np.asarray(rvec, dtype=float).reshape(3, 1))
    return R, None


# ---------------------------------------------------------------------------
# TableTracker: runtime anchor state machine

# (anchor-independent constants; thresholds documented in AR_POC.md)
ADJUST_POS_M = 0.03       # below: small damped correction
ADJUST_ANG_DEG = 3.0
SNAP_POS_M = 0.15         # below: snap (relocalization); above: outlier
SNAP_ANG_DEG = 15.0
LOST_JUMP_POS_M = 0.5     # unexplained head jump -> LOST
LOST_JUMP_ANG_DEG = 60.0
LOST_TIMEOUT_S = 10.0     # no observations while unstable -> LOST
DEGRADED_AFTER_S = 1.0    # no observations while stable -> DEGRADED
RELOCK_CONSECUTIVE = 5    # consistent outliers before relock attempt
CORRECT_GAIN = 0.35       # complementary-filter gain for small residuals


class TableTracker:
    """Owns the live anchor: correct, relocalize, freeze, or lose it.

    Feed update() every frame with the current head pose; feed accepted
    marker observations via observe_marker(). Never moves the anchor on
    a single frame: residuals below ADJUST_* get a damped correction,
    residuals below SNAP_* snap (logged, single step), anything larger
    is an outlier until RELOCK_CONSECUTIVE consistent samples arrive.
    """

    def __init__(self, table_w=DEFAULT_TABLE_W_M,
                 table_l=DEFAULT_TABLE_L_M) -> None:
        self.anchor = TableAnchor((0, 0, 0), (1, 0, 0, 0),
                                  table_w, table_l)
        self.state = "UNINITIALIZED"
        self.last_correction_m = 0.0
        self.last_correction_deg = 0.0
        self.last_residual_m = 0.0
        self.last_residual_deg = 0.0
        self.last_relock_at = 0.0
        self._last_head = None       # (pos, quat, stable, stamp)
        self._outlier_streak = 0
        self._outlier_cluster: list = []
        self._last_seen_marker_at = 0.0
        self._last_unstable_at = 0.0

    @property
    def has_anchor(self) -> bool:
        return self.state in ("LOCKED", "DEGRADED", "APPROX")

    def note_head_pose(self, pos, quat, stable: bool, stamp: float) -> None:
        """Feed every frame; detects unexplained jumps (VIO reset)."""
        cur = (tuple(pos), quat_normalize(tuple(quat)), bool(stable),
               float(stamp))
        prev = self._last_head
        self._last_head = cur
        if prev is None or self.state == "UNINITIALIZED":
            return
        ppos, pquat, pstable, pstamp = prev
        dt = stamp - pstamp
        if dt <= 0.0 or dt > 0.5 or not pstable or not stable:
            return
        dp = math.sqrt(sum((a - b) ** 2 for a, b in zip(pos, ppos)))
        da = math.degrees(quat_angle_between(
            quat_normalize(quat), pquat))
        if dp > LOST_JUMP_POS_M or da > LOST_JUMP_ANG_DEG:
            # Unexplained teleport: do not trust the old world frame.
            self._lose_anchor(
                f"head jump {dp:.2f}m/{da:.1f}deg in {dt * 1000:.0f}ms")

    def note_origin_reset(self, old_pos=None, old_quat=None) -> None:
        """Called when the app recenters (VIO origin changes).

        If the pre-reset head pose is given, the anchor is carried into
        the new frame (position + yaw only; pitch/roll are gravity-owned
        and unchanged). Otherwise the anchor is marked LOST.
        """
        if (old_pos is not None and old_quat is not None
                and self.has_anchor):
            # T_new = T_new_old @ T_old, where T_new_old undoes the head
            # pose at reset time (position + yaw component only).
            yaw = _yaw_only_quat(old_quat)
            t_inv_pos, t_inv_quat = rigid_inv(tuple(old_pos), yaw)
            p, q = rigid_mul(t_inv_pos, t_inv_quat,
                             self.anchor.pos, self.anchor.quat)
            self.anchor.pos = p
            self.anchor.quat = q
            self.anchor.tracking_state = self.state
            self.anchor.last_observed_at = time.monotonic()
            self._outlier_streak = 0
            self._outlier_cluster = []
            # Drop the pre-reset head baseline: the next pose lives in the
            # new world frame and must not compare against the old one.
            self._last_head = None
            print("[table] anchor carried across origin reset", file=sys.stderr)
        elif self.has_anchor:
            self._lose_anchor("origin reset without known transform")

    def _lose_anchor(self, why: str) -> None:
        print(f"[table] anchor LOST ({why}); frozen, needs relocalization",
              file=sys.stderr)
        self.state = "LOST"
        self.anchor.tracking_state = "LOST"
        self._outlier_streak = 0
        self._outlier_cluster = []

    def observe_marker(self, world_pos, world_quat, reproj_err: float,
                       stamp: float, stable: bool, approx: bool):
        """Consume one validated T_W_T observation from the calibrator.

        Called with the calibrator's current best estimate (median of
        its accepted window) whenever a fresh accepted frame exists.
        """
        if not self.has_anchor and self.state not in ("UNINITIALIZED", "LOST"):
            return
        if self.state in ("UNINITIALIZED", "LOST"):
            # Acquisition / reacquisition path: adopt once plausible.
            self.anchor.pos = tuple(world_pos)
            self.anchor.quat = quat_normalize(tuple(world_quat))
            self.anchor.confidence = 0.5 if approx else 0.7
            self.anchor.tracking_state = "APPROX" if approx else "LOCKED"
            self.anchor.last_observed_at = stamp
            self.anchor.obs_count += 1
            self.anchor.reproj_err_px = float(reproj_err)
            self.state = self.anchor.tracking_state
            print(f"[table] anchor acquired ({self.state}) "
                  f"conf={self.anchor.confidence:.2f}", file=sys.stderr)
            return

        # Residual of the observation against the live anchor.
        dp = math.sqrt(sum((a - b) ** 2
                           for a, b in zip(world_pos, self.anchor.pos)))
        da = math.degrees(quat_angle_between(world_quat, self.anchor.quat))
        self.last_residual_m = dp
        self.last_residual_deg = da
        self._last_seen_marker_at = stamp

        adjust_pm = ADJUST_POS_M
        adjust_am = math.radians(ADJUST_ANG_DEG)
        if dp <= adjust_pm and da <= math.degrees(adjust_am):
            # Small residual: damped correction (complementary filter).
            k = CORRECT_GAIN
            p = tuple(a + (b - a) * k
                      for a, b in zip(self.anchor.pos, world_pos))
            q = slerp(self.anchor.quat, quat_normalize(world_quat), k)
            self.anchor.pos = p
            self.anchor.quat = q
            self.last_correction_m = dp * k
            self.last_correction_deg = da * k
            self._outlier_streak = 0
            self._outlier_cluster = []
            self._recover_if_degraded(stamp, stable, approx)
        elif dp <= SNAP_POS_M and da <= SNAP_ANG_DEG:
            # Medium residual: snap (logged, single step).
            self.anchor.pos = tuple(world_pos)
            self.anchor.quat = quat_normalize(tuple(world_quat))
            self.last_correction_m = dp
            self.last_correction_deg = da
            self._outlier_streak = 0
            self._outlier_cluster = []
            print(f"[table] anchor snapped: residual "
                  f"{dp * 1000:.1f}mm {da:.2f}deg", file=sys.stderr)
            self._recover_if_degraded(stamp, stable, approx)
        else:
            # Large single-frame jump: outlier until proven otherwise.
            self._outlier_streak += 1
            self._outlier_cluster.append((tuple(world_pos),
                                          quat_normalize(tuple(world_quat))))
            if len(self._outlier_cluster) > RELOCK_CONSECUTIVE:
                self._outlier_cluster.pop(0)
            if self._outlier_streak >= RELOCK_CONSECUTIVE:
                self._relock_from_cluster(stamp, approx)

    def _recover_if_degraded(self, stamp, stable: bool, approx: bool) -> None:
        """Fresh agreeing observations heal DEGRADED back to live."""
        if self.state == "DEGRADED" and stable:
            self.state = "APPROX" if approx else "LOCKED"
            self.anchor.tracking_state = self.state
            self.anchor.last_observed_at = stamp
            print(f"[table] anchor recovered ({self.state})", file=sys.stderr)

    def _relock_from_cluster(self, stamp, approx: bool) -> None:
        cluster = self._outlier_cluster[-RELOCK_CONSECUTIVE:]
        ps = [p for p, _q in cluster]
        mean = tuple(sum(v[i] for v in ps) / len(ps) for i in range(3))
        spread = max(math.sqrt(sum((a - b) ** 2 for a, b in zip(p, mean)))
                     for p in ps)
        qs = [q for _p, q in cluster]
        qmean = quat_mean(qs)
        maxang = max(math.degrees(quat_angle_between(q, qmean)) for q in qs)
        if spread <= 0.05 and maxang <= 5.0:
            # No-op guard: a frozen estimator feeds identical samples;
            # "relocking" onto the live pose is noise, not recovery.
            dp = math.sqrt(sum((a - b) ** 2
                               for a, b in zip(mean, self.anchor.pos)))
            da = math.degrees(quat_angle_between(qmean, self.anchor.quat))
            if dp < 0.001 and da < 0.1:
                self._outlier_streak = 0
                self._outlier_cluster = []
                return
            self.anchor.pos = mean
            self.anchor.quat = qmean
            self.anchor.last_observed_at = stamp
            self.anchor.obs_count += len(cluster)
            self.state = "APPROX" if approx else "LOCKED"
            self.anchor.tracking_state = self.state
            print("[table] anchor relocked on consistent cluster "
                  f"(spread {spread * 1000:.1f}mm, {maxang:.1f}deg)",
                  file=sys.stderr)
        self._outlier_streak = 0
        self._outlier_cluster = []

    def mark_seen(self, stamp: float, stable: bool) -> None:
        """Called each frame: handles DEGRADED/LOST timeouts."""
        if stable:
            if stamp - self._last_seen_marker_at > DEGRADED_AFTER_S:
                if self.state == "LOCKED":
                    self.state = "DEGRADED"
                    self.anchor.tracking_state = "DEGRADED"
            if stamp - self._last_seen_marker_at > LOST_TIMEOUT_S:
                if self.state in ("LOCKED", "DEGRADED"):
                    self._lose_anchor(
                        f"no marker for {LOST_TIMEOUT_S:.0f}s")
        else:
            # Tracking itself unstable: freeze, flag degraded.
            if self.state == "LOCKED":
                self.state = "DEGRADED"
                self.anchor.tracking_state = "DEGRADED"


def _yaw_only_quat(q):
    """Project a Hamilton quat onto yaw-about-+Y (GL up)."""
    f = pose_math.quat_rotate(quat_normalize(q), (0.0, 0.0, -1.0))
    yaw = math.atan2(-f[0], -f[2])
    hy = yaw / 2.0
    return (math.cos(hy), 0.0, math.sin(hy), 0.0)


# ---------------------------------------------------------------------------
# Marker detector worker (own thread, non-blocking mailbox)

class MarkerDetector:
    """Detect ArUco markers on a worker thread; latest-only output.

    Feed with JPEG frames via submit(); take() returns the newest
    detection dict or None (never blocks, never queues).
    Detection dict: {"corners": [(x, y)x4] ordered TL,TR,BR,BL,
    "marker_id": int, "img_w": int, "img_h": int, "seq": int,
    "ts_ns": int, "arrival_mono": float}.
    """

    def __init__(self, aruco_dict_name=DEFAULT_MARKER_DICT,
                 marker_id=DEFAULT_MARKER_ID,
                 min_interval_s: float = 0.0) -> None:
        self.aruco_dict_name = aruco_dict_name
        self.marker_id = int(marker_id)
        self.min_interval_s = float(min_interval_s)
        self._lock = threading.Lock()
        self._pending = None
        self._latest = None
        self._seq_seen = -1
        self._seq_done = -1
        self._frames_seen = 0
        self._frames_done = 0
        self._last_process_t = 0.0
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._detector = None

    @property
    def frames_seen(self):
        with self._lock:
            return self._frames_seen

    @property
    def frames_done(self):
        with self._lock:
            return self._frames_done

    def start(self) -> None:
        import cv2

        aruco = cv2.aruco
        name = getattr(aruco, self.aruco_dict_name, None)
        if name is None:
            raise RuntimeError(
                f"unknown aruco dict {self.aruco_dict_name!r}")
        dictionary = aruco.getPredefinedDictionary(name)
        params = aruco.DetectorParameters()
        self._detector = aruco.ArucoDetector(dictionary, params)
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._worker,
                                        name="table-detect", daemon=True)
        self._thread.start()

    def submit(self, jpeg: bytes, w: int, h: int, seq: int, ts_ns: int,
               arrival_mono: float) -> bool:
        """Offer a frame; False if the worker is busy (frame dropped)."""
        with self._lock:
            if self._pending is not None:
                return False
            self._pending = (jpeg, w, h, seq, ts_ns, arrival_mono)
            self._frames_seen += 1
            return True

    def take(self):
        """Newest detection dict or None (non-blocking, drains)."""
        with self._lock:
            d = self._latest
            self._latest = None
            return d

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
            self._thread = None
        self._detector = None

    def _worker(self) -> None:
        import time as _time

        import cv2
        import numpy as np

        while not self._stop_event.is_set():
            with self._lock:
                job = self._pending
                self._pending = None
            if job is None:
                self._stop_event.wait(0.005)
                continue
            jpeg, w, h, seq, ts_ns, arrival = job
            now = _time.monotonic()
            if now - self._last_process_t < self.min_interval_s:
                continue
            self._last_process_t = now
            try:
                buf = np.frombuffer(jpeg, dtype=np.uint8)
                img = cv2.imdecode(buf, cv2.IMREAD_COLOR)
                if img is None:
                    continue
                gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
                corners, ids, _rej = self._detector.detectMarkers(gray)
                if ids is None:
                    continue
                for i, mid in enumerate(ids.reshape(-1)):
                    if int(mid) != self.marker_id:
                        continue
                    pts = np.asarray(corners[i]).reshape(-1, 2)
                    if pts.shape != (4, 2):
                        continue
                    det = {"corners": [(float(x), float(y)) for x, y in pts],
                           "marker_id": int(mid),
                           "img_w": int(img.shape[1]),
                           "img_h": int(img.shape[0]),
                           "seq": int(seq), "ts_ns": int(ts_ns),
                           "arrival_mono": float(arrival)}
                    with self._lock:
                        self._latest = det
                        self._seq_done = int(seq)
                        self._frames_done += 1
                    break
            except Exception:
                continue
