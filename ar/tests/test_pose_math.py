"""Unit tests for pose_math: GL <-> Panda3D coordinate conversion.

Run:  uv run python -m unittest discover -s tests -v
Pure stdlib + pose_math: no window, no hardware needed.
"""

import math
import unittest

from pose_math import (
    M_GL2PANDA,
    approx,
    gl_pose_to_panda_matrix,
    gl_to_panda_pos,
    mat3_mul,
    mat3_transpose,
    mat3_vec,
    mat4_inv_rigid,
    mat4_mul,
    mat4_point,
    quat_mul,
    quat_rotate,
    quat_to_mat3,
    view_matrix_for_head,
)

IDENTITY_Q = (1.0, 0.0, 0.0, 0.0)
ORIGIN = (0.0, 0.0, 0.0)


def deg(d):
    return math.radians(d)


def yaw_q(d):
    h = deg(d) / 2.0
    return (math.cos(h), 0.0, math.sin(h), 0.0)


def pitch_q(d):
    h = deg(d) / 2.0
    return (math.cos(h), math.sin(h), 0.0, 0.0)


def roll_q(d):
    h = deg(d) / 2.0
    return (math.cos(h), 0.0, 0.0, math.sin(h))


IDENT_MAT4 = (1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1, 0, 0, 0, 0, 1)


class TestBasisChange(unittest.TestCase):
    def test_identity_pose_is_basis_change(self):
        # The head world matrix for identity is M itself: a GL-authored
        # object placed through it lands correctly in Panda space.
        m = gl_pose_to_panda_matrix(ORIGIN, IDENTITY_Q)
        self.assertTrue(approx(m[:12], (1, 0, 0, 0,
                                       0, 0, 1, 0,
                                       0, -1, 0, 0)))
        self.assertTrue(approx((m[12], m[13], m[14]), (0.0, 0.0, 0.0)))

    def test_basis_change_sends_gl_forward_to_panda_forward(self):
        self.assertTrue(approx(mat3_vec(M_GL2PANDA, (0.0, 0.0, -1.0)),
                              (0.0, 1.0, 0.0)))

    def test_positive_x_translation(self):
        m = gl_pose_to_panda_matrix((1.0, 0.0, 0.0), IDENTITY_Q)
        self.assertTrue(approx((m[12], m[13], m[14]), (1.0, 0.0, 0.0)))

    def test_positive_y_translation_is_panda_up(self):
        m = gl_pose_to_panda_matrix((0.0, 1.0, 0.0), IDENTITY_Q)
        self.assertTrue(approx((m[12], m[13], m[14]), (0.0, 0.0, 1.0)))

    def test_positive_z_translation_is_panda_backward(self):
        m = gl_pose_to_panda_matrix((0.0, 0.0, 1.0), IDENTITY_Q)
        self.assertTrue(approx((m[12], m[13], m[14]), (0.0, -1.0, 0.0)))

    def test_pos_helper_matches_matrix(self):
        for p in [(1.0, 2.0, 3.0), (-0.5, 0.25, -1.0)]:
            m = gl_pose_to_panda_matrix(p, IDENTITY_Q)
            self.assertTrue(approx(gl_to_panda_pos(p), (m[12], m[13], m[14])))


class TestRotations(unittest.TestCase):
    def test_yaw_plus90_turns_forward_to_left(self):
        # GL yaw +90 about +Y sends forward (0,0,-1) to (-1,0,0).
        self.assertTrue(approx(quat_rotate(yaw_q(90), (0.0, 0.0, -1.0)),
                              (-1.0, 0.0, 0.0)))
        # In Panda terms that facing is still -X (M fixes X).
        f = quat_rotate(yaw_q(90), (0.0, 0.0, -1.0))
        self.assertTrue(approx(mat3_vec(M_GL2PANDA, f), (-1.0, 0.0, 0.0)))

    def test_pitch_plus90_turns_forward_to_up(self):
        # R_x(+90): (0,0,-1) -> (0,1,0): looking straight up in GL.
        self.assertTrue(approx(quat_rotate(pitch_q(90), (0.0, 0.0, -1.0)),
                              (0.0, 1.0, 0.0)))
        # Panda up is +Z.
        f = quat_rotate(pitch_q(90), (0.0, 0.0, -1.0))
        self.assertTrue(approx(mat3_vec(M_GL2PANDA, f), (0.0, 0.0, 1.0)))

    def test_roll_plus90_turns_right_to_up(self):
        self.assertTrue(approx(quat_rotate(roll_q(90), (1.0, 0.0, 0.0)),
                              (0.0, 1.0, 0.0)))

    def test_quat_rotate_matches_quat_matrix(self):
        for q in (yaw_q(30), pitch_q(-20), roll_q(45),
                  quat_mul(yaw_q(30), pitch_q(-20))):
            r = quat_to_mat3(q)
            for v in ((1.0, 0.0, 0.0), (0.0, 1.0, 0.0), (0.0, 0.0, 1.0)):
                self.assertTrue(approx(quat_rotate(q, v), mat3_vec(r, v)))

    def test_combined_translation_and_rotation(self):
        pos = (0.5, 1.5, -2.0)
        q = quat_mul(yaw_q(30), pitch_q(-15))
        m = gl_pose_to_panda_matrix(pos, q)
        # Translation part converts by the basis change.
        self.assertTrue(approx((m[12], m[13], m[14]), (0.5, 2.0, 1.5)))
        # Upper 3x3 is a pure rotation (orthonormal, det +1).
        r = (m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10])
        self.assertTrue(approx(mat3_mul(r, mat3_transpose(r)),
                              (1, 0, 0, 0, 1, 0, 0, 0, 1), eps=1e-9))


class TestInversion(unittest.TestCase):
    def test_head_times_view_is_identity(self):
        pos = (0.3, -0.1, 0.8)
        q = quat_mul(yaw_q(-25), quat_mul(pitch_q(10), roll_q(5)))
        h = gl_pose_to_panda_matrix(pos, q)
        v = mat4_inv_rigid(h)
        self.assertTrue(approx(mat4_mul(h, v), IDENT_MAT4, eps=1e-9))
        self.assertTrue(approx(mat4_mul(v, h), IDENT_MAT4, eps=1e-9))

    def test_view_matrix_maps_ahead_point_to_view_axis(self):
        # A point d metres straight ahead of the head must round-trip
        # through the view matrix back to head space: (0, 0, -d).
        # (The matrix preserves the GL view convention; the Panda lens's
        # +Y look axis is handled at the look_at boundary, not here.)
        pos = (0.3, 1.7, 0.8)
        q = quat_mul(yaw_q(-25), pitch_q(10))
        view = view_matrix_for_head(pos, q)
        # Recompute properly: ahead = t + R*(0,0,-d), d = 2.
        fwd = quat_rotate(q, (0.0, 0.0, -1.0))
        ahead_gl = (pos[0] + 2.0 * fwd[0],
                    pos[1] + 2.0 * fwd[1],
                    pos[2] + 2.0 * fwd[2])
        ahead_panda = mat3_vec(M_GL2PANDA, ahead_gl)
        got = mat4_point(view, ahead_panda)
        self.assertTrue(approx(got, (0.0, 0.0, -2.0), eps=1e-6))

    def test_head_origin_maps_to_view_origin(self):
        pos = (0.3, 1.7, 0.8)
        q = quat_mul(yaw_q(-25), pitch_q(10))
        view = view_matrix_for_head(pos, q)
        got = mat4_point(view, mat3_vec(M_GL2PANDA, pos))
        self.assertTrue(approx(got, (0.0, 0.0, 0.0), eps=1e-6))


if __name__ == "__main__":
    unittest.main()
