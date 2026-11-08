# Viture Luma Ultra AR PoC (Python + Panda3D)

Native optical AR for the **VITURE Luma Ultra** XR glasses: world-locked
wireframe geometry on the physical glasses display, anchored by the
onboard Carina 6DoF head pose. No virtual monitors, no desktop capture,
no video passthrough in the default path — one fullscreen window on
the glasses output, pure-black clear (invisible on the additive
combiner), only virtual geometry emits light.

See [AR_POC.md](AR_POC.md) for the architecture, setup, launch,
render modes, recentering, diagnostics, and known limitations.

## Layout

```
flake.nix            # dev environment (Python 3.12 + uv + system libs)
pyproject.toml       # uv package management (panda3d + pillow)
.python-version      # 3.12
src/
  ar_poc.py          # the PoC: window, regions/cameras, render loop
  viture_sdk.py      # ctypes bindings for libglasses.so (+ camera, display modes)
  providers.py       # pose providers: viture (threaded) / desktop / synthetic
  pose_math.py       # GL<->Panda basis change, quats, view matrices (tested)
  ar_scene.py        # calibration scene and marker-aligned table outline
  video_bg.py        # legacy world-locked video panel (opt-in via --video-panel)
tests/
  test_pose_math.py  # conversion unit tests (unittest, no window/hardware)
etc/
  70-viture.rules    # udev rules so the SDK can claim USB without root
AR_POC.md             # full PoC documentation
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

# one-time USB permissions, then replug the glasses:
sudo cp etc/70-viture.rules /etc/udev/rules.d/70-viture.rules
sudo udevadm control --reload-rules && sudo udevadm trigger
```

> Immutable rootfs (this machine): `/etc` is read-only, so install the
> rule per session instead — as root:
> `chmod 666 /dev/bus/usb/<bus>/<dev>` for the `35ca:1104` glasses and
> `0c45:636b` camera nodes (devnums change on re-enumeration; the
> self-test reports `USB_UNAVAILABLE` / `-2` without it).

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

Controls: **R** recentre · **D** debug overlay (lens readout included) ·
**F** fade toggle ([ ] width, - = strength) ·
**M** manipulate · **V** stage/object · **B** cycle object · **U** undo ·
**X** reset stage · **G** pinch · **H** hand tracking · **Esc/Q** quit.
Fullscreen auto-targets the VITURE output (override with
`--monitor NAME` or `--win-origin X,Y`; `--no-place` skips auto-move).
