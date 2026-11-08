"""Centralized VITURE-GL <-> Panda3D coordinate conversion (pure Python).

Conventions (right-handed throughout):
  GL (SDK上下): x -> right, y -> up, z -> backward (out of the screen
    toward the viewer). Pose = [px,py,pz, qw,qx,qy,qz], Hamilton
    quaternions, body-to-world: v_world = q * v_body.
  Panda: x -> right, y -> forward, z -> up.

The basis change GL -> Panda is::

    panda = (gl_x, -gl_z, gl_y)

i.e. the rotation taking GL axes to Panda axes. Rotation parts convert
by conjugation (R_p = M * R_gl * M^T); translations map directly.
Matrices are 16-tuples in row-major order (matching Panda3D's
LMatrix4 constructor layout and v' = v * M row-vector convention).

Only stdlib is used so the unit tests run anywhere; the application
converts to Panda3D types at a single boundary.
"""

from __future__ import annotations

import math

# Basis change GL -> Panda, row-major 3x3:
#   row0 = image of GL +X = Panda +X
#   row1 = image of GL +Y = Panda +Z
#   row2 = image of GL +Z = Panda -Y
M_GL2PANDA = (
    1.0, 0.0, 0.0,
    0.0, 0.0, 1.0,
    0.0, -1.0, 0.0,
)

M_PANDA2GL = (
    1.0, 0.0, 0.0,
    0.0, 0.0, -1.0,
    0.0, 1.0, 0.0,
)


def mat3_mul(a, b):
    """Row-major 3x3 product: (v*a)*b = v*(a*b)."""
    return tuple(
        sum(a[3 * i + k] * b[3 * k + j] for k in range(3))
        for i in range(3) for j in range(3)
    )


def mat3_transpose(m):
    return tuple(m[3 * j + i] for i in range(3) for j in range(3))


def mat3_vec(m, v):
    """Row-vector transform: v' = v * m."""
    return tuple(sum(v[k] * m[3 * k + j] for k in range(3)) for j in range(3))


def quat_to_mat3(q):
    """Hamilton unit quat (w,x,y,z) -> row-major rotation matrix.

    Matches quat_rotate: v' = v * R equals quat_rotate(q, v).
    (Row-vector form, i.e. the transpose of the column-vector textbook
    matrix, consistent with mat3_vec/mat4_point.)
    """
    w, x, y, z = q
    return (
        1.0 - 2.0 * (y * y + z * z), 2.0 * (x * y + z * w), 2.0 * (x * z - y * w),
        2.0 * (x * y - z * w), 1.0 - 2.0 * (x * x + z * z), 2.0 * (y * z + x * w),
        2.0 * (x * z + y * w), 2.0 * (y * z - x * w), 1.0 - 2.0 * (x * x + y * y),
    )


def quat_rotate(q, v):
    """Rotate vector v by Hamilton unit quat (w,x,y,z)."""
    w, x, y, z = q
    tx = 2.0 * (y * v[2] - z * v[1])
    ty = 2.0 * (z * v[0] - x * v[2])
    tz = 2.0 * (x * v[1] - y * v[0])
    return (v[0] + w * tx + (y * tz - z * ty),
            v[1] + w * ty + (z * tx - x * tz),
            v[2] + w * tz + (x * ty - y * tx))


def quat_mul(a, b):
    """Hamilton product a*b (apply b first, then a), (w,x,y,z)."""
    aw, ax, ay, az = a
    bw, bx, by, bz = b
    return (aw * bw - ax * bx - ay * by - az * bz,
            aw * bx + ax * bw + ay * bz - az * by,
            aw * by - ax * bz + ay * bw + az * bx,
            aw * bz + ax * by - ay * bx + az * bw)


def gl_pose_to_panda_matrix(pos, quat):
    """Head pose (GL frame) -> Panda3D world matrix (row-major 16-tuple).

    The head is a rigid body: its world matrix is C = M * H, the GL pose
    left-multiplied by the basis change (object semantics: a GL-authored
    object placed through C lands correctly oriented in Panda space).
    Note this is NOT directly usable as a camera matrix -- the Panda
    lens looks along local +Y while the head faces local -Z, so the
    application aims the camera with look_at (verified pixel-perfect)
    instead of composing quats through Panda's conventions.
    """
    r_gl = quat_to_mat3(quat)
    m = M_GL2PANDA
    # Rotation part of M * H (matrix product in row-vector order:
    # apply H, then M -- i.e. express the head rotation in Panda axes).
    r = mat3_mul(r_gl, m)
    t = mat3_vec(m, pos)
    return (r[0], r[1], r[2], 0.0,
            r[3], r[4], r[5], 0.0,
            r[6], r[7], r[8], 0.0,
            t[0], t[1], t[2], 1.0)


def mat4_mul(a, b):
    """Row-major 4x4 product: v*(a*b) = (v*a)*b."""
    return tuple(
        sum(a[4 * i + k] * b[4 * k + j] for k in range(4))
        for i in range(4) for j in range(4)
    )


def mat4_inv_rigid(m):
    """Inverse of a rigid 4x4 (rotation + translation only)."""
    r = (m[0], m[1], m[2], m[4], m[5], m[6], m[8], m[9], m[10])
    rt = mat3_transpose(r)
    t = (m[12], m[13], m[14])
    ti = tuple(-sum(t[k] * rt[3 * k + j] for k in range(3)) for j in range(3))
    return (rt[0], rt[1], rt[2], 0.0,
            rt[3], rt[4], rt[5], 0.0,
            rt[6], rt[7], rt[8], 0.0,
            ti[0], ti[1], ti[2], 1.0)


def mat4_point(m, p):
    """Transform point (x,y,z) by row-major 4x4 (translation applied)."""
    x, y, z = p
    return (x * m[0] + y * m[4] + z * m[8] + m[12],
            x * m[1] + y * m[5] + z * m[9] + m[13],
            x * m[2] + y * m[6] + z * m[10] + m[14])


def view_matrix_for_head(pos, quat):
    """View matrix (world-to-head) for a GL head pose, in Panda frame."""
    return mat4_inv_rigid(gl_pose_to_panda_matrix(pos, quat))


def gl_to_panda_pos(pos):
    """Position-only conversion (translation part of the basis change)."""
    return mat3_vec(M_GL2PANDA, pos)


def approx(a, b, eps=1e-6):
    return all(abs(x - y) <= eps for x, y in zip(a, b))
