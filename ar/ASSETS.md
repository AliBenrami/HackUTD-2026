# Tabletop golf assets

Run from the Nix development shell (`nix develop`, then `uv sync`). The
`panda3d-gltf` dependency registers Panda3D's native Python GLB loader;
Panda3D converts glTF Y-up to Panda Z-up. No Blender conversion is needed for
the selected models. The original archives remain in `~/hackutd26_assets`.
Override this with `--assets-dir PATH` or `HACKUTD_ASSETS_DIR=PATH`.

## Inventory and provenance

`uv run python scripts/catalog_golf_assets.py` enumerates the licensed GLBs
into `assets/manifest.json` (489 models: 126 Kenney Minigolf Kit, 329 Kenney
Nature Kit, 34 Grab3D). It checks the CC0 license text inside each archive:

- `kenney_minigolf-kit.zip`: `License.txt`, Kenney Minigolf Kit 3.1, CC0.
- `kenney_nature-kit.zip`: `License.txt`, Kenney Nature Kit, CC0.
- `grab3d-basket-2026-11-08.zip`: `LICENSE.txt`, Grab3D, CC0 1.0; individual
  model links are included in that file.
- `drive-download-20261108T000721Z-1-001.zip`: 150 OBJ/MTL, FBX, and Blend
  models (the same model names in several formats); **no license found**.
  Not catalogued, extracted, or rendered until its provenance is confirmed.

The Kenney archives also contain FBX/OBJ versions, textures, previews and
license files. The minigolf GLBs reference an external
`Models/GLB format/Textures/colormap.png` despite the `.glb` extension;
the loader extracts that texture beside the selected model. Nature GLBs use
stylized material colors; foliage's shipped turquoise base color is overridden
to green and rock dirt to pale gray at load time, without changing geometry or
bark. Grab3D pond has embedded textured PBR geometry.
The manifest records the actual source archive, member path, category and
license provenance. Only the 13 GLBs used by the demo/gallery and their Kenney
colormap are bundled under `assets/models/` (about 1.3 MB total); original archives
and unlicensed models are **not** committed. The app loads bundled models
first, so the default demo works without `~/hackutd26_assets`. Any other
catalog entry is lazily extracted from its original archive to
`<assets-dir>/.golf-cache/`, with an in-process model cache to avoid repeat I/O.
Deleting `.golf-cache` regenerates it from the original ZIPs. OBJ/FBX/Blend
are not runtime-supported; convert a **licensed** source to GLB offline before
cataloguing it. Only GLB assets are currently selected.

## Metric layout

The GLB loader applies glTF-to-Panda axis conversion. Every asset is measured
from its Panda tight bounds and scaled *uniformly*. A fresh placement pivot
has its origin at the XY bounding-box centre and bottom Z; placement `z=0`
rests on the marker's tabletop plane. Orientation and original hierarchy stay
inside the pivot. `AssetManager.load(id)` returns independent placement nodes
sharing cached model data. For an asset's size override, add `"target":
["xy", 0.12]` or `["z", 0.18]` to its manifest entry. `xy` sizes the widest
horizontal dimension; `z` sizes height; `max` sizes the largest dimension.
The inventory generator preserves existing target overrides. Sizes in metres.

The layout `assets/golf_demo.json` gives each asset ID a `position` [x,y,z],
optional `rotation` [heading,pitch,roll] in degrees, and optional uniform
`scale`. Table-local +Z is the surface normal. The authoring footprint is
0.60 × 0.40 m (configured defaults, **not measured table dimensions**); the
course uniformly fits smaller configured tables. Objects are children of
`table-root/table-adjust/table-stage/golf-stage-root/golf-course` and never
the head camera. Edit JSON to add obstacles. Unknown optional assets are
skipped with an explicit log; the anchor and projection are unchanged.

Run `uv run python src/ar_poc.py --scene golf-demo` on the glasses (the
default), or `--scene asset-gallery` and Tab/Shift-Tab to browse the selected
models. `;`/`'` rotates a model; `B` toggles bounds and local XYZ axes; an
overlay shows ID and dimensions. `--scene calibration --table` retains the
old tabletop primitive diagnostics; `--calibrate` retains the optics rig.
Desktop preview (untracked, not a physical alignment check):
`uv run python src/ar_poc.py --provider desktop --windowed --look 0,-15`.

Golf-stage-only controls: Shift+J/L (table X), Shift+I/K (table Y),
Shift+U/O (height), Shift+,/. (yaw), Shift+[/] (uniform scale), Shift+9
(reset). The existing 1–9 table-adjust calibration controls are separate.

## Visual checks and limits

The demo uses 16 placements: Kenney start/straight/ramp/hole/flag/ball,
obstacle diamond and windmill; Kenney Nature rocks, trees and bushes; Grab3D
pond with an opaque cyan water inset inside its 3D shoreline. No skybox,
camera feed, collision or stereo change. The course renders on black and is
visible in desktop overhead, low-angle, opposite-side and gallery screenshots.
The reused GLB pond's
PBR shoreline may appear light under optical display lighting. The existing
edge-fade shader reports a GLSL compilation warning on this machine; the
course itself still renders in desktop mono mode. Physical alignment, correct
*glasses* multi-angle display and world lock **still need a live user check**.
The hardware self-test found the headset (product ID `0x1104`) but failed to
open its USB device for writing (`Permission denied`); no live golf rendering
or anchor check was possible. A persistent NixOS rule change has been written
outside this repository but **not activated**, because `nixos-rebuild switch`
failed on an unrelated VS Code package; see [HANDOFF.md](HANDOFF.md).

Live check: ensure VITURE device permissions (`uv run python src/ar_poc.py
--self-test`), then run the default scene with the ArUco marker visible.
Wait for `[table] anchor acquired`; walk around to inspect slope, pond, flag,
and rocks from both sides, look away and back, use stage controls if needed,
and verify black regions reveal the real tabletop. Use `D`/`N` for debug
overlay and marker-aligned outline. Do not infer physical accuracy from the
desktop preview. If the self-test reports `/dev/bus/usb/... Permission denied`,
activate appropriate NixOS `services.udev.extraRules` through a successful
system rebuild, then replug the glasses before retrying. The checked-in
`etc/70-viture.rules` is a reference, not a mutable NixOS `/etc` install step.
