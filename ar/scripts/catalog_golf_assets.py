"""Inventory the downloaded archives; no model bytes are copied into git."""
import json
import os
from pathlib import Path
import zipfile

ROOT = Path(os.environ.get("HACKUTD_ASSETS_DIR", "~/hackutd26_assets")).expanduser()
OUT = Path(__file__).resolve().parents[1] / "assets" / "manifest.json"
PACKS = {
    "kenney_minigolf-kit.zip": ("golf", "Models/GLB format/", "License.txt"),
    "kenney_nature-kit.zip": ("nature", "Models/GLTF format/", "License.txt"),
    "grab3d-basket-2026-11-08.zip": ("grab3d", "", "LICENSE.txt"),
}


def category(pack, name):
    n = name.lower()
    if pack == "golf":
        return "golf"
    if any(s in n for s in ("pond", "lake", "river", "water", "puddle")):
        return "water"
    if any(s in n for s in ("rock", "pebble", "cliff", "boulder")):
        return "obstacles"
    if any(s in n for s in ("tree", "plant", "grass", "flower", "bush")):
        return "decoration"
    return "terrain"


def generate(root=ROOT):
    models = {}
    sources = {}
    existing = json.loads(OUT.read_text()).get("models", {}) if OUT.is_file() else {}
    for archive, (pack, prefix, license_file) in PACKS.items():
        with zipfile.ZipFile(root / archive) as z:
            if license_file not in z.namelist() or b"CC0" not in z.read(license_file):
                raise ValueError(f"Missing CC0 license in {archive}")
            sources[pack] = {"archive": archive, "license": license_file,
                             "terms": "CC0 1.0"}
            for member in z.namelist():
                if not member.startswith(prefix) or not member.lower().endswith(".glb"):
                    continue
                name = Path(member).stem
                asset_id = f"{pack}_{name}"
                models[asset_id] = {"source": pack, "member": member,
                                    "category": category(pack, name)}
                for override in ("target", "bundled"):
                    if override in existing.get(asset_id, {}):
                        models[asset_id][override] = existing[asset_id][override]
    return {"sources": sources, "models": dict(sorted(models.items()))}


if __name__ == "__main__":
    OUT.parent.mkdir(exist_ok=True)
    data = generate()
    OUT.write_text(json.dumps(data, indent=2) + "\n")
    print(f"{len(data['models'])} licensed GLB models -> {OUT}")
