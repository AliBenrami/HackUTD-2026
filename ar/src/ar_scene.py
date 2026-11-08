"""World-locked PoC scene for native optical AR (wireframe only).

Authored once in OpenGL-style world coordinates (x -> right, y -> up,
z -> backward, metres) and never moved afterwards. Only the camera
moves, which is what pins the overlay to the room.

On an additive combiner black emits no light, so everything is
GL_LINES-equivalent (Panda3D line segments) on a pure-black clear.
No video, no backgrounds, no skyboxes -- only virtual geometry.

Layout (metres, relative to the tracking origin):
  A  green wireframe cube,  1.5 m straight ahead (primary reference)
  B  blue wireframe octahedron, ~35 deg left (head turn to find)
  C  red wireframe pyramid, ~35 deg right (head turn to find)
"""

from __future__ import annotations

CUBE_CENTER = (0.0, 0.0, -1.50)
CUBE_HALF = 0.15

LEFT_CENTER = (-1.20, 0.30, -1.80)
LEFT_RADIUS = 0.18

RIGHT_CENTER = (1.20, 0.10, -1.80)
RIGHT_HALF = 0.15
RIGHT_HEIGHT = 0.35


def _new_segs(name):
    from panda3d.core import LineSegs

    segs = LineSegs(name)
    segs.setThickness(2.0)
    return segs


def build_wire_cube(parent, center=CUBE_CENTER, half=CUBE_HALF,
                    color=(0.25, 1.0, 0.35, 1.0), name="ar-cube"):
    """Object A: bright green wireframe cube."""
    segs = _new_segs(name)
    cx, cy, cz = center
    corners = [
        (cx - half, cy - half, cz - half), (cx + half, cy - half, cz - half),
        (cx + half, cy + half, cz - half), (cx - half, cy + half, cz - half),
        (cx - half, cy - half, cz + half), (cx + half, cy - half, cz + half),
        (cx + half, cy + half, cz + half), (cx - half, cy + half, cz + half),
    ]
    edges = [(0, 1), (1, 2), (2, 3), (3, 0),
             (4, 5), (5, 6), (6, 7), (7, 4),
             (0, 4), (1, 5), (2, 6), (3, 7)]
    segs.setColor(*color)
    for a, b in edges:
        segs.moveTo(*corners[a])
        segs.drawTo(*corners[b])
    return parent.attachNewNode(segs.create())


def build_octahedron(parent, center=LEFT_CENTER, radius=LEFT_RADIUS,
                     color=(0.35, 0.55, 1.0, 1.0), name="ar-left"):
    """Object B: blue wireframe octahedron (clearly non-cube)."""
    segs = _new_segs(name)
    cx, cy, cz = center
    top = (cx, cy + radius, cz)
    bottom = (cx, cy - radius, cz)
    ring = [(cx + radius, cy, cz), (cx, cy, cz - radius),
            (cx - radius, cy, cz), (cx, cy, cz + radius)]
    segs.setColor(*color)
    for i, p in enumerate(ring):
        segs.moveTo(*top)
        segs.drawTo(*p)
        segs.moveTo(*bottom)
        segs.drawTo(*p)
        segs.moveTo(*p)
        segs.drawTo(*ring[(i + 1) % 4])
    return parent.attachNewNode(segs.create())


def build_pyramid(parent, center=RIGHT_CENTER, half=RIGHT_HALF,
                  height=RIGHT_HEIGHT, color=(1.0, 0.3, 0.25, 1.0),
                  name="ar-right"):
    """Object C: red wireframe square pyramid."""
    segs = _new_segs(name)
    cx, cy, cz = center
    apex = (cx, cy + height / 2.0, cz)
    base = [(cx - half, cy - height / 2.0, cz - half),
            (cx + half, cy - height / 2.0, cz - half),
            (cx + half, cy - height / 2.0, cz + half),
            (cx - half, cy - height / 2.0, cz + half)]
    segs.setColor(*color)
    for i, p in enumerate(base):
        segs.moveTo(*apex)
        segs.drawTo(*p)
        segs.moveTo(*p)
        segs.drawTo(*base[(i + 1) % 4])
    return parent.attachNewNode(segs.create())


def build_calibration(parent, hfov_deg, vfov_deg, depth=3.0):
    """Temporary stereo calibration rig (see --calibrate).

    Frustum-filling border, corner markers, center crosshair, and
    angular rings at 5/10/15/20 deg eccentricity (radius = depth * tan).
    If any border edge is missing on the glasses, that side is clipped
    by optics/windowing, not by the scene: the geometry deliberately
    overfills nothing and matches the projection exactly.
    """
    import math

    from panda3d.core import TextNode

    segs = _new_segs("ar-calib")
    hw = depth * math.tan(math.radians(hfov_deg) / 2.0)
    hh = depth * math.tan(math.radians(vfov_deg) / 2.0)
    z = -depth

    # Border exactly on the frustum edge.
    segs.setColor(1.0, 1.0, 1.0, 1.0)
    corners = [(-hw, -hh, z), (hw, -hh, z), (hw, hh, z), (-hw, hh, z)]
    for i, p in enumerate(corners):
        segs.moveTo(*p)
        segs.drawTo(*corners[(i + 1) % 4])

    # Corner L markers, inset 3% toward center.
    segs.setColor(1.0, 0.95, 0.25, 1.0)
    inset = 0.06
    for sx, sy in ((-1, -1), (1, -1), (1, 1), (-1, 1)):
        cx, cy = sx * hw * (1.0 - inset), sy * hh * (1.0 - inset)
        lx, ly = hw * 0.06, hh * 0.06
        segs.moveTo(cx, cy, z)
        segs.drawTo(cx - sx * lx, cy, z)
        segs.moveTo(cx, cy, z)
        segs.drawTo(cx, cy - sy * ly, z)

    # Center crosshair + 0.5 deg reference circle.
    segs.setColor(1.0, 0.3, 0.3, 1.0)
    tick = depth * math.tan(math.radians(1.0))
    segs.moveTo(-tick, 0.0, z)
    segs.drawTo(tick, 0.0, z)
    segs.moveTo(0.0, -tick, z)
    segs.drawTo(0.0, tick, z)
    segs.setColor(0.3, 1.0, 0.3, 1.0)
    _circle(segs, (0.0, 0.0, z), depth * math.tan(math.radians(0.5)))

    # Angular rings every 5 deg with labels at the top.
    segs.setColor(0.0, 0.85, 0.85, 1.0)
    for deg in (5, 10, 15, 20):
        _circle(segs, (0.0, 0.0, z), depth * math.tan(math.radians(deg)))
    node = parent.attachNewNode(segs.create())

    for deg in (5, 10, 15, 20):
        tn = TextNode(f"ar-calib-{deg}")
        tn.set_text(f"{deg}\u00b0")
        tn.set_text_color(0.0, 0.85, 0.85, 1.0)
        tn.set_align(TextNode.A_center)
        label = parent.attachNewNode(tn)
        label.set_pos(0.0, depth * math.tan(math.radians(deg)), z)
        label.set_scale(0.09)
    return node


def _circle(segs, center, radius, steps=72):
    """Append a GL-space line-loop circle facing +Z."""
    import math

    cx, cy, cz = center
    first = None
    prev = None
    for i in range(steps + 1):
        a = 2.0 * math.pi * i / steps
        p = (cx + radius * math.cos(a), cy + radius * math.sin(a), cz)
        if i == 0:
            first = p
        else:
            segs.moveTo(*prev)
            segs.drawTo(*p)
        prev = p
    segs.moveTo(*prev)
    segs.drawTo(*first)


# ---------------------------------------------------------------------------
# Solid lit meshes (for tabletop objects under real lights).
#
# All builders emit GeomTriangles with computed (analytic) normals and
# per-vertex colors, CCW-outward winding, into GL coordinates. The app
# must attach at least one light above the table node or these render
# black.


def _solid_geom_node(name, positions, normals, colors, triangles):
    """Pack verts + triangle index list into a GeomNode."""
    from panda3d.core import (Geom, GeomNode, GeomTriangles,
                              GeomVertexData, GeomVertexFormat,
                              GeomVertexWriter)

    fmt = GeomVertexFormat.getV3n3c4()
    vdata = GeomVertexData(name, fmt, Geom.UHStatic)
    vdata.setNumRows(len(positions))
    vw = GeomVertexWriter(vdata, "vertex")
    nw = GeomVertexWriter(vdata, "normal")
    cw = GeomVertexWriter(vdata, "color")
    for p, n, c in zip(positions, normals, colors):
        vw.addData3(*p)
        nw.addData3(*n)
        cw.addData4(*c)
    prim = GeomTriangles(Geom.UHStatic)
    for a, b, c in triangles:
        prim.addVertices(a, b, c)
    prim.closePrimitive()
    geom = Geom(vdata)
    geom.addPrimitive(prim)
    node = GeomNode(name)
    node.addGeom(geom)
    return node


def build_solid_box(parent, center=(0, 0, 0.05), size=(0.1, 0.1, 0.1),
                    color=(0.2, 0.9, 0.4, 1.0), name="ar-solid-box"):
    """Solid box; center/size in parent (table-local) coords, metres."""
    cx, cy, cz = center
    sx, sy, sz = size[0] / 2.0, size[1] / 2.0, size[2] / 2.0
    # Per-face verts for flat normals: (corners, normal).
    faces = [
        ([(1, 1, 1), (1, -1, 1), (1, -1, -1), (1, 1, -1)], (1, 0, 0)),
        ([(-1, 1, -1), (-1, -1, -1), (-1, -1, 1), (-1, 1, 1)], (-1, 0, 0)),
        ([(-1, 1, 1), (-1, 1, -1), (1, 1, -1), (1, 1, 1)], (0, 1, 0)),
        ([(-1, -1, -1), (-1, -1, 1), (1, -1, 1), (1, -1, -1)], (0, -1, 0)),
        ([(-1, -1, 1), (-1, 1, 1), (1, 1, 1), (1, -1, 1)], (0, 0, 1)),
        ([(-1, 1, -1), (-1, -1, -1), (1, -1, -1), (1, 1, -1)], (0, 0, -1)),
    ]
    positions, normals, colors, tris = [], [], [], []
    for corners, n in faces:
        base = len(positions)
        for sxn, syn, szn in corners:
            positions.append((cx + sxn * sx, cy + syn * sy, cz + szn * sz))
            normals.append(n)
            colors.append(color)
        # CCW outward as seen from outside each face.
        tris += [(base, base + 1, base + 2), (base, base + 2, base + 3)]
    # Faces authored per-face (flat normals); _outward() below enforces
    # CCW-outward winding per triangle from its face normal.
    node = _solid_geom_node(name, positions, normals, colors,
                            _outward(tris, positions, normals))
    return parent.attachNewNode(node)


def _outward(tris, positions, normals):
    """Ensure each triangle winds CCW as seen from its face normal."""
    import numpy as np

    fixed = []
    for (a, b, c) in tris:
        pa, pb, pc = (np.array(positions[i], dtype=float) for i in (a, b, c))
        n = np.array(normals[a], dtype=float)
        winding = np.dot(np.cross(pb - pa, pc - pa), n)
        fixed.append((a, b, c) if winding >= 0.0 else (a, c, b))
    return fixed


def build_solid_sphere(parent, center=(0, 0, 0.05), radius=0.05,
                       color=(0.3, 0.6, 1.0, 1.0), name="ar-solid-sphere",
                       slices=24, stacks=16):
    """Solid sphere with analytic normals (normal = radial)."""
    import math

    import numpy as np

    cx, cy, cz = center
    positions, normals, colors, tris = [], [], [], []
    for j in range(stacks + 1):
        theta = math.pi * j / stacks  # 0 = +Z pole
        for i in range(slices + 1):
            phi = 2.0 * math.pi * i / slices
            n = (math.sin(theta) * math.cos(phi),
                 math.sin(theta) * math.sin(phi),
                 math.cos(theta))
            positions.append((cx + radius * n[0], cy + radius * n[1],
                              cz + radius * n[2]))
            normals.append(n)
            colors.append(color)
    ring = slices + 1
    for j in range(stacks):
        for i in range(slices):
            a, b = j * ring + i, j * ring + i + 1
            c, d = (j + 1) * ring + i, (j + 1) * ring + i + 1
            tris += [(a, c, b), (b, c, d)]
    node = _solid_geom_node(name, positions, normals, colors,
                            _outward(tris, positions, normals))
    return parent.attachNewNode(node)


def build_solid_cylinder(parent, center=(0, 0, 0.05), radius=0.04,
                         height=0.10, color=(1.0, 0.6, 0.2, 1.0),
                         name="ar-solid-cylinder", slices=24):
    """Solid cylinder standing along parent +Z (table normal)."""
    import math

    cx, cy, cz = center
    hz = height / 2.0
    positions, normals, colors, tris = [], [], [], []
    # Side wall.
    for i in range(slices + 1):
        a = 2.0 * math.pi * i / slices
        n = (math.cos(a), math.sin(a), 0.0)
        positions.append((cx + radius * n[0], cy + radius * n[1], cz - hz))
        normals.append(n)
        colors.append(color)
        positions.append((cx + radius * n[0], cy + radius * n[1], cz + hz))
        normals.append(n)
        colors.append(color)
    for i in range(slices):
        a, b = 2 * i, 2 * i + 2
        c, d = 2 * i + 1, 2 * i + 3
        tris += [(a, b, c), (c, b, d)]
    # Caps (flat +/-Z normals).
    for top, n in ((cz + hz, (0, 0, 1)), (cz - hz, (0, 0, -1))):
        base = len(positions)
        positions.append((cx, cy, top))
        normals.append(n)
        colors.append(color)
        for i in range(slices + 1):
            a = 2.0 * math.pi * i / slices
            positions.append((cx + radius * math.cos(a),
                              cy + radius * math.sin(a), top))
            normals.append(n)
            colors.append(color)
        for i in range(slices):
            tris.append((base, base + 1 + i, base + 2 + i))
    node = _solid_geom_node(name, positions, normals, colors,
                            _outward(tris, positions, normals))
    return parent.attachNewNode(node)


def build_arrow(parent, origin=(0, 0, 0.01), direction=(0, 0, 1),
                length=0.15, shaft_r=0.006, head_r=0.016, head_l=0.045,
                color=(1.0, 0.9, 0.2, 1.0), name="ar-arrow", slices=16):
    """Solid arrow from origin along direction (any unit-ish vector)."""
    import math

    import numpy as np

    d = np.array(direction, dtype=float)
    nn = float(np.linalg.norm(d))
    d = d / nn if nn > 1e-12 else np.array([0.0, 0.0, 1.0])
    # Orthonormal basis around d.
    up = np.array([0.0, 0.0, 1.0]) if abs(d[2]) < 0.9 else np.array([0.0, 1.0, 0.0])
    u = np.cross(d, up)
    u = u / np.linalg.norm(u)
    v = np.cross(d, u)
    o = np.array(origin, dtype=float)
    shaft_end = o + d * max(0.0, length - head_l)
    tip = o + d * length
    positions, normals, colors, tris = [], [], [], []

    def ring(ctr, uu, vv, r, n_pts):
        pts = []
        for i in range(n_pts + 1):
            a = 2.0 * math.pi * i / n_pts
            pts.append(ctr + r * (math.cos(a) * uu + math.sin(a) * vv))
        return pts

    # Shaft wall (normal radial around d).
    r0, r1 = ring(o, u, v, shaft_r, slices), ring(shaft_end, u, v, shaft_r, slices)
    base = 0
    for p in r0:
        positions.append(tuple(p))
        n = tuple((np.array(p) - o) - np.dot(np.array(p) - o, d) * d)
        nn = float(np.linalg.norm(n))
        normals.append(tuple(np.array(n) / nn) if nn > 1e-12 else (1, 0, 0))
        colors.append(color)
    for p in r1:
        positions.append(tuple(p))
        n = tuple((np.array(p) - shaft_end)
                  - np.dot(np.array(p) - shaft_end, d) * d)
        nn = float(np.linalg.norm(n))
        normals.append(tuple(np.array(n) / nn) if nn > 1e-12 else (1, 0, 0))
        colors.append(color)
    n = slices + 1
    for i in range(slices):
        tris += [(base + i, base + i + 1, base + n + i),
                 (base + i + 1, base + n + i + 1, base + n + i)]
    # Shaft base cap + head cone + head base cap.
    def cap_fan(ctr_pt, ring_pts, normal):
        b = len(positions)
        positions.append(tuple(ctr_pt))
        normals.append(tuple(normal))
        colors.append(color)
        for p in ring_pts:
            positions.append(tuple(p))
            normals.append(tuple(normal))
            colors.append(color)
        for i in range(len(ring_pts) - 1):
            tris.append((b, b + 1 + i, b + 2 + i))

    cap_fan(o, r0, -d)
    # Cone: apex tip, base ring at shaft_end radius head_r.
    hb = ring(shaft_end, u, v, head_r, slices)
    apex_idx = len(positions)
    positions.append(tuple(tip))
    colors.append(color)
    slope = head_r / max(1e-9, head_l)
    apex_n = tuple(d)
    normals.append(apex_n)
    cone_base = len(positions)
    for p in hb:
        positions.append(tuple(p))
        radial = (np.array(p) - shaft_end) / max(1e-12, head_r)
        cn = np.array(radial + d * (head_r / max(1e-9, head_l)), dtype=float)
        cn = cn / max(1e-12, float(np.linalg.norm(cn)))
        normals.append(tuple(cn))
        colors.append(color)
    for i in range(slices):
        tris.append((apex_idx, cone_base + i, cone_base + i + 1))
    cap_fan(shaft_end, hb, -d)
    node = _solid_geom_node(name, positions, normals, colors,
                            _outward(tris, positions, normals))
    return parent.attachNewNode(node)


def build_table_debug(parent, width_m=0.60, length_m=0.40,
                      name="ar-table-debug"):
    """Table wireframe: bounds rect, axes triad, origin ring, label.

    Authored in table-local coords (x right, y up-in-plane, z normal):
    bounds at z=0 with the triad +X red / +Y green / +Z blue.
    """
    segs = _new_segs(name)
    hw, hl = width_m / 2.0, length_m / 2.0
    z = 0.001
    segs.setColor(1.0, 0.75, 0.2, 1.0)
    corners = [(-hw, -hl, z), (hw, -hl, z), (hw, hl, z), (-hw, hl, z)]
    for i, p in enumerate(corners):
        segs.moveTo(*p)
        segs.drawTo(*corners[(i + 1) % 4])
    triad = 0.10
    for color, delta in (
        ((1.0, 0.15, 0.15, 1.0), (triad, 0.0, 0.0)),
        ((0.2, 1.0, 0.2, 1.0), (0.0, triad, 0.0)),
        ((0.3, 0.5, 1.0, 1.0), (0.0, 0.0, triad)),
    ):
        segs.setColor(*color)
        segs.moveTo(0.0, 0.0, z)
        segs.drawTo(*[a + b for a, b in zip((0.0, 0.0, z), delta)])
    segs.setColor(1.0, 1.0, 1.0, 1.0)
    _circle(segs, (0.0, 0.0, z), 0.015)
    node = parent.attachNewNode(segs.create())
    try:
        from panda3d.core import TextNode

        tn = TextNode(f"{name}-label")
        tn.set_text("TABLE")
        tn.set_text_color(1.0, 0.75, 0.2, 1.0)
        tn.set_align(TextNode.A_center)
        label = parent.attachNewNode(tn)
        label.set_pos(0.0, -hl - 0.03, 0.0)
        label.set_scale(0.025)
    except Exception:
        pass
    return node
