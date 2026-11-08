"""Cyberpunk GLB catalog: lazy extraction and metric contact pivots.

The restricted source archive stays outside Git.  Models are extracted on
demand, cached, and normalized exactly once per placement while preserving
their authored flat-shaded materials and vertex colors.
"""
import json
import os
from pathlib import Path
import zipfile

from panda3d.core import MaterialAttrib, NodePath, Texture

MANIFEST = Path(__file__).resolve().parents[1] / "assets" / "manifest.json"
DEFAULT_ROOT = "~/hackutd26_assets"

class AssetManager:
    def __init__(self, loader, root=None, manifest=MANIFEST,
                  prop_scale=1.0, anisotropic_degree=8):
        if not 0 < prop_scale <= 1:
            raise ValueError("prop_scale must be in (0, 1]")
        self.loader = loader
        self.prop_scale = float(prop_scale)
        self.anisotropic_degree = max(1, int(anisotropic_degree))
        self.root = Path(root or os.environ.get("HACKUTD_ASSETS_DIR", DEFAULT_ROOT)).expanduser()
        self.manifest_path = Path(manifest)
        self.catalog = json.loads(self.manifest_path.read_text())
        self.cache = self.root / ".cyberpunk-cache"
        self._models = {}
        self._bounds = {}

    def available(self):
        return list(self.catalog["models"])

    def _path(self, asset_id):
        entry = self.catalog["models"].get(asset_id)
        if entry is None:
            raise KeyError(f"Unknown cyberpunk asset {asset_id!r}; see assets/manifest.json")
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
        return dest

    def load(self, asset_id, target=None, prop_scale=None):
        """Independent placement pivot at the model's bottom XY centre.

        target: optional (axis, metres) override; default is a tabletop size
        for demo assets, otherwise 10 cm along the largest dimension.
        """
        if asset_id not in self._models:
            path = self._path(asset_id)
            model = self.loader.loadModel(str(path))
            if model.is_empty():
                raise ValueError(f"Could not load {asset_id}: {path}")
            lo, hi = model.get_tight_bounds()
            if lo is None:
                raise ValueError(f"Empty mesh: {asset_id}")
            dims = tuple(float(hi[i] - lo[i]) for i in range(3))
            if min(dims) < 0 or max(dims) <= 0:
                raise ValueError(f"Invalid bounds: {asset_id} {dims}")
            textures = model.find_all_textures()
            for i in range(textures.get_num_textures()):
                texture = textures.get_texture(i)
                texture.set_magfilter(Texture.FT_linear)
                texture.set_minfilter(Texture.FT_linear_mipmap_linear)
                texture.set_anisotropic_degree(self.anisotropic_degree)
            # Authored glTF colours stay untouched; only the response to the
            # scene lights is lifted so non-emissive props gain form.
            for geom_node in model.find_all_matches("**/+GeomNode"):
                geom = geom_node.node()
                for index in range(geom.get_num_geoms()):
                    attrib = geom.get_geom_state(index).get_attrib(MaterialAttrib)
                    if attrib is None:
                        continue
                    mat = attrib.get_material()
                    emission = mat.get_emission()
                    if any(emission[i] > .02 for i in range(3)):
                        # Keep authored neon hues, but avoid full-white clipping
                        # and oversized bloom halos on large sign faces.
                        mat.set_emission((emission[0]*.8, emission[1]*.8,
                                          emission[2]*.8, emission[3]))
                        continue
                    mat.set_roughness(min(mat.get_roughness(), .68))
                    mat.set_metallic(max(mat.get_metallic(), .12))
                    mat.set_specular((.18, .22, .26, 1))
                    mat.set_shininess(18)
            self._models[asset_id] = model
            self._bounds[asset_id] = (tuple(lo), dims)
        lo, dims = self._bounds[asset_id]
        entry = self.catalog["models"][asset_id]
        axis, metres = target or entry.get("target") or ("max", .10)
        extent = {"xy": max(dims[:2]), "z": dims[2], "max": max(dims)}[axis]
        if extent <= 0 or metres <= 0:
            raise ValueError(f"Invalid size for {asset_id}: {extent}, {metres}")
        multiplier = self.prop_scale if prop_scale is None else prop_scale
        if not 0 < multiplier <= 1:
            raise ValueError("prop_scale must be in (0, 1]")
        scale = metres / extent * multiplier
        pivot = NodePath(asset_id)
        geometry = pivot.attach_new_node("normalized-model")
        instance = self._models[asset_id].copy_to(geometry)
        instance.set_pos(-(lo[0] + dims[0] / 2) * scale,
                         -(lo[1] + dims[1] / 2) * scale, -lo[2] * scale)
        instance.set_scale(scale)
        pivot.set_python_tag("dimensions_m", tuple(d * scale for d in dims))
        pivot.set_python_tag("texture_filter", f"trilinear/{self.anisotropic_degree}x")
        return pivot
