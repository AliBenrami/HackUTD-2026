"""Declarative tabletop course and small on-demand asset inspector."""
import json
import math
from pathlib import Path
import sys

from panda3d.core import (Geom, GeomNode, GeomTriangles, GeomVertexData,
                          GeomVertexFormat, GeomVertexWriter, LineSegs, TextNode)

LAYOUT = Path(__file__).resolve().parents[1] / "assets" / "golf_demo.json"
GALLERY = ["golf_start", "golf_ramp", "golf_hole-round", "golf_flag-red",
           "golf_ball-red", "golf_windmill", "golf_obstacle-diamond",
           "nature_rock_largeA", "nature_rock_smallA", "nature_tree_default",
           "nature_plant_bush", "grab3d_pond"]


def _water(parent):
    """Opaque cyan water inset inside the downloaded pond's real 3D rim."""
    data = GeomVertexData("water", GeomVertexFormat.get_v3(), Geom.UH_static)
    vertex = GeomVertexWriter(data, "vertex")
    vertex.add_data3(0, 0, 0)
    for i in range(25):
        angle = i * 2 * math.pi / 24
        vertex.add_data3(.052 * math.cos(angle), .045 * math.sin(angle), 0)
    triangles = GeomTriangles(Geom.UH_static)
    for i in range(24):
        triangles.add_vertices(0, 1 + i, 2 + i)
    geom = Geom(data)
    geom.add_primitive(triangles)
    node = GeomNode("pond-water")
    node.add_geom(geom)
    water = parent.attach_new_node(node)
    water.set_color(.05, .78, 1.0, 1)
    water.set_light_off(1)
    water.set_two_sided(True)
    return water


def build_course(stage, manager, width, length, layout=LAYOUT):
    data = json.loads(Path(layout).read_text())
    if data.get("scene") != "golf-demo":
        raise ValueError("Expected golf-demo layout")
    root = stage.attach_new_node("golf-course")
    placed = []
    # Uniform fit for different configured tabletops (layout authored for 60 x 40 cm).
    fit = min(1.0, width / .60, length / .40)
    root.set_scale(fit)
    for item in data["objects"]:
        try:
            node = manager.load(item["asset"])
        except (FileNotFoundError, KeyError, ValueError) as exc:
            print(f"[golf] skipped {item['asset']}: {exc}", file=sys.stderr)
            continue
        node.reparent_to(root)
        node.set_pos(*item["position"])
        node.set_hpr(*item.get("rotation", [0, 0, 0]))
        node.set_scale(item.get("scale", 1.0))
        if item["asset"] == "golf_ball-red":
            node.set_texture_off(1)
            node.set_material_off(1)
            node.set_color(1, 1, 1, 1)
        elif item["asset"] == "grab3d_pond":
            water = _water(root)
            water.set_pos(item["position"][0], item["position"][1], .031)
        placed.append(node)
    return root, placed


def _lines(parent, name, segments, color):
    lines = LineSegs(name)
    lines.set_thickness(2)
    lines.set_color(*color)
    for a, b in segments:
        lines.move_to(*a)
        lines.draw_to(*b)
    return parent.attach_new_node(lines.create())


class Gallery:
    def __init__(self, stage, manager, base):
        self.root = stage.attach_new_node("golf-gallery")
        self.manager = manager
        self.base = base
        self.ids = [name for name in GALLERY if name in manager.available()]
        self.index = 0
        self.model = None
        self.debug = self.root.attach_new_node("gallery-debug")
        self.label = None
        self.show()

    def show(self):
        if self.model:
            self.model.remove_node()
        self.debug.node().remove_all_children()
        name = self.ids[self.index]
        self.model = self.manager.load(name)
        self.model.reparent_to(self.root)
        dims = self.model.get_python_tag("dimensions_m")
        x, y, z = (d / 2 for d in dims)
        c = [(-x, -y, 0), (x, -y, 0), (x, y, 0), (-x, y, 0),
             (-x, -y, z * 2), (x, -y, z * 2), (x, y, z * 2), (-x, y, z * 2)]
        edges = [(i, (i + 1) % 4) for i in range(4)] + [
            (i + 4, (i + 1) % 4 + 4) for i in range(4)] + [(i, i + 4) for i in range(4)]
        _lines(self.debug, "bounds", [(c[a], c[b]) for a, b in edges], (1, 1, 1, 1))
        for endpoint, color in [((.15, 0, 0), (1, .2, .2, 1)),
                                ((0, .15, 0), (.2, 1, .2, 1)),
                                ((0, 0, .15), (.3, .5, 1, 1))]:
            _lines(self.debug, "axis", [((0, 0, 0), endpoint)], color)
        if self.label:
            self.label.destroy()
        from direct.gui.OnscreenText import OnscreenText
        self.label = OnscreenText(text=f"{self.index+1}/{len(self.ids)} {name}  "
                                  f"{dims[0]*100:.1f} x {dims[1]*100:.1f} x {dims[2]*100:.1f} cm\n"
                                  "Tab/Shift-Tab browse   ;/' rotate   B bounds/axes",
                                  pos=(-1.25, .88), scale=.045, align=TextNode.ALeft,
                                  fg=(1, 1, 1, 1), mayChange=True)

    def cycle(self, direction):
        self.index = (self.index + direction) % len(self.ids)
        self.show()

    def rotate(self, degrees):
        self.model.set_h(self.model.get_h() + degrees)

    def toggle_debug(self):
        self.debug.show() if self.debug.is_hidden() else self.debug.hide()
