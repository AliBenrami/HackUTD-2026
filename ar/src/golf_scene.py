"""Continuous cyberpunk terrain renderer and cyberpunk asset gallery."""
import math
import sys

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, LineSegs,
                          NodePath, TextNode, Vec3)

import course_generator
from cyber_theme import apply, apply_vertex_material, rgba
from golf_specs import BALL_DIAMETER_M, COURSE_SCALE

LAYOUT = None  # Legacy JSON course deliberately retired.
GALLERY = []  # Populated from the cyberpunk-only manifest.


def _geom_node(name, vertices, triangles):
    fmt = GeomVertexFormat.get_v3n3c4()
    data = GeomVertexData(name, fmt, Geom.UH_static)
    data.set_num_rows(len(vertices))
    vw, nw, cw = (GeomVertexWriter(data, column)
                  for column in ("vertex", "normal", "color"))
    for pos, normal, color in vertices:
        vw.add_data3(*pos)
        nw.add_data3(*normal)
        cw.add_data4(*color)
    prim = GeomTriangles(Geom.UH_static)
    for a, b, c in triangles:
        prim.add_vertices(a, b, c)
    prim.close_primitive()
    geom = Geom(data)
    geom.add_primitive(prim)
    node = GeomNode(name)
    node.add_geom(geom)
    return NodePath(node)


def _terrain(layout):
    t = layout["terrain"]
    n, w, l = t["grid_size"], t["width_m"], t["length_m"]
    dx, dy = w/(n-1), l/(n-1)
    vertices, positions = [], []
    base, secondary, ridge = rgba("base"), rgba("secondary"), rgba("ridge")
    # Compute each shared height once. Normals use adjacent cached samples;
    # this keeps regeneration out of the sustained pose-to-render path and
    # avoids five expensive route/noise queries per vertex.
    for j in range(n):
        y = -l/2+j*dy
        row = []
        for i in range(n):
            x = -w/2+i*dx
            z = course_generator.terrain_height(layout, x, y)
            row.append((x, y, z))
        positions.append(row)
    for j in range(n):
        for i in range(n):
            p = positions[j][i]
            left, right = positions[j][max(0, i-1)], positions[j][min(n-1, i+1)]
            down, up = positions[max(0, j-1)][i], positions[min(n-1, j+1)][i]
            zx = (right[2]-left[2])/max(dx, right[0]-left[0])
            zy = (up[2]-down[2])/max(dy, up[1]-down[1])
            normal = Vec3(-zx, -zy, 1)
            normal.normalize()
            slope = min(1., math.hypot(zx, zy)/.85)
            nx, ny = i/(n-1), j/(n-1)
            # Low-frequency panel variation avoids checkerboard/ripple noise.
            variation = course_generator._noise(layout["seed"]+1201,
                                                nx*3.1, ny*3.1)*.5+.5
            lit = .16+.20*variation
            color = tuple(base[k]*(1-lit)+secondary[k]*lit for k in range(4))
            # Slope and elevation give hills/valleys readable silhouettes even
            # when the optical display washes out subtle albedo differences.
            rel = (p[2]-t["base_height_m"]) / max(t["height_amplitude_m"], 1e-6)
            high, low = max(0., min(1., rel)), max(0., min(1., -rel))
            color = tuple(color[k]*(1+.20*high-.22*low) for k in range(3)) + (1,)
            color = tuple(color[k]*(1-slope*.42)+ridge[k]*(slope*.42)
                          for k in range(4))
            vertices.append((p, tuple(normal), color))
    triangles = []
    for j in range(n-1):
        for i in range(n-1):
            a, b = j*n+i, j*n+i+1
            c, d = (j+1)*n+i, (j+1)*n+i+1
            triangles.extend(((a, b, d), (a, d, c)))
    node = _geom_node("cyber-terrain", vertices, triangles)
    node.set_python_tag("dimensions_m", (w, l, max(v[0][2] for v in vertices)))
    node.set_python_tag("terrain_vertices", positions)
    node.set_python_tag("triangle_count", len(triangles))
    apply_vertex_material(node, "base")
    return node, positions, triangles


def _terrain_sides(layout, positions):
    n = len(positions)
    perimeter = (positions[0] + [row[-1] for row in positions[1:]] +
                 list(reversed(positions[-1][:-1])) +
                 [row[0] for row in reversed(positions[1:-1])])
    bottom = -.025/layout["course_scale"]
    chamfer = .002/layout["course_scale"]
    chamfer_drop = .0015/layout["course_scale"]
    vertices, triangles = [], []
    top_color, wall_color, bottom_color = (rgba("secondary"), rgba("sidewall"),
                                           rgba("ridge"))
    for i, p in enumerate(perimeter):
        j = (i+1) % len(perimeter)
        q = perimeter[j]
        tx, ty = q[0]-p[0], q[1]-p[1]
        normal = Vec3(ty, -tx, 0)
        normal.normalize()
        chamfer_normal = Vec3(normal[0]*.72, normal[1]*.72, .7)
        chamfer_normal.normalize()
        vertices.extend((
            (p, tuple(chamfer_normal), top_color),
            ((p[0]+normal[0]*chamfer, p[1]+normal[1]*chamfer,
              p[2]-chamfer_drop), tuple(chamfer_normal), top_color),
            ((p[0]-normal[0]*.010/layout["course_scale"],
              p[1]-normal[1]*.010/layout["course_scale"], bottom),
             tuple(normal), bottom_color)))
        a, b = 3*i, 3*j
        triangles.extend(((a, b+1, b), (a, a+1, b+1),
                          (a+1, b+2, b+1), (a+1, a+2, b+2)))
    side = _geom_node("cyber-island-sides", vertices, triangles)
    apply_vertex_material(side, "sidewall")
    trim = LineSegs("island-perimeter-trim")
    trim.set_thickness(2)
    trim.set_color(*rgba("cyan", .72))
    for i, p in enumerate(perimeter+[perimeter[0]]):
        q = perimeter[(i+1) % len(perimeter)]
        tx, ty = q[0]-p[0], q[1]-p[1]
        normal = Vec3(ty, -tx, 0)
        normal.normalize()
        x, y = p[0]+normal[0]*chamfer, p[1]+normal[1]*chamfer
        z = p[2]-chamfer_drop+.0004
        (trim.move_to if i == 0 else trim.draw_to)(x, y, z)
    trim_node = side.attach_new_node(trim.create())
    trim_node.set_python_tag("neon", True)
    return side


def _mesh_height(layout, positions, x, y):
    """Exact height of the rendered terrain triangles, clamped at the border.

    Bilinear sampling differs from the two-triangle surface on steep quads and
    lets the terrain poke through the fairway, so reproduce the actual split.
    """
    rows, columns = len(positions), len(positions[0])
    t = layout["terrain"]
    dx, dy = t["width_m"]/(columns-1), t["length_m"]/(rows-1)
    gx = max(0., min(columns-1., (x+t["width_m"]/2)/dx))
    gy = max(0., min(rows-1., (y+t["length_m"]/2)/dy))
    i = min(columns-2, int(gx))
    j = min(rows-2, int(gy))
    u, v = gx-i, gy-j
    a = positions[j][i][2]
    b = positions[j][i+1][2]
    c = positions[j+1][i][2]
    d = positions[j+1][i+1][2]
    if u >= v:  # triangle (a, b, d)
        return a + (b-a)*u + (d-b)*v
    return a + (d-c)*u + (c-a)*v  # triangle (a, d, c)


def _ribbon(layout, positions):
    route = layout["route"]
    vertices, triangles = [], []
    color = rgba("fairway")
    cross = (-1., -.75, -.5, -.25, 0., .25, .5, .75, 1.)
    for i, p in enumerate(route):
        prev, nxt = route[max(0, i-1)], route[min(len(route)-1, i+1)]
        dx, dy = nxt[0]-prev[0], nxt[1]-prev[1]
        length = math.hypot(dx, dy) or 1
        nx, ny = -dy/length, dx/length
        progress = i/max(1, len(route)-1)
        half = course_generator.fairway_width_at(layout, progress)/2
        shade = .84+.12*math.sin(progress*math.pi)
        # The corridor is sculpted flat across its width; use the route-centre
        # normal so steep blend normals do not paint jagged shadow bands.
        normal = course_generator.terrain_normal(layout, p[0], p[1])
        # Five cross-sections let the surface follow the sculpted heightfield
        # instead of bridging edge heights with a single sagging quad.
        for fraction in cross:
            x, y = p[0]+nx*half*fraction, p[1]+ny*half*fraction
            z = _mesh_height(layout, positions, x, y)+.0012/layout["course_scale"]
            vertices.append(((x, y, z), normal,
                             tuple(c*shade if k < 3 else c
                                   for k, c in enumerate(color))))
    span = len(cross)
    for i in range(len(route)-1):
        for k in range(span-1):
            a = i*span+k
            b = i*span+k+1
            c = (i+1)*span+k+1
            d = (i+1)*span+k
            triangles.extend(((a, c, b), (a, d, c)))
    ribbon = _geom_node("neon-fairway", vertices, triangles)
    apply_vertex_material(ribbon, "fairway")
    ribbon.set_two_sided(True)
    # Narrow emissive boundaries replace the previous uniformly bright river.
    for side in (-1, 1):
        edge = LineSegs(f"fairway-edge-{'left' if side < 0 else 'right'}")
        edge.set_thickness(3)
        edge.set_color(*rgba("cyan"))
        for i, p in enumerate(route):
            prev, nxt = route[max(0, i-1)], route[min(len(route)-1, i+1)]
            dx, dy = nxt[0]-prev[0], nxt[1]-prev[1]
            length = math.hypot(dx, dy) or 1
            half = course_generator.fairway_width_at(
                layout, i/max(1, len(route)-1))/2
            x, y = p[0]-dy/length*half*side, p[1]+dx/length*half*side
            z = _mesh_height(layout, positions, x, y)+.0020/layout["course_scale"]
            (edge.move_to if i == 0 else edge.draw_to)(x, y, z)
        edge_node = ribbon.attach_new_node(edge.create())
        edge_node.set_python_tag("neon", True)
    # Restrained directional center dashes support route reading from low angles.
    marks = LineSegs("fairway-direction-marks")
    marks.set_thickness(2); marks.set_color(*rgba("lime", .62))
    for i in range(5, len(route)-3, 8):
        a, b = route[i], route[min(i+2, len(route)-1)]
        za = _mesh_height(layout, positions, *a)+.0014/layout["course_scale"]
        zb = _mesh_height(layout, positions, *b)+.0014/layout["course_scale"]
        marks.move_to(a[0], a[1], za); marks.draw_to(b[0], b[1], zb)
    marks_node = ribbon.attach_new_node(marks.create())
    marks_node.set_python_tag("neon", True)
    ribbon.set_python_tag("dimensions_m", (layout["terrain"]["width_m"],
                                           layout["fairway_width_m"], .002))
    return ribbon


def _disc(name, radius, z, color_name, seed=0, segments=28, neon=True):
    color = rgba(color_name, .9)
    vertices = [((0, 0, z), (0, 0, 1), color)]
    for i in range(segments):
        angle = 2*math.pi*i/segments
        irregular = 1+.06*math.sin(angle*5+seed)
        vertices.append(((math.cos(angle)*radius*irregular,
                          math.sin(angle)*radius*irregular, z),
                         (0, 0, 1), color))
    triangles = [(0, i+1, (i+1) % segments+1) for i in range(segments)]
    node = _geom_node(name, vertices, triangles)
    apply(node, color_name, neon)
    node.set_two_sided(True)
    return node


def _ring(name, outer, inner, z, color_name, segments=40):
    color = rgba(color_name)
    vertices, triangles = [], []
    for i in range(segments):
        angle = 2*math.pi*i/segments
        ca, sa = math.cos(angle), math.sin(angle)
        vertices.extend((((ca*outer, sa*outer, z), (0, 0, 1), color),
                         ((ca*inner, sa*inner, z), (0, 0, 1), color)))
    for i in range(segments):
        j = (i+1) % segments
        triangles.extend(((2*i, 2*j, 2*j+1),
                          (2*i, 2*j+1, 2*i+1)))
    node = _geom_node(name, vertices, triangles)
    apply(node, color_name, True)
    node.set_two_sided(True)
    return node


def _box(name, size, height, color_name="secondary", neon_edges=True):
    x, y, z = size/2, size/2, height
    ps = [(-x,-y,0),(x,-y,0),(x,y,0),(-x,y,0),
          (-x,-y,z),(x,-y,z),(x,y,z),(-x,y,z)]
    quads = ((0,3,2,1,(0,0,-1)), (4,5,6,7,(0,0,1)),
             (0,1,5,4,(0,-1,0)), (1,2,6,5,(1,0,0)),
             (2,3,7,6,(0,1,0)), (3,0,4,7,(-1,0,0)))
    vertices, faces = [], []
    for quad in quads:
        start = len(vertices)
        vertices.extend((ps[index], quad[4], rgba(color_name)) for index in quad[:4])
        faces.extend(((start, start+1, start+2), (start, start+2, start+3)))
    node = _geom_node(name, vertices, faces)
    apply(node, color_name)
    node.set_python_tag("dimensions_m", (size, size, height))
    if neon_edges:
        lines = LineSegs(name+"-neon")
        lines.set_thickness(3)
        lines.set_color(*rgba("amber"))
        for a, b in ((0,1),(1,2),(2,3),(3,0),(4,5),(5,6),(6,7),(7,4),
                     (0,4),(1,5),(2,6),(3,7)):
            lines.move_to(*ps[a]); lines.draw_to(*ps[b])
        edge = node.attach_new_node(lines.create())
        edge.set_python_tag("neon", True)
    return node


def _sphere(name, radius, color_name="white", rings=14, segments=24,
            neon=False):
    vertices, triangles = [], []
    color = rgba(color_name)
    for j in range(rings+1):
        phi = math.pi*j/rings
        for i in range(segments):
            theta = 2*math.pi*i/segments
            n = (math.sin(phi)*math.cos(theta), math.sin(phi)*math.sin(theta), math.cos(phi))
            vertices.append(((n[0]*radius, n[1]*radius, n[2]*radius+radius), n, color))
    for j in range(rings):
        for i in range(segments):
            a, b = j*segments+i, j*segments+(i+1)%segments
            c, d = (j+1)*segments+i, (j+1)*segments+(i+1)%segments
            triangles.extend(((a,b,d),(a,d,c)))
    node = _geom_node(name, vertices, triangles)
    apply(node, color_name, neon)
    node.set_python_tag("dimensions_m", (radius*2, radius*2, radius*2))
    return node


def _target(layout):
    root = NodePath("cyber-target")
    radius = layout["ball_diameter_m"]/layout["course_scale"]*.72
    cup = _disc("target-cup", radius*.48, .001/layout["course_scale"],
                "ridge", neon=False)
    cup.reparent_to(root)
    for i, (name, outer, inner, z) in enumerate(
            (("lime", 1., .78, .002), ("cyan", .67, .52, .003))):
        ring = _ring(f"target-ring-{i}", radius*outer, radius*inner,
                     z/layout["course_scale"], name)
        ring.reparent_to(root)
    beacon = LineSegs("target-hologram-beacon")
    beacon.set_thickness(4); beacon.set_color(*rgba("lime"))
    beacon.move_to(0, 0, 0); beacon.draw_to(0, 0, radius*1.8)
    beacon_node = root.attach_new_node(beacon.create())
    beacon_node.set_python_tag("neon", True)
    root.set_python_tag("dimensions_m", (radius*2, radius*2, .005/layout["course_scale"]))
    return root


def _attach_collision(root, layout, positions, triangles):
    """Static Bullet triangle mesh built from the exact visible vertices."""
    try:
        from panda3d.bullet import BulletRigidBodyNode, BulletTriangleMesh, BulletTriangleMeshShape
        mesh = BulletTriangleMesh()
        flat = [p for row in positions for p in row]
        for a, b, c in triangles:
            mesh.add_triangle(Vec3(*flat[a]), Vec3(*flat[b]), Vec3(*flat[c]), True)
        body = BulletRigidBodyNode("cyber-terrain-static-body")
        body.set_mass(0)
        body.add_shape(BulletTriangleMeshShape(mesh, dynamic=False))
        node = root.attach_new_node(body)
        node.set_python_tag("terrain_mesh", mesh)
        return node
    except ImportError:
        print("[cyber] Panda Bullet unavailable; terrain collision body omitted", file=sys.stderr)
        return None


def build_course(stage, manager, width, length, layout=None,
                 course_scale=None, ball_diameter=None):
    course_scale = float(course_scale or COURSE_SCALE)
    ball_diameter = float(ball_diameter or BALL_DIAMETER_M)
    if layout is None:
        # The explicit legacy/fixed option is now a deterministic cyber style proof.
        layout = course_generator.generate(4242, width, length, "medium",
                                           course_scale=course_scale,
                                           ball_diameter_m=ball_diameter)
    valid, detail = course_generator.validate(layout)
    if not valid:
        raise ValueError(f"invalid cyber course: {detail}")
    root = stage.attach_new_node("golf-course")
    root.set_python_tag("course_scale", course_scale)
    root.set_python_tag("layout", layout)
    placed = []
    terrain, positions, triangles = _terrain(layout)
    terrain.reparent_to(root); placed.append(terrain)
    sides = _terrain_sides(layout, positions); sides.reparent_to(root); placed.append(sides)
    ribbon = _ribbon(layout, positions); ribbon.reparent_to(root); placed.append(ribbon)
    _attach_collision(root, layout, positions, triangles)
    for i, hazard in enumerate(layout["hazards"]):
        color_name = "magenta" if i % 2 else "cyan"
        rim = _disc(f"plasma-rim-{i}", hazard["radius_m"]*1.16, 0,
                    "ridge", layout["seed"]+i, neon=False)
        rim.set_pos(*hazard["position"])
        rim.set_z(rim.get_z()-.0004/course_scale)
        rim.reparent_to(root); placed.append(rim)
        pool = _disc(f"plasma-pool-{i}", hazard["radius_m"], 0,
                     color_name, layout["seed"]+i, segments=40)
        pool.set_pos(*hazard["position"])
        pool.set_python_tag("dimensions_m", (hazard["radius_m"]*2,
                                             hazard["radius_m"]*2, .002))
        pool.reparent_to(root); placed.append(pool)
        halo = _ring(f"plasma-edge-{i}", hazard["radius_m"]*1.12,
                     hazard["radius_m"]*1.02, .0004/course_scale, color_name,
                     segments=40)
        halo.set_pos(*hazard["position"])
        halo.reparent_to(root); placed.append(halo)
    for i, obstacle in enumerate(layout["obstacles"]):
        size = obstacle["footprint_m"]
        if obstacle["kind"] == "crystal":
            obj = _box(f"cyber-crystal-{i}", size*.72, size*1.15, "magenta")
            obj.set_h(45)
        else:
            obj = _box(f"cyber-barrier-{i}", size, size*.65, "secondary")
        obj.set_pos(*obstacle["position"])
        obj.reparent_to(root); placed.append(obj)
    target = _target(layout)
    hx, hy = layout["hole"]
    target.set_pos(hx, hy, course_generator.terrain_height(layout, hx, hy)+.001)
    target.reparent_to(root); placed.append(target)
    # Stored layout dimensions are authoritative for rendering and validation.
    ball_diameter = float(layout["ball_diameter_m"])
    radius = ball_diameter/2
    ball = _sphere("cyber-ball", radius, "white", neon=False)
    sx, sy = layout["start"]
    ball.set_pos(sx, sy, course_generator.terrain_height(layout, sx, sy))
    ball.set_scale(1/course_scale)  # only gameplay-size compensation
    ball.set_python_tag("collision_radius_m", radius)
    ball.reparent_to(root); placed.append(ball)
    # Cyan seam remains visible from every direction.
    seam = _disc("ball-cyan-seam", radius*.32, radius*2+.0002, "cyan", segments=16)
    seam.reparent_to(ball)
    for item in layout["decor"]:
        try:
            node = manager.load(item["asset"], target=item["target"])
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"[cyber] missing {item['asset']}; procedural placeholder: {exc}",
                  file=sys.stderr)
            node = _box("cyber-placeholder", item["footprint_m"],
                        item["target"][1], "secondary")
        node.set_pos(*item["position"])
        node.set_hpr(*item.get("rotation", [0, 0, 0]))
        node.reparent_to(root); placed.append(node)
    debug = root.attach_new_node("course-debug")
    lines = LineSegs("route-debug")
    lines.set_thickness(4); lines.set_color(*rgba("lime"))
    for i, (x, y) in enumerate(layout["route"]):
        z = course_generator.terrain_height(layout, x, y)+.004/course_scale
        (lines.move_to if i == 0 else lines.draw_to)(x, y, z)
    debug.attach_new_node(lines.create())
    debug.hide()
    root.set_python_tag("debug_node", debug)
    root.set_python_tag("neon_enabled", True)
    root.set_python_tag("animated_neon", [node for node in root.find_all_matches("**/*")
                                          if node.get_python_tag("neon")])
    return root, placed


def _lines(parent, name, segments, color):
    lines = LineSegs(name); lines.set_thickness(2); lines.set_color(*color)
    for a, b in segments:
        lines.move_to(*a); lines.draw_to(*b)
    return parent.attach_new_node(lines.create())


class Gallery:
    def __init__(self, stage, manager, base):
        self.root = stage.attach_new_node("cyberpunk-gallery")
        self.manager, self.base = manager, base
        self.ids = manager.available()
        self.index, self.model, self.label = 0, None, None
        self.debug = self.root.attach_new_node("gallery-debug")
        self.show()

    def show(self):
        if self.model: self.model.remove_node()
        self.debug.node().remove_all_children()
        name = self.ids[self.index]
        self.model = self.manager.load(name, target=("max", .16))
        self.model.reparent_to(self.root)
        dims = self.model.get_python_tag("dimensions_m")
        if self.label: self.label.destroy()
        from direct.gui.OnscreenText import OnscreenText
        self.label = OnscreenText(text=f"{self.index+1}/{len(self.ids)} {name}\n"
                                  f"{dims[0]*100:.1f} × {dims[1]*100:.1f} × {dims[2]*100:.1f} cm",
                                  pos=(-1.25,.88), scale=.045, align=TextNode.ALeft,
                                  fg=rgba("cyan"), mayChange=True)

    def cycle(self, direction):
        self.index = (self.index+direction) % len(self.ids); self.show()

    def rotate(self, degrees): self.model.set_h(self.model.get_h()+degrees)
    def toggle_debug(self): self.debug.show() if self.debug.is_hidden() else self.debug.hide()
