"""Render-thread-only table-local obstacle models and simple static colliders."""
from panda3d.core import (BitMask32, CollisionBox, CollisionNode,
                          LineSegs, Point3)

ASSETS = {"rock": "cyber_neon_crate", "hill": "cyber_power_generator",
          "water": "cyber_traffic_hologram", "wall": "cyber_jersey_barrier",
          "generic": "cyber_neon_crate"}


class ObstacleVisuals:
    def __init__(self, parent, assets, default_height=.055):
        self.root = parent.attach_new_node("physical-obstacles")
        self.assets = assets
        self.default_height = default_height
        self.nodes = {}
        self.previews = {}
        self.mode = "highlight"  # optical see-through: no physical occlusion
        self.height_query = None

    def set_height_query(self, query):
        """Place overlays on generated terrain without moving measured XY."""
        self.height_query = query
        for node, _visual, _outline, item in self.nodes.values():
            node.set_z(float(query(item.x, item.y)) if query else 0)

    def place(self, item):
        if item.id in self.nodes:
            self.delete(item.id)
        node = self.root.attach_new_node(f"physical-obstacle-{item.id}")
        z = float(self.height_query(item.x, item.y)) if self.height_query else 0
        node.set_pos(item.x, item.y, z)
        node.set_h(item.angle)
        visual = node.attach_new_node("asset-overlay")
        asset_id = ASSETS[item.kind]
        try:
            # Physical collider/footprint is measured; the overlay may use a
            # different artistic scale, but must not inherit prop shrinkage.
            model = self.assets.load(asset_id, target=("xy", max(item.width, item.length)),
                                     prop_scale=1.0)
            model.reparent_to(visual)
        except (ValueError, FileNotFoundError, KeyError) as exc:
            print(f"[obstacle] asset unavailable: {exc}")
        line = LineSegs(f"footprint-{item.id}")
        line.set_thickness(3)
        line.set_color(.1, 1, .8, 1)
        x, y = item.width/2, item.length/2
        for i, (a, b) in enumerate(((-x,-y), (x,-y), (x,y), (-x,y), (-x,-y))):
            (line.move_to if i == 0 else line.draw_to)(a, b, .004)
        outline = node.attach_new_node(line.create())
        collider = CollisionNode(f"static-{item.kind}-{item.id}")
        height = self.default_height  # unmeasured physics proxy
        # Height is an unmeasured proxy, but XY must remain the *measured*
        # physical footprint even when the artistic overlay is rescaled.
        collider.add_solid(CollisionBox(Point3(0, 0, height/2),
                                        item.width/2, item.length/2,
                                        .003 if item.kind == "water" else height/2))
        collider.set_from_collide_mask(BitMask32.all_off())
        collider.set_into_collide_mask(BitMask32.bit(2) if item.kind == "water"
                                      else BitMask32.bit(1))
        collision_node = node.attach_new_node(collider)
        collision_node.hide()
        self.nodes[item.id] = (node, visual, outline, item)
        self._visibility(item.id)

    def _visibility(self, id):
        _, visual, outline, _ = self.nodes[id]
        if self.mode == "overlay":
            visual.show()
            outline.hide()
        else:
            visual.hide()
            outline.show()

    def toggle(self):
        self.mode = "overlay" if self.mode == "highlight" else "highlight"
        for id in self.nodes:
            self._visibility(id)
        return self.mode

    def delete(self, id):
        item = self.nodes.pop(id, None)
        if item:
            item[0].remove_node()

    def clear(self):
        for id in list(self.nodes):
            self.delete(id)
        self.show_candidates({})

    def show_candidates(self, candidates):
        for node in self.previews.values():
            node.remove_node()
        self.previews.clear()
        for id, (obj, _count) in candidates.items():
            if id in self.nodes:
                continue
            lines = LineSegs(f"candidate-{id}")
            lines.set_thickness(2)
            lines.set_color(1, .8, .1, 1)
            x, y = obj.width/2, obj.length/2
            for n, (px, py) in enumerate(((-x,-y), (x,-y), (x,y), (-x,y), (-x,-y))):
                (lines.move_to if n == 0 else lines.draw_to)(px, py, .008)
            node = self.root.attach_new_node(lines.create())
            node.set_pos(obj.x, obj.y, 0)
            node.set_h(obj.angle)
            self.previews[id] = node
