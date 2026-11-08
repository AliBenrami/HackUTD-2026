"""Stage the licensed reference pack for Unity's glTF importer."""

import argparse
import json
from pathlib import Path
from zipfile import ZipFile


def main():
    project = Path(__file__).resolve().parents[1]
    manifest = json.loads((project.parent / "ar" / "assets" / "manifest.json").read_text())
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("archive", type=Path)
    args = parser.parse_args()
    models = manifest["models"]
    destination = project / "Assets" / "Resources" / "CyberpunkModels"
    with ZipFile(args.archive) as pack:
        missing = [item["member"] for item in models.values() if item["member"] not in pack.namelist()]
        if missing:
            parser.error(f"archive is missing {', '.join(missing)}")
        destination.mkdir(parents=True, exist_ok=True)
        for name, item in models.items():
            (destination / f"{name}.glb").write_bytes(pack.read(item["member"]))
    (destination / "catalog.txt").write_text("\n".join(models) + "\n")
    print(f"Staged {len(models)} reference models in {destination}")


if __name__ == "__main__":
    main()
