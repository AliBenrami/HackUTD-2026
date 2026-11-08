"""Licensed GLB catalog: lazy extraction, shared model data, metric contact pivots."""
import json
import os
from pathlib import Path
import zipfile

from panda3d.core import Material, MaterialAttrib, NodePath

MANIFEST = Path(__file__).resolve().parents[1] / "assets" / "manifest.json"
DEFAULT_ROOT = "~/hackutd26_assets"

# Dominant dimension in metres, selected for tabletop readability.
TARGETS = {"golf_ball-red": ("xy", .045), "golf_flag-red": ("z", .17),
           "golf_start": ("xy", .115), "golf_straight": ("xy", .115),
           "golf_hole-round": ("xy", .115), "golf_ramp": ("xy", .115),
           "golf_hill-round": ("xy", .115), "golf_windmill": ("z", .15),
           "golf_obstacle-diamond": ("xy", .115),
           "nature_rock_largeA": ("xy", .10),
           "nature_rock_smallA": ("xy", .06),
           "nature_tree_default": ("z", .19),
           "nature_plant_bush": ("xy", .09),
           "grab3d_pond": ("xy", .17)}


class AssetManager:
    def __init__(self, loader, root=None, manifest=MANIFEST):
        self.loader = loader
        self.root = Path(root or os.environ.get("HACKUTD_ASSETS_DIR", DEFAULT_ROOT)).expanduser()
        self.manifest_path = Path(manifest)
        self.catalog = json.loads(self.manifest_path.read_text())
        self.cache = self.root / ".golf-cache"
        self._models = {}
        self._bounds = {}

    def available(self):
        return list(self.catalog["models"])

    def _path(self, asset_id):
        entry = self.catalog["models"].get(asset_id)
        if entry is None:
            raise KeyError(f"Unknown golf asset {asset_id!r}; see assets/manifest.json")
        if "bundled" in entry:
            bundled = self.manifest_path.parent / entry["bundled"]
            if bundled.is_file():
                return bundled
        source = self.catalog["sources"][entry["source"]]
        archive = self.root / source["archive"]
        if not archive.is_file():
            raise FileNotFoundError(f"Missing asset archive: {archive} (--assets-dir)")
        member = entry["member"]
        dest = self.cache / source["archive"].removesuffix(".zip") / member
        with zipfile.ZipFile(archive) as z:
            if not dest.is_file() or dest.stat().st_size != z.getinfo(member).file_size:
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(z.read(member))
            # Kenney GLBs refer to a sibling external colormap, despite .glb.
            texture = str(Path(member).parent / "Textures/colormap.png")
            if texture in z.namelist():
                tex_dest = dest.parent / "Textures/colormap.png"
                if not tex_dest.is_file():
                    tex_dest.parent.mkdir(exist_ok=True)
                    tex_dest.write_bytes(z.read(texture))
        return dest

    def load(self, asset_id, target=None):
        """Independent placement pivot at the model's bottom XY centre.

        target: optional (axis, metres) override; default is a tabletop size
        for demo assets, otherwise 10 cm along the largest dimension.
        """
        if asset_id not in self._models:
            path = self._path(asset_id)
            model = self.loader.loadModel(str(path))
            if model.is_empty():
                raise ValueError(f"Could not load {asset_id}: {path}")
            if asset_id.startswith("nature_"):
                # This particular Kenney Nature variant ships turquoise
                # 'leafsGreen' / 'grass' base colors. Keep the authored mesh,
                # UVs and wood, but align foliage with the golf kit's greens.
                for geom in model.find_all_matches("**/+GeomNode"):
                    gn = geom.node()
                    for i in range(gn.get_num_geoms()):
                        state = gn.get_geom_state(i)
                        attrib = state.get_attrib(MaterialAttrib)
                        if attrib is None:
                            continue
                        original = attrib.get_material()
                        color = ({"leafsGreen": (.18, .85, .21, 1),
                                  "grass": (.18, .86, .22, 1)}.get(original.get_name()))
                        if original.get_name() == "dirt" and asset_id.startswith("nature_rock"):
                            color = (.73, .76, .78, 1)
                        if color:
                            material = Material(original)
                            material.set_base_color(color)
                            gn.set_geom_state(i, state.set_attrib(MaterialAttrib.make(material)))
            lo, hi = model.get_tight_bounds()
            if lo is None:
                raise ValueError(f"Empty mesh: {asset_id}")
            dims = tuple(float(hi[i] - lo[i]) for i in range(3))
            if min(dims) < 0 or max(dims) <= 0:
                raise ValueError(f"Invalid bounds: {asset_id} {dims}")
            self._models[asset_id] = model
            self._bounds[asset_id] = (tuple(lo), dims)
        lo, dims = self._bounds[asset_id]
        entry = self.catalog["models"][asset_id]
        axis, metres = target or entry.get("target") or TARGETS.get(asset_id, ("max", .10))
        extent = {"xy": max(dims[:2]), "z": dims[2], "max": max(dims)}[axis]
        if extent <= 0 or metres <= 0:
            raise ValueError(f"Invalid size for {asset_id}: {extent}, {metres}")
        scale = metres / extent
        pivot = NodePath(asset_id)
        geometry = pivot.attach_new_node("normalized-model")
        instance = self._models[asset_id].copy_to(geometry)
        instance.set_pos(-(lo[0] + dims[0] / 2) * scale,
                         -(lo[1] + dims[1] / 2) * scale, -lo[2] * scale)
        instance.set_scale(scale)
        pivot.set_python_tag("dimensions_m", tuple(d * scale for d in dims))
        return pivot
