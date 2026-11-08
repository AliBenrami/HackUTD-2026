# AR PoC handoff (2026-11-07)

This is the **working-code map**, current verification record, and known-issues
list for the next contributor. Read [README.md](README.md) to run it,
[AR_POC.md](AR_POC.md) for tracking/optics history, and [ASSETS.md](ASSETS.md)
for model provenance and size/layout rules. Start in `ar/`, not the repository
root. The Git branch for this work is `ar_checkpoint1` (pushed to `origin`;
commits `00d79fd`, `f5b6f4a`). Do not silently assume a desktop screenshot
proves alignment through the glasses.

## What runs

* `uv run python src/ar_poc.py` defaults to the **golf-demo**, marker-anchored
  tabletop scene on the glasses. `--scene asset-gallery` shows one of twelve
  preview models at a time; `--scene calibration` restores the primitive
  diagnostic scene; `--calibrate` selects the separate optics calibration rig.
  Golf/gallery implicitly enable table mode; `--table` enables the tabletop
  tracker with the primitive calibration scene. `--help` is authoritative for
  flags and numerical defaults.
* Stack: NixOS/Hyprland, Python 3.12, Panda3D, `panda3d-gltf`, official Linux
  VITURE `libglasses.so` (proprietary SDK **not committed**). `flake.nix` sets
  `VITURE_SDK_LIB` from a local SDK checkout if present; otherwise set that
  environment variable yourself. The panel is a real DP output, not a virtual
  monitor. `providers.ViturePoseProvider` polls Carina 6DoF on a background
  thread; the render thread consumes pose snapshots. `--provider desktop
  --windowed --look 0,-15` is an **untracked** simulation preview; the desktop
  table is deliberately placed in front of the simulated head.
* The clear color is black for optical see-through. No RGB camera background
  is drawn in the normal path. The edge-fade effect is retained. Mono is the
  hardware-proven display path; SBS stereo code exists but is not validated
  on the working Linux display pipeline. No physical occlusion, physics,
  scoring, club tracking or binocular depth claim is made.

## Code and data flow

1. `src/ar_poc.py`: argument parsing, ShowBase/display setup, scene graph,
   keys, `VitureARApp._update` render task. `src/viture_sdk.py` provides ctypes
   SDK access; `src/providers.py` emits `(pos, quat, status, timestamp)` poses
   from hardware/desktop/synthetic sources. `src/pose_math.py` converts the
   SDK's GL-style world frame (X right, Y up, -Z forward) into Panda coordinates.
   The camera moves with the head; objects do **not** follow it. Do not change
   projection, `gl_space`, or head pose transforms to resize assets.
2. `src/tabletop.py`: camera frames are submitted to `MarkerDetector`'s
   worker. `TimeSync` maps frame timestamps to monotonic time (this SDK build
   has supplied zero device timestamps, so arrival-time fallback matters).
   `PoseHistory` interpolates head pose at image time; IPPE estimates the
   marker pose. `TableCalibrator` rejects bad/reprojection/gravity/inconsistent
   observations and forms an anchor. `TableTracker` handles APPROX/LOCKED,
   DEGRADED, LOST, correction, recenter carry and recovery. Defaults: printed
   ArUco `DICT_6X6_250`, ID 42, **100 mm marker**; configured table **0.60 ×
   0.40 m** (defaults, *not measured* dimensions). Generated target is
   `build/table_target.png`; generator: `scripts/make_table_target.py`.
3. `VitureARApp._update_table` publishes the accepted pose on `table-root`.
   Scene chain: `render → gl-space → table-root (tracking) → table-adjust
   (legacy manual table adjustment) → table-stage (legacy lift) →
   golf-stage-root (independent golf controls) → golf-course/gallery`. Table
   debug outline is under `table-root`, **not** the golf stage. Table-local XY
   is the surface; +Z is its normal. The stale world-space blue grid was
   removed. `table-root` remains hidden until an anchor exists on hardware.
4. `assets/manifest.json` records **489 CC0 GLBs** and archive member/license
   provenance. `src/golf_assets.py` resolves IDs, loads a bundled file first,
   otherwise extracts its GLB and any sibling colormap from the corresponding
   archive under `~/hackutd26_assets/.golf-cache/` (override with
   `--assets-dir` or `HACKUTD_ASSETS_DIR`). It caches the imported model in
   memory, applies glTF→Panda axis conversion via the loader, measures tight
   bounds, uniformly scales to metres, and returns independent bottom-centred
   placement pivots. Kenney Nature foliage/rock materials are recolored for
   optical visibility, not remeshed. Original ZIPs stay outside Git.
5. `assets/golf_demo.json` has **16 placements** using 13 bundled GLBs and a
   shared Kenney colormap (ordinary Git files, about 1.3 MB total). `src/golf_scene.py`
   reads the JSON, uniformly fits the authored 60 × 40 cm footprint to a
   smaller configured table, and adds a bright opaque cyan water inset inside
   the Grab3D pond's 3D shore. The golf ball's red asset is rendered white.
   Course/asset positions, rotations and per-object scales belong in JSON;
   asset IDs/size overrides belong in the manifest. The gallery lists its
   twelve selected models in `golf_scene.GALLERY`, and shows the current name,
   dimensions, bounding box and local axes. Only the **selected** GLBs are
   bundled: the other catalog entries require the original licensed archives.

## Live controls and calibration

* Golf-only **Shift+J/L**: local X; **Shift+I/K**: local Y;
  **Shift+U/O**: height; **Shift+,/.**: yaw; **Shift+[/]**: uniform
  scale; **Shift+9**: reset golf-stage placement. These affect
  `golf-stage-root`, not the calibrated marker transform.
* Legacy tabletop: **Y** scan on/off; **N** marker outline; **Z** freeze;
  **S** save; **0** restore; **1/2** lift; **3/4** yaw; **5/6** X;
  **7/8** Z; **9** clear; **C** attempt hand-eye solve. Those adjustments
  live in `table-adjust`/`table-stage`, separate from golf-stage controls.
  `R` recentres the pose provider and carries a known anchor. `D` toggles
  text diagnostics, `F` toggles edge fade, `Esc/Q` exits. Gallery:
  Tab/Shift+Tab browse, `;`/`'` rotate, `B` debug bounds/axes. `--manipulate`
  is a separate experimental hand/keyboard layer; some keys are context
  dependent. Avoid changing tracking/calibration to compensate for a model
  that looks too big or small.
* `table_calib.json` is **machine-local and ignored**, not a portable truth;
  it can contain saved intrinsics, hand-eye and/or anchor. With no hand-eye
  solution, the app uses an explicit approximate camera-to-head flip. Current
  alignment is functional but not metrically verified. For calibration, move
  through diverse head rotations while viewing the marker, press `C`, inspect
  residuals in logs, then `S`. Don't invent a new table-detection algorithm
  while working on visual assets.

## Verification and outstanding issues

From `ar/` after `nix develop && uv sync`:

```sh
PYTHONPATH=src uv run python -m unittest discover -s tests
uv run python src/ar_poc.py --scene golf-demo --smoke-frames 20
uv run python src/ar_poc.py --scene asset-gallery --smoke-frames 12
uv run python src/ar_poc.py --scene calibration --smoke-frames 12
uv run python src/ar_poc.py --provider desktop --windowed --look 0,-15
uv run python src/ar_poc.py --self-test  # checks live USB access
```

At handoff, **84 tests passed** and golf/gallery smoke runs also passed with
`HACKUTD_ASSETS_DIR=/tmp/opencode/no-archives` (bundled assets only). Desktop
golf was visually inspected from overhead, low angle and opposite side;
gallery and black background rendered. A GLSL compile warning from the
**existing edge-fade shader** appeared during desktop renders, although the
course still drew. No measurements establish physical placement accuracy or
new asset appearance through the glasses. Previous user testing found the
table anchor much better after state-machine fixes; **the golf scene has not
been walked around on hardware by the implementation agent**. Manual test:
show the printed marker, wait for `[table] anchor acquired`, inspect the hill,
pond, rocks and flag from multiple sides, look away and return, check stage
nudges and black-through-glass background, and record `[table] det/acc/rej`
and calibration logs. Never claim improved alignment from desktop screenshots.

**Hardware access:** the most recent agent `--self-test` saw product ID
`0x1104` but failed to open USB for writing (`Permission denied`). Local
`/etc/nixos/viture.nix` was changed to give group `users` `0660` access to
all USB device nodes (broader than the checked-in VITURE-specific sample rule);
`sudo nixos-rebuild switch` **failed on an unrelated VS Code package build**
(`rg` absent in its source tarball), so the change was *not confirmed active*.
Resolve that rebuild or otherwise arrange persistent device access, replug,
check node ownership and rerun self-test before live acceptance. The machine
configuration is outside this repository. Do not copy `etc/70-viture.rules`
directly into an immutable NixOS `/etc` and assume it persists.

**Tracking caveat worth inspecting before any next calibration change:**
`ar_poc.py:_table_on_detection` currently calls
`cal.observe(..., approx_ok=not approx)` while `TableCalibrator.observe` in
`tabletop.py` uses `approx_ok=True` to select relaxed APPROX gates and label.
That looks inverted. The tracker separately receives `approx` correctly;
this particular call site was **not corrected or live retested** as part of
the documentation handoff. Reproduce with live `[table] acc/rej` logs before
changing state-machine behavior; add a regression test if fixing it.

**Distribution:** the selected licensed models are ordinary Git blobs.
GitHub rejected Git LFS upload due to this repository's exhausted LFS
budget; the entire selected set is small enough for normal Git. The 66 MB
download archive directory, unlicensed drive archive, proprietary SDK,
downloaded MediaPipe hand model and personal `table_calib.json` are not in
Git. Do not re-add any without checking rights and necessity. The GitHub
branch was pushed after the normal-Git asset commit; keep future commits on
the user's selected branch and do not assume you should deploy the app.
