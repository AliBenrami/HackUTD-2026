# Viture Luma Ultra AR PoC (Python + Panda3D)

Native optical AR for the **VITURE Luma Ultra** XR glasses: a miniature
golf scene on a marker-anchored physical tabletop, viewed with Carina 6DoF
head tracking. No virtual monitors, no desktop capture,
no video passthrough in the default path — one fullscreen window on
the glasses output, pure-black clear (invisible on the additive
combiner), only virtual geometry emits light.

Start with [HANDOFF.md](HANDOFF.md) if taking over this work. See
[AR_POC.md](AR_POC.md) for tracking and optics, and [ASSETS.md](ASSETS.md)
for model provenance and layout.

## Layout

```
flake.nix            # dev environment (Python 3.12 + uv + system libs)
pyproject.toml       # uv dependencies (Panda3D, glTF loader, etc.)
.python-version      # 3.12
src/
  ar_poc.py          # the PoC: window, regions/cameras, render loop
  viture_sdk.py      # ctypes bindings for libglasses.so (+ camera, display modes)
  providers.py       # pose providers: viture (threaded) / desktop / synthetic
  pose_math.py       # GL<->Panda basis change, quats, view matrices (tested)
  ar_scene.py        # calibration scene and marker-aligned table outline
  video_bg.py        # legacy world-locked video panel (opt-in via --video-panel)
tests/
  test_pose_math.py  # conversion tests; see also test_tabletop/test_golf_assets
etc/
  70-viture.rules    # udev rules so the SDK can claim USB without root
HANDOFF.md            # current state, architecture and verification handoff
AR_POC.md             # tracking, optics and early PoC history
ASSETS.md             # model catalog, licenses, size and layout
```

The proprietary **VITURE SDK is not vendored** (same policy as the
reference repo at `/home/jude/Repos/Viture_AR_Playground`, whose
`02_ar_overlay`/`common/carina_pose.c` this follows). It is resolved at
runtime from `$VITURE_SDK_LIB` (file or arch dir); the flake shellHook
defaults it to the reference checkout's unpacked blobs.

## Setup

```sh
nix develop
uv sync

# On NixOS, add USB rules via services.udev.extraRules in the system config,
# then sudo nixos-rebuild switch and replug. See HANDOFF.md for this machine.
```

`etc/70-viture.rules` is a sample for mutable udev setups. On this NixOS
machine, `/etc/nixos/viture.nix` is imported but its newest USB permission
change has **not** been activated: a system rebuild failed on an unrelated
VS Code package. See [HANDOFF.md](HANDOFF.md#verification-and-outstanding-issues).

## Run

```sh
uv run python src/ar_poc.py --self-test        # hardware check, no window
uv run python src/ar_poc.py --list-displays    # find the glasses output
uv run python src/ar_poc.py --provider desktop --windowed   # sim preview
uv run python src/ar_poc.py --provider desktop --windowed --calibrate  # rig
uv run python src/ar_poc.py --render-mode stereo --windowed # SBS preview
uv run python src/ar_poc.py --provider desktop --windowed --manipulate  # hands
PYTHONPATH=src uv run python -m unittest discover -s tests  # all tests
uv run python src/ar_poc.py                    # glasses, auto mode
uv run python src/ar_poc.py --scene asset-gallery # inspect downloaded assets
uv run python src/ar_poc.py --scene calibration --table # original primitive table
```

Fullscreen auto-targets the VITURE output (move + real fullscreen via
`hyprctl` dispatch; `--no-place` skips it). Details, projection
settings (`--fov/--hfov/--near/--far`), calibration, stereo, and the
optics-vs-software verdict live in [AR_POC.md](AR_POC.md).
The default is now the licensed, asset-based tabletop golf demo. See
[ASSETS.md](ASSETS.md) for archive provenance, metric layout and stage controls.
The selected CC0 models are bundled with the repository; the original archives
remain optional for browsing the full catalog.

## Physical tabletop obstacles (experimental)

With the marker anchor active and an **empty** physical playing area visible,
press **Shift+B** to collect seven RGB views for an in-memory baseline. Automatic
obstacle detection then starts (Shift+A pauses/resumes it). Place a cup or box,
remove your hand, and keep the area in view until five consistent observations
produce a table-local rock or highlight. No marker is needed on the object.
**Shift+S** starts a manual scan even if automatic mode is off; amber candidate
footprints appear on the table, **Shift+Tab** selects one and **Shift+C** confirms
it. **Shift+R** rejects the selected candidate. The baseline is never silently
updated; remove pre-existing objects and press Shift+B again if needed.

Obstacle controls: **Shift+V** full asset/highlight, **Shift+H** rock/hill/water/
wall/generic, **Shift+arrows** adjust position, **Shift+-/=** adjust size,
**Shift+X** remove selected, **Shift+D** clear all, **Shift+P** save and
**Shift+0** reload `obstacle_layout.json` (machine-local, ignored). **Shift+M**
masks the selected permanent feature for the session; recapture baseline after.
`--obstacle-debug` opens an optional laptop-only RGB/rectified/baseline/mask
diagnostic window; `--obstacle-resolution` sets top-down pixels per metre.
`--obstacle-height` sets the unmeasured collider proxy height (default 5.5 cm).
The glasses never show the camera feed. This path is unverified on hardware;
see [AR_POC.md](AR_POC.md#physical-object-obstacles-experimental) for limits.

## Neon Cyber Golf terrain

Procedural generation is the default: launching with no `--scene` flag builds
a fresh continuous cyberpunk terrain on the calibrated table. A random seed is
logged; pass `--seed`/`--course-seed 12345` to reproduce it. `--scene
fixed-demo` (legacy alias `golf-demo`) now shows a deterministic cyberpunk
style proof; it does not load the removed traditional assets.
`--scene procedural --difficulty easy|medium|hard --seed 12345`
builds a reproducible course on the same tracked table. **Alt+1/2/3** switches
difficulty, **Alt+G** selects a new random seed, **Alt+R** regenerates the
current seed, **Alt+F** restores the cyber style proof, **Alt+Z** restores the
previous layout. **Alt+V** toggles route/validation geometry, **Alt+N** toggles
neon accents, and **Alt+B** toggles optional subtle desktop bloom. For a
specific runtime seed,
press **Alt+T**, type digits with **Ctrl+0..9**, then **Alt+Enter**. **Alt+S**
saves the generated layout to `course_layout.json`; **Alt+L** reloads it after
table-size validation. `--course-layout PATH` overrides the save path.
Every generation logs a `[golf-report]` block (seed, difficulty, archetype,
dimensions, segments, turns, obstacle/decor counts, direct obstruction,
traversable route, attempts, validation).
`--course-margin` (default 3 cm) and `--course-decor` (default 4) control
physical edge margin and city-detail density. At 60×40 cm the generated island
uses 54×34 cm. Low-frequency domain-warped macro noise (3 octaves), one broad
seeded ridge, plus a corner mesa and opposite basin give deliberate hills,
valleys and cliffs; the smooth route corridor sculpts that terrain and flattens
start/target pads. Easy is broad (12.0 cm fairway) and gentle, Medium bends
(9.0 cm) with partial barriers, and Hard narrows (6.5 cm), climbs and directly
obstructs shortcuts while retaining the intended route. Fairway is dark teal
with bright cyan edges and lime direction dashes, never a uniform bright river.
`--course-scale 0.25` (default) scales the **entire assembled course** uniformly
on `course-scale-root` (child of `golf-stage-root`: `table-stage` →
`golf-stage-root` (manual nudge: position/yaw, scale always 1.0) →
`course-scale-root` (the single authoritative scale) → `golf-course` →
terrain, fairway, plasma, barriers, city props, ball/target). Geometry
and relative positions scale together. The tabletop anchor, tracking, camera,
calibration and physical table bounds are not scaled.
`--ball-diameter 0.022` (default, metres) keeps the golf ball independently
configurable in 0.020–0.043: geometry, collision radius, hole clearance and
validation all follow it. Stage scaling never changes its world diameter (the
ball node compensates by exactly 1/scale). **Shift+[ / Shift+]** retune the whole-course
scale live between **0.10–1.00** without restart or recalibration; **Shift+9**
resets to 0.25. Per-asset size overrides remain available in
`assets/manifest.json`. Saved procedural layouts record their course scale;
legacy `prop_scale` layouts are rejected and must be regenerated.
Physical-object colliders remain measured size.

The visible terrain and static Bullet triangle mesh share the same vertices;
full ball dynamics, swing physics, scoring and tracked club remain deferred. The
physical-object obstacle layer remains a sibling of the course scene and is
untouched by regeneration. See [ASSETS.md](ASSETS.md) for physical sizes and
[AR_POC.md](AR_POC.md) for geometry-validation limits.

Graphics presets: `--quality performance|balanced|quality` (default
`balanced`). Performance uses a 65² grid, fixed-function lighting, 4×
anisotropic filtering, no sRGB framebuffer and no bloom; Balanced uses a 97²
grid, per-pixel shader-auto lighting, trilinear 8× filtering and sRGB;
Quality uses a 129² grid, sRGB and restrained bloom. Requested MSAA is
2/4/8; this AMD 680M driver reports actual 8 in all three modes
(24-bit RGB + 24-bit depth). Bloom is opt-in (Balanced off, Quality on),
configurable via `--bloom --bloom-threshold 0.70 --bloom-intensity 0.55
--bloom-size small`, and uses blend `(.30,.40,.30,0.0)` so only bright neon
blooms — the pure-black clear stays black for optical see-through. Bloom
offscreen buffers report MSAA 4 (Balanced) / 8 (Quality), so AA survives
postprocessing. `--graphics-debug` logs framebuffer, preset, ball/fairway/
terrain/mesh counts, texture filtering and FPS (about 120 FPS
Balanced/Quality, about 185–195 FPS Performance on this machine).

Generation data averages about 18 ms and a full 97×97 visual/Bullet subtree
build about 0.35 s on the development machine. Both happen only on an explicit
startup/regeneration event, never in the sustained head-pose update. Reusable
GLBs are cached by `AssetManager`; the active course loads only its selected
city props, not all 23 models. Repeatable screenshots:
`--look 0,-16 --shot out.png --shot-frames 60` (top: `--view-pos 0,0.85,-1.2
--look 0,-89`; side: `--view-pos 0.38,0.12,-0.75 --look 40,-35`; opposite:
`--view-pos=-0.38,0.12,-0.75 --look=-40,-35`).

Controls: **R** recentre · **D** debug overlay (lens readout included) ·
**F** fade toggle ([ ] width, - = strength) ·
**M** manipulate · **V** stage/object · **B** cycle object · **U** undo ·
**X** reset stage · **G** pinch · **H** hand tracking · **Esc/Q** quit.
