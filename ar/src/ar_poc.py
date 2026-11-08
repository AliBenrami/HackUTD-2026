#!/usr/bin/env python3
"""Native optical AR PoC for VITURE Luma Ultra (Panda3D + Carina 6DoF).

World-locked tabletop golf on the glasses display, anchored by the
onboard 6DoF head pose and table marker. No virtual monitors, no desktop
capture, no video passthrough in the default path -- just virtual geometry on a
pure-black (optically transparent) fullscreen window.

Usage:
    uv run python src/ar_poc.py --help
    uv run python src/ar_poc.py --provider desktop --windowed   # no glasses
    uv run python src/ar_poc.py --self-test                    # hardware check
    uv run python src/ar_poc.py                                # glasses, auto mode
    uv run python src/ar_poc.py --render-mode stereo --request-sbs

Controls: R recenter - D debug overlay - Esc/Q quit.
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time

import viture_sdk
from viture_sdk import POSE_STABLE

import pose_math

DEFAULT_VFOV_Y_DEGREES = 29.0  # ~52 deg diagonal at 16:10 -> ~29 deg
# vertical. APPROXIMATE, not panel-calibrated: tune with --vfov if the
# overlay swims against the real world. See AR_POC.md (optics section).
NEAR_PLANE_METRES = 0.05
FAR_PLANE_METRES = 50.0
POSE_LOG_INTERVAL = 90
GLASSES_DISPLAY_TAG = "VITURE"
LOOK_AT_DISTANCE = 5.0  # metres ahead of the head for the look_at target
DEFAULT_IPD_METRES = 0.063
SBS_WIDTH_THRESHOLD = 3800  # window this wide (or wider) implies SBS output


def parse_args(argv=None) -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--provider", default="viture",
                   choices=("viture", "desktop", "synthetic"),
                   help="head-pose source (default %(default)s)")
    p.add_argument("--render-mode", default="auto",
                   choices=("mono", "stereo", "auto"),
                   help="mono, stereo side-by-side, or auto from window width")
    p.add_argument("--monitor", default=None, metavar="NAME",
                   help="substring matching the glasses output "
                        "(default: auto-detect VITURE)")
    p.add_argument("--win-origin", metavar="X,Y", default=None,
                   help="place the window at logical pixel origin X,Y "
                        "(overrides monitor detection)")
    p.add_argument("--no-place", action="store_true",
                   help="skip automatic move+fullscreen onto the glasses "
                        "output (leave window management to you)")
    p.add_argument("--windowed", action="store_true",
                   help="desktop-window preview instead of fullscreen")
    p.add_argument("--fov", type=float, default=None,
                   help="vertical field of view, degrees "
                        f"(default {DEFAULT_VFOV_Y_DEGREES}; approximate, "
                        "see AR_POC.md)")
    p.add_argument("--hfov", type=float, default=None,
                   help="anchor horizontal instead of vertical FOV, degrees "
                        "(overrides --fov for the horizontal axis)")
    p.add_argument("--near", type=float, default=NEAR_PLANE_METRES,
                   help="near clip distance, metres (default %(default)s)")
    p.add_argument("--far", type=float, default=FAR_PLANE_METRES,
                   help="far clip distance, metres (default %(default)s)")
    p.add_argument("--calibrate", action="store_true",
                   help="stereo calibration scene instead of the AR world "
                        "(borders, corners, crosshair, angular rings)")
    p.add_argument("--ipd", type=float, default=DEFAULT_IPD_METRES,
                   help="eye separation in metres for stereo "
                        f"(default %(default)s)")
    p.add_argument("--swap-eyes", action="store_true",
                   help="swap left/right eye assignment (diagnostic)")
    p.add_argument("--request-sbs", action="store_true",
                   help="ask the glasses (via SDK) for 3840x1200@90 SBS "
                        "display mode, then verify (opt-in, viture only)")
    p.add_argument("--3dof", dest="dof6", action="store_false",
                   help="orientation-only tracking (default 6DoF)")
    p.add_argument("--look", metavar="YAW,PITCH", default=None,
                   help="pin the desktop/synthetic view, degrees "
                        "(test hook; ignored with --provider viture)")
    p.add_argument("--video-panel", action="store_true",
                   help="legacy path: show the live camera feed on a "
                        "world-locked panel (default: pure optical, off)")
    p.add_argument("--manipulate", action="store_true",
                   help="enable the hand/keyboard manipulation layer "
                        "(stage + object moving; default off)")
    p.add_argument("--hands", default="sim", choices=("sim", "mediapipe"),
                   help="hand input source when manipulating "
                        "(default %(default)s; mediapipe needs the glasses "
                        "camera + --hand-model)")
    p.add_argument("--hand-model", default="models/hand_landmarker.task",
                   metavar="PATH",
                   help="MediaPipe hand-landmarker bundle "
                        "(default %(default)s)")
    p.add_argument("--manip-mode", default="stage", choices=("stage", "object"),
                   help="initial manipulation target (default %(default)s)")
    p.add_argument("--select-cone", type=float, default=4.0, metavar="DEG",
                   help="object selection cone half-angle, degrees")
    p.add_argument("--sensitivity", type=float, default=1.0, metavar="S",
                   help="drag movement multiplier")
    p.add_argument("--no-fade", action="store_true",
                   help="start with the optical edge fade disabled")
    p.add_argument("--fade-width", type=float, default=0.10, metavar="W",
                   help="fade band width as a fraction of half-view, 0-0.5 "
                        "(default %(default)s)")
    p.add_argument("--fade-strength", type=float, default=1.0, metavar="S",
                   help="fade strength 0-1 (default %(default)s)")
    p.add_argument("--debug", action="store_true",
                   help="start with the debug overlay visible (D toggles)")
    p.add_argument("--table", action="store_true",
                   help="marker-assisted tabletop AR: detect the ArUco "
                        "table target on the glasses camera, anchor virtual "
                        "objects to the physical table (implicit in golf/gallery)")
    p.add_argument("--scene", choices=("calibration", "golf-demo", "asset-gallery"),
                   default="golf-demo", help="visual scene (default %(default)s)")
    p.add_argument("--assets-dir", default=None, metavar="DIR",
                   help="downloaded asset archives (default ~/hackutd26_assets or HACKUTD_ASSETS_DIR)")
    p.add_argument("--table-w", type=float, default=0.60, metavar="M",
                   help="physical table width, metres (default %(default)s)")
    p.add_argument("--table-l", type=float, default=0.40, metavar="M",
                   help="physical table length, metres (default %(default)s)")
    p.add_argument("--marker-size-mm", type=float, default=100.0,
                   metavar="MM", help="table marker side length, "
                   "millimetres (default %(default)s)")
    p.add_argument("--table-dict", default="DICT_6X6_250", metavar="NAME",
                   help="ArUco dictionary (default %(default)s)")
    p.add_argument("--table-id", type=int, default=42, metavar="ID",
                   help="table marker id (default %(default)s)")
    p.add_argument("--table-calib", default="table_calib.json", metavar="PATH",
                   help="extrinsics/anchor save file (default %(default)s)")
    p.add_argument("--table-approx-hfov", type=float, default=70.0,
                   metavar="DEG", help="assumed camera HFOV when no "
                   "intrinsics calibrated (APPROX; default %(default)s)")
    p.add_argument("--shot", metavar="PATH", default=None,
                   help="save a screenshot of the 3D view to PATH")
    p.add_argument("--shot-frames", type=int, default=150, metavar="N",
                   help="rendered frames to wait before --shot (default %(default)s)")
    p.add_argument("--smoke-frames", type=int, default=0, metavar="N",
                   help="headless check: render N frames with the synthetic "
                        "pose and exit (no window, no glasses)")
    p.add_argument("--self-test", action="store_true",
                   help="hardware check against the real glasses; no window")
    p.add_argument("--list-displays", action="store_true",
                   help="list candidate display outputs and exit")
    return p.parse_args(argv)


def find_glasses_monitor(prefer: str | None = None):
    """Locate the glasses output via hyprctl. Returns dict or None."""
    import json
    import subprocess

    try:
        out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                             text=True, timeout=10)
        monitors = json.loads(out.stdout or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    if prefer:
        for m in monitors:
            blob = f"{m.get('name', '')} {m.get('description', '')}".lower()
            if prefer.lower() in blob:
                return m
        return None
    for m in monitors:
        blob = f"{m.get('name', '')} {m.get('description', '')}".lower()
        if GLASSES_DISPLAY_TAG.lower() in blob:
            return m
    return None


def list_displays() -> int:
    import subprocess

    print("--- Hyprland monitors ---")
    try:
        out = subprocess.run(["hyprctl", "monitors", "-j"], capture_output=True,
                             text=True, timeout=10)
        import json
        for m in json.loads(out.stdout or "[]"):
            print(f"{m.get('name')}: {m.get('width')}x{m.get('height')} "
                  f"at {m.get('x')},{m.get('y')} "
                  f"'{m.get('description', '')}'")
    except (OSError, subprocess.SubprocessError, ValueError):
        print("(hyprctl not available)")
    print("--- DRM outputs (sysfs) ---")
    base = "/sys/class/drm"
    try:
        for name in sorted(os.listdir(base)):
            if "-" not in name or name.startswith("render"):
                continue
            try:
                with open(os.path.join(base, name, "status")) as f:
                    status = f.read().strip()
                if status != "connected":
                    continue
                modes = open(os.path.join(base, name, "modes")).read().split()
                print(f"{name}: connected, modes e.g. {', '.join(modes[:4])}")
            except OSError:
                continue
    except OSError as exc:
        print(f"(cannot scan {base}: {exc})")
    auto = find_glasses_monitor()
    if auto is not None:
        print(f"(auto-detected glasses: {auto.get('name')} at "
              f"{auto.get('x')},{auto.get('y')})")
    else:
        print(f"(no {GLASSES_DISPLAY_TAG!r} monitor found; pass --monitor or "
              "--win-origin X,Y)")
    return 0


class VitureARApp:
    def __init__(self, args: argparse.Namespace) -> None:
        from direct.showbase.ShowBase import ShowBase
        from panda3d.core import PerspectiveLens, loadPrcFileData

        if args.smoke_frames > 0:
            loadPrcFileData("", "window-type none")
        else:
            loadPrcFileData("", "load-display pandagl")
            loadPrcFileData("", "audio-library-name null")
            loadPrcFileData("", "window-title Viture AR PoC")
            # Detect the glasses output BEFORE configuring the window so
            # fullscreen requests the panel's native size (requesting
            # 1920x1080 on the 1920x1200 panel risks letterbox/stretch).
            mon = None
            if not args.windowed:
                mon = find_glasses_monitor(args.monitor)
                if mon is not None:
                    print(f"[ar] targeting monitor {mon.get('name')} "
                          f"{mon.get('width')}x{mon.get('height')} "
                          f"at {mon.get('x', 0)},{mon.get('y', 0)}",
                          file=sys.stderr)
                else:
                    print("[ar] glasses monitor not detected; fullscreen "
                          "lands on the focused monitor (focus DP-1 first, "
                          "or pass --win-origin X,Y)", file=sys.stderr)
            if args.windowed:
                loadPrcFileData("", "win-size 960 540")
                loadPrcFileData("", "fullscreen false")
                loadPrcFileData("", "undecorated false")
            else:
                w = int(mon.get("width", 1920)) if mon else 1920
                h = int(mon.get("height", 1200)) if mon else 1200
                loadPrcFileData("", f"win-size {w} {h}")
                loadPrcFileData("", "fullscreen true")
                loadPrcFileData("", "undecorated true")
            origin = args.win_origin
            if origin is None and mon is not None:
                origin = f"{mon.get('x', 0)},{mon.get('y', 0)}"
            if origin:
                try:
                    x, y = origin.split(",")
                    loadPrcFileData("", f"win-origin {int(x)} {int(y)}")
                except ValueError:
                    raise SystemExit("--win-origin must look like X,Y")

        self.args = args
        self.base = ShowBase()
        self.base.disableMouse()
        self.base.setBackgroundColor(0, 0, 0, 1)  # black == transparent

        # Everything AR lives under gl_space, expressed in GL coordinates.
        self.gl_space = self.base.render.attachNewNode("gl-space")
        from panda3d.core import LMatrix4
        self.gl_space.set_mat(LMatrix4(1, 0, 0, 0,
                                      0, 0, 1, 0,
                                      0, -1, 0, 0,
                                      0, 0, 0, 1))

        import ar_scene
        # Stage root: moving it repositions the whole virtual world.
        # Calibration stays directly under gl_space (never manipulated).
        self.stage_root = self.gl_space.attachNewNode("stage")
        self.world = self.stage_root.attachNewNode("world")
        self.objects = {}
        if args.calibrate:
            win0 = self.base.win
            aspect0 = (win0.get_x_size() / max(1, win0.get_y_size())
                       if win0 is not None else 16.0 / 10.0)
            hfov0, vfov0 = self._lens_pair(aspect0)
            print(f"[ar] calibration rig: hfov={hfov0:.2f} vfov={vfov0:.2f} "
                  f"aspect={aspect0:.3f}", file=sys.stderr)
            ar_scene.build_calibration(self.world, hfov0, vfov0)
        elif args.scene == "calibration":
            self.obj_cube = ar_scene.build_wire_cube(self.world)  # A: green
            self.obj_octa = ar_scene.build_octahedron(self.world)  # B: blue
            self.obj_pyramid = ar_scene.build_pyramid(self.world)  # C: red
            self.objects = {"cube": self.obj_cube,
                            "octahedron": self.obj_octa,
                            "pyramid": self.obj_pyramid}
        self.world.hide()  # black frame until tracking locks

        import edge_fade
        self.fade = edge_fade.EdgeFadeEffect(
            self.base.render, width=args.fade_width,
            strength=args.fade_strength)
        if args.no_fade:
            self.fade.set_enabled(False)

        self.lens = PerspectiveLens()
        self.lens.set_near_far(args.near, args.far)
        if self.base.cam is not None:  # None under `window-type none`
            self.base.cam.node().setLens(self.lens)
            self.base.camera.setPos(self.gl_space, 0.0, 0.0, 0.0)
        self._last_size: tuple[int, int] | None = None
        # Stereo rig: populated by _setup_display_regions() when active.
        self.stereo = False
        self.eye_cams: list = []
        self.eye_lenses: list = []
        self._fit_lens(force=True)

        if self.base.win is not None:
            self._setup_display_regions()
        self._setup_stereo_indicators()

        self._setup_debug_overlay()
        self.base.accept("escape", self._quit)
        self.base.accept("q", self._quit)
        self.base.accept("r", self._recenter)
        self.base.accept("d", self._toggle_debug)
        self.base.accept("f", self._toggle_fade)
        self.base.accept("[", self._fade_narrower)
        self.base.accept("]", self._fade_wider)
        self.base.accept("-", self._fade_weaker)
        self.base.accept("=", self._fade_stronger)

        self.provider = self._make_provider(args)
        self.locked = False
        self.frames = 0
        self._shot_done = False
        self._placed = False
        self._place_attempts = 0

        if args.provider == "desktop":
            for key in ("arrow_up", "arrow_down", "arrow_left",
                        "arrow_right", "space", "c"):
                self.base.accept(key, self.provider.key_down, [key])
                self.base.accept(key + "-up", self.provider.key_up, [key])

        self._setup_manipulation(args)
        self._setup_table(args)

        if self.table is not None and args.scene != "calibration":
            self._setup_golf(args)

        self.base.taskMgr.add(self._update, "ar-update")

    def _setup_manipulation(self, args) -> None:
        import gestures
        import manipulate
        import pointer

        self.recognizer = gestures.GestureRecognizer()
        self.gesture_state = self.recognizer.state
        self.pointer = pointer.SpatialPointer(
            pointer.ApproxCamera(1920, 1080))
        self.manipulator = manipulate.SceneManipulator(
            self.stage_root, dict(self.objects), self.base.render,
            self.pointer, select_cone_deg=args.select_cone,
            sensitivity=args.sensitivity)
        if args.manip_mode == "object":
            self.manipulator.set_mode(manipulate.OBJECT)
        # Pointer indicator: small wireframe diamond at the aim point.
        import ar_scene as _sc
        self.pointer_dot = _sc.build_octahedron(
            self.base.render, center=(0, 2, 0), radius=0.02,
            color=(1.0, 1.0, 1.0, 1.0), name="ar-pointer")
        self.pointer_dot.hide()
        # Selection box: bright frame around the current target.
        self.select_box = _sc.build_wire_cube(
            self.stage_root, center=(0, 0, -1.5), half=0.22,
            color=(1.0, 1.0, 1.0, 1.0), name="ar-select")
        self.select_box.hide()
        self.hand_tracker = None
        self.hand_sim = None
        self.cam_stream = None
        self._last_hands: list = []
        self._sim_pinch_key = False

        self.base.accept("m", self._toggle_manipulate)
        self.base.accept("v", self._cycle_manip_target)
        self.base.accept("b", self._cycle_object)
        self.base.accept("u", self._manip_undo)
        self.base.accept("x", self._manip_reset_stage)
        self.base.accept("g", self._sim_pinch_on)
        self.base.accept("g-up", self._sim_pinch_off)
        self.base.accept("h", self._toggle_hand_tracker)
        self.base.accept("i", self._nudge, [0.0, 0.05, 0.0])
        self.base.accept("k", self._nudge, [0.0, -0.05, 0.0])
        self.base.accept("j", self._nudge, [-0.05, 0.0, 0.0])
        self.base.accept("l", self._nudge, [0.05, 0.0, 0.0])
        self.base.accept("o", self._nudge, [0.0, 0.0, -0.05])
        self.base.accept("p", self._nudge, [0.0, 0.0, 0.05])
        self.base.accept(",", self._yaw_selected, [-5.0])
        self.base.accept(".", self._yaw_selected, [5.0])
        self.base.accept("mouse1", self._sim_pinch_mouse, [True])
        self.base.accept("mouse1-up", self._sim_pinch_mouse, [False])
        if args.manipulate:
            self.manipulator.set_enabled(True)
            if hasattr(self.provider, "look_enabled"):
                self.provider.look_enabled = False
            print("[ar] manipulation ENABLED "
                  f"(mode={self.manipulator.mode}); M toggles, V switches "
                  "stage/object", file=sys.stderr)
        if args.hands == "sim" and self.base.win is not None:
            import hand_track

            self.hand_sim = hand_track.DesktopHandSimulator(self.base.win)

    # -- providers --------------------------------------------------------
    def _make_provider(self, args):
        import providers

        if args.smoke_frames > 0:
            return providers.SinePoseProvider()
        if args.provider == "viture":
            return providers.ViturePoseProvider(
                six_dof=args.dof6, request_sbs=args.request_sbs)
        if args.provider == "desktop":
            print("[ar] desktop simulator: mouse-look, arrows move, "
                  "Space/C up/down, R recentres", file=sys.stderr)
            provider = providers.DesktopPoseProvider(self.base.win)
            if args.look:
                try:
                    yaw_s, pitch_s = args.look.split(",")
                    provider.set_fixed(float(yaw_s), float(pitch_s))
                except ValueError:
                    raise SystemExit("--look must look like YAW,PITCH")
            return provider
        if args.provider == "synthetic":
            return providers.SinePoseProvider()
        raise SystemExit(f"unknown provider {args.provider!r}")

    # -- display regions / stereo ------------------------------------------
    def _want_stereo(self) -> bool:
        if self.args.render_mode == "stereo":
            return True
        if self.args.render_mode == "mono":
            return False
        win = self.base.win  # auto
        return win is not None and win.get_x_size() >= SBS_WIDTH_THRESHOLD

    def _setup_display_regions(self) -> None:
        from panda3d.core import BitMask32, Camera, PerspectiveLens

        win = self.base.win
        assert win is not None
        self.stereo = self._want_stereo()
        if not self.stereo:
            print(f"[ar] mono rendering "
                  f"({win.get_x_size()}x{win.get_y_size()})", file=sys.stderr)
            return
        print(f"[ar] stereo side-by-side "
              f"({win.get_x_size()}x{win.get_y_size()})", file=sys.stderr)
        win.remove_all_display_regions()
        halves = [(0.0, 0.5), (0.5, 1.0)]
        if self.args.swap_eyes:
            halves = [(0.5, 1.0), (0.0, 0.5)]
        for i, (x0, x1) in enumerate(halves):
            dr = win.make_mono_display_region(x0, x1, 0.0, 1.0)
            dr.set_clear_color_active(True)
            dr.set_clear_color((0, 0, 0, 1))
            dr.set_clear_depth_active(True)
            cam_node = Camera(f"eye-{i}")
            cam_np = self.base.camera.attach_new_node(cam_node)
            # Eye separation along head-right (camera-local +X).
            cam_np.set_pos((-1 if i == 0 else 1) * self.args.ipd / 2.0, 0, 0)
            lens = PerspectiveLens()
            lens.set_near_far(self.args.near, self.args.far)
            cam_node.set_lens(lens)
            cam_node.set_camera_mask(BitMask32.bit(i))
            dr.set_camera(cam_np)
            self.eye_cams.append(cam_np)
            self.eye_lenses.append(lens)
        # Lenses were created after the initial fit; force-apply now.
        self._last_size = None
        self._fit_lens(force=True)

    def _setup_stereo_indicators(self) -> None:
        """Per-eye L/R badges (masks hide each from the opposite eye)."""
        if not self.stereo:
            return
        from panda3d.core import BitMask32, TextNode

        for i, (tag, pos) in enumerate((("L", (0.18, 2.0, 0.38)),
                                       ("R", (-0.18, 2.0, 0.38)))):
            tn = TextNode(f"eye-{tag}")
            tn.set_text(tag)
            tn.set_text_color(0.3, 1.0, 0.3, 1.0)
            tn.set_align(TextNode.A_center)
            node = self.eye_cams[i].attach_new_node(tn)
            node.set_scale(0.09)
            node.set_pos(*pos)
            # Visible to its own eye only.
            node.hide(BitMask32.bit(1 - i))

    # -- debug overlay ------------------------------------------------------
    def _setup_debug_overlay(self) -> None:
        from direct.gui.OnscreenText import OnscreenText

        self._debug_lines = []
        self._debug_visible = bool(self.args.debug)
        for i in range(22):
            t = OnscreenText(text=" ", pos=(-1.28, 0.92 - i * 0.062),
                             scale=0.042, align=0, fg=(1, 1, 1, 1),
                             bg=(0, 0, 0, 0.45), mayChange=True)
            if not self._debug_visible:
                t.hide()
            self._debug_lines.append(t)

    def _toggle_debug(self) -> None:
        self._debug_visible = not self._debug_visible
        for t in self._debug_lines:
            t.show() if self._debug_visible else t.hide()

    # -- manipulation controls ----------------------------------------------
    def _toggle_manipulate(self) -> None:
        on = not self.manipulator.enabled
        self.manipulator.set_enabled(on)
        # Desktop sim: the mouse steers the head by default, which makes
        # pointing impossible (the view swings away from the pointer).
        # While manipulating, the mouse aims the hand only.
        if hasattr(self.provider, "look_enabled"):
            self.provider.look_enabled = not on
        print(f"[ar] manipulation {'ENABLED' if on else 'DISABLED'}",
              file=sys.stderr)
        if not on:
            self.pointer_dot.hide()
            self.select_box.hide()

    def _cycle_manip_target(self) -> None:
        import manipulate

        if self.manipulator.mode == manipulate.STAGE:
            self.manipulator.set_mode(manipulate.OBJECT)
            if self.manipulator.selected is None:
                self.manipulator.selected = "cube"
        else:
            self.manipulator.set_mode(manipulate.STAGE)
        print(f"[ar] manipulate target: {self.manipulator.mode} "
              f"({self.manipulator.selected or '-'})", file=sys.stderr)

    def _cycle_object(self) -> None:
        import manipulate

        if self.manipulator.mode != manipulate.OBJECT:
            self.manipulator.set_mode(manipulate.OBJECT)
        print(f"[ar] object: {self.manipulator.cycle_object()}",
              file=sys.stderr)

    def _manip_undo(self) -> None:
        print("[ar] undo: "
              f"{'restored' if self.manipulator.undo() else 'stack empty'}",
              file=sys.stderr)

    def _manip_reset_stage(self) -> None:
        self.manipulator.reset_stage()
        print("[ar] stage reset to origin", file=sys.stderr)

    def _sim_pinch_on(self) -> None:
        self._sim_pinch_key = True
        if self.hand_sim is not None:
            self.hand_sim.set_pinch_key(True)

    def _sim_pinch_off(self) -> None:
        self._sim_pinch_key = False
        if self.hand_sim is not None:
            self.hand_sim.set_pinch_key(False)

    def _sim_pinch_mouse(self, down: bool) -> None:
        if self.hand_sim is not None:
            self.hand_sim.set_pinch_mouse(down)

    def _toggle_hand_tracker(self) -> None:
        if self.hand_tracker is not None:
            self.hand_tracker.stop()
            self.hand_tracker = None
            print("[ar] hand tracking OFF (keyboard still works)",
                  file=sys.stderr)
        elif self.args.hands == "mediapipe":
            self._start_hand_tracker()

    def _start_hand_tracker(self) -> None:
        """Start the MediaPipe worker + glasses camera feed (opt-in)."""
        import os as _os

        import hand_track

        model = self.args.hand_model
        if not _os.path.isfile(model):
            print(f"[ar] hand model not found: {model}\n"
                  f"     download it:\n"
                  f"     mkdir -p models && curl -sL -o {model} \\\n"
                  f"       {hand_track.HandTracker.MODEL_URL}\n"
                  "     continuing keyboard-only (no hand input).",
                  file=sys.stderr)
            return
        try:
            lib = viture_sdk.load_lib()
            pid = viture_sdk.find_glasses_pid(lib)
            tbl = getattr(self, "table", None)
            if tbl is not None and tbl.get("cam") is not None:
                stream = tbl["cam"]  # shared with tabletop scanning
                print("[ar] sharing table camera stream", file=sys.stderr)
            else:
                stream = viture_sdk.CameraStream(lib)
                stream.start(pid)
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"[ar] camera unavailable ({exc}); hand tracking needs "
                  "the glasses camera. Continuing keyboard-only.",
                  file=sys.stderr)
            return
        try:
            tracker = hand_track.HandTracker(model)
            tracker.start()
        except Exception as exc:
            print(f"[ar] hand tracker failed ({exc}); continuing "
                  "keyboard-only.", file=sys.stderr)
            try:
                tbl = getattr(self, "table", None)
                if tbl is None or tbl.get("cam") is not stream:
                    stream.close()
            except Exception:
                pass
            return
        self.cam_stream = stream
        self.hand_tracker = tracker
        print("[ar] hand tracking on (MediaPipe, worker thread); "
              "show a hand to the glasses camera", file=sys.stderr)

    # -- tabletop AR (marker-assisted world anchor; opt-in via --table) -----
    def _setup_table(self, args) -> None:
        self.table = None
        if args.calibrate or (not args.table and args.scene == "calibration"):
            return
        import tabletop

        table_root = self.gl_space.attachNewNode("table-root")
        table_adjust = table_root.attachNewNode("table-adjust")
        table_stage = table_adjust.attachNewNode("table-stage")
        table_root.hide()

        import ar_scene

        debug_node = ar_scene.build_table_debug(
            table_root, args.table_w, args.table_l)
        # Objects rest ON the surface: centre z = half-extent (table-local,
        # x right, y up-in-plane, z normal).
        if args.scene == "calibration":
            ar_scene.build_solid_box(table_stage, center=(-0.15, 0.03, 0.05),
                                     size=(0.10, 0.10, 0.10), color=(.25, 1, .35, 1))
            ar_scene.build_solid_sphere(table_stage, center=(.12, .06, .04),
                                        radius=.04, color=(.35, .55, 1, 1))
            ar_scene.build_solid_cylinder(table_stage, center=(.02, -.10, .04),
                                          radius=.035, height=.08, color=(1, .6, .2, 1))
            ar_scene.build_arrow(table_stage, origin=(0, 0, .005),
                                 direction=(0, 0, 1), length=.15,
                                 color=(1, .9, .2, 1))

        from panda3d.core import AmbientLight, DirectionalLight

        amb = AmbientLight("table-amb")
        amb.set_color((0.5, 0.5, 0.5, 1.0))
        amb_np = table_stage.attach_new_node(amb)
        table_stage.set_light(amb_np)
        key = DirectionalLight("table-key")
        key.set_color((1.0, 1.0, 1.0, 1.0))
        key_np = table_stage.attach_new_node(key)
        # Light +Y aims at the surface (DirectionalLight shines along
        # its node's +Y); from up-left so boxes shade on two faces.
        key_np.set_pos(-0.4, -0.4, 1.0)
        key_np.look_at(0.0, 0.0, 0.0)
        table_stage.set_light(key_np)

        calib_path = args.table_calib
        saved = tabletop.load_calibration(calib_path)
        hand_eye = None
        he_saved = saved.get("hand_eye")
        if isinstance(he_saved, dict) and "pos" in he_saved \
                and "quat" in he_saved:
            try:
                hand_eye = (tuple(he_saved["pos"]), tuple(he_saved["quat"]))
                print(f"[table] loaded hand-eye from {calib_path} "
                      f"(resid {he_saved.get('diag', {}).get('rot_resid_deg_mean', float('nan')):.3f}deg)",
                      file=sys.stderr)
            except (TypeError, ValueError):
                hand_eye = None
        intr = saved.get("intrinsics") if isinstance(saved, dict) else None

        calibrator = tabletop.TableCalibrator(
            marker_size_m=args.marker_size_mm / 1000.0,
            table_w=args.table_w, table_l=args.table_l)
        tracker = tabletop.TableTracker(table_w=args.table_w,
                                        table_l=args.table_l)
        detector = tabletop.MarkerDetector(
            aruco_dict_name=args.table_dict, marker_id=args.table_id)
        try:
            detector.start()
        except Exception as exc:
            print(f"[table] detector failed ({exc}); table mode off",
                  file=sys.stderr)
            table_root.remove_node()
            return

        cam = None
        cam_owned = False
        if args.smoke_frames == 0 and args.provider == "viture":
            try:
                import viture_sdk

                lib = viture_sdk.load_lib()
                pid = viture_sdk.find_glasses_pid(lib)
                cam = viture_sdk.CameraStream(lib)
                cam.start(pid)
                cam_owned = True
            except Exception as exc:
                print(f"[table] camera unavailable ({exc}); scanning off "
                      "(anchor restore + saved extrinsics still work)",
                      file=sys.stderr)
                cam = None

        self.table = {
            "root": table_root, "adjust": table_adjust,
            "stage": table_stage, "debug": debug_node,
            "calibrator": calibrator, "tracker": tracker,
            "detector": detector, "timesync": tabletop.TimeSync(),
            "history": tabletop.PoseHistory(),
            "hand_eye": hand_eye,
            "cam": cam, "cam_owned": cam_owned,
            "scanning": cam is not None, "viz": True, "frozen": False,
            "calib_path": calib_path, "intrinsics": intr,
            "approx_hfov": args.table_approx_hfov,
            "adjust": {"yaw_deg": 0.0, "x": 0.0, "z": 0.0, "stage_z": 0.0},
            "stats": {"det": 0, "acc": 0, "rej": {}, "amb": 0,
                      "last_err": float("nan"), "stale": 0},
        }
        if args.provider == "desktop":
            # Desktop-only untracked preview; never presented as a physical lock.
            table_root.set_pos(0, -0.30, -1.2)
            table_root.set_p(-90)
            table_root.show()
            print("[table] desktop preview (NOT tracked)", file=sys.stderr)
        self._apply_table_adjust()
        self.base.accept("y", self._table_toggle_scan)
        self.base.accept("n", self._table_toggle_viz)
        self.base.accept("z", self._table_toggle_freeze)
        self.base.accept("s", self._table_save)
        self.base.accept("0", self._table_restore)
        self.base.accept("1", self._table_bump_stage_z, [0.01])
        self.base.accept("2", self._table_bump_stage_z, [-0.01])
        self.base.accept("3", self._table_bump_yaw, [2.0])
        self.base.accept("4", self._table_bump_yaw, [-2.0])
        self.base.accept("5", self._table_bump_x, [0.01])
        self.base.accept("6", self._table_bump_x, [-0.01])
        self.base.accept("7", self._table_bump_z, [0.01])
        self.base.accept("8", self._table_bump_z, [-0.01])
        self.base.accept("9", self._table_clear_adjust)
        # NOTE: "c" also drives the desktop simulator down-move; in table
        # mode with --provider desktop, hand-eye solve wins. Use viture.
        self.base.accept("c", self._table_solve_handeye)
        print("[table] on: Y scan N viz Z freeze S save 0 restore "
              "1/2 lift 3/4 yaw 5/6 x 7/8 z 9 clear C hand-eye",
              file=sys.stderr)

    def _setup_golf(self, args) -> None:
        from golf_assets import AssetManager
        import golf_scene

        self.golf_assets = AssetManager(self.base.loader, args.assets_dir)
        self.golf_stage = self.table["stage"].attach_new_node("golf-stage-root")
        self.golf_offset = [0.0, 0.0, 0.0, 0.0, 1.0]  # x,y,z,yaw,scale
        if args.scene == "golf-demo":
            self.golf_course, self.golf_objects = golf_scene.build_course(
                self.golf_stage, self.golf_assets, args.table_w, args.table_l)
            print(f"[golf] loaded {len(self.golf_objects)} course objects", file=sys.stderr)
        else:
            self.gallery = golf_scene.Gallery(self.golf_stage, self.golf_assets, self.base)
            self.base.accept("tab", self.gallery.cycle, [1])
            self.base.accept("shift-tab", self.gallery.cycle, [-1])
            self.base.accept(";", self.gallery.rotate, [-15])
            self.base.accept("'", self.gallery.rotate, [15])
            self.base.accept("b", self.gallery.toggle_debug)
        for key, delta in (("shift-j", (-.01, 0, 0, 0, 0)),
                           ("shift-l", (.01, 0, 0, 0, 0)),
                           ("shift-i", (0, .01, 0, 0, 0)),
                           ("shift-k", (0, -.01, 0, 0, 0)),
                           ("shift-u", (0, 0, .01, 0, 0)),
                           ("shift-o", (0, 0, -.01, 0, 0)),
                           ("shift-,", (0, 0, 0, -5, 0)),
                           ("shift-.", (0, 0, 0, 5, 0)),
                           ("shift-[", (0, 0, 0, 0, -.05)),
                           ("shift-]", (0, 0, 0, 0, .05))):
            self.base.accept(key, self._move_golf_stage, [delta])
        self.base.accept("shift-9", self._reset_golf_stage)

    def _move_golf_stage(self, delta) -> None:
        self.golf_offset = [a + b for a, b in zip(self.golf_offset, delta)]
        self.golf_offset[4] = max(.3, min(1.5, self.golf_offset[4]))
        x, y, z, yaw, scale = self.golf_offset
        self.golf_stage.set_pos(x, y, z)
        self.golf_stage.set_h(yaw)
        self.golf_stage.set_scale(scale)
        print(f"[golf] stage x={x:.2f} y={y:.2f} height={z:.2f} "
              f"yaw={yaw:.0f} scale={scale:.2f}", file=sys.stderr)

    def _reset_golf_stage(self) -> None:
        self.golf_offset = [0, 0, 0, 0, 1]
        self.golf_stage.set_pos(0, 0, 0)
        self.golf_stage.set_h(0)
        self.golf_stage.set_scale(1)

    def _apply_table_adjust(self) -> None:
        t = self.table
        if t is None:
            return
        a = t["adjust"]
        adj_node = t["root"].find("**/table-adjust")
        adj_node.set_pos(float(a["x"]), 0.0, float(a["z"]))
        adj_node.set_h(float(a["yaw_deg"]))
        t["stage"].set_pos(0.0, 0.0, float(a["stage_z"]))

    def _table_toggle_scan(self) -> None:
        t = self.table
        if t is None:
            return
        if t["cam"] is None:
            print("[table] no camera; scanning unavailable", file=sys.stderr)
            return
        t["scanning"] = not t["scanning"]
        print(f"[table] scanning {'on' if t['scanning'] else 'off'}",
              file=sys.stderr)

    def _table_toggle_viz(self) -> None:
        t = self.table
        if t is None:
            return
        t["viz"] = not t["viz"]
        if t["viz"]:
            t["debug"].show()
        else:
            t["debug"].hide()

    def _table_toggle_freeze(self) -> None:
        t = self.table
        if t is None:
            return
        t["frozen"] = not t["frozen"]
        print(f"[table] anchor {'frozen' if t['frozen'] else 'live'}",
              file=sys.stderr)

    def _table_bump_stage_z(self, dz: float) -> None:
        if self.table is None:
            return
        self.table["adjust"]["stage_z"] = round(
            self.table["adjust"]["stage_z"] + dz, 3)
        self._apply_table_adjust()

    def _table_bump_yaw(self, dd: float) -> None:
        if self.table is None:
            return
        self.table["adjust"]["yaw_deg"] = round(
            self.table["adjust"]["yaw_deg"] + dd, 2)
        self._apply_table_adjust()

    def _table_bump_x(self, dx: float) -> None:
        if self.table is None:
            return
        self.table["adjust"]["x"] = round(self.table["adjust"]["x"] + dx, 3)
        self._apply_table_adjust()

    def _table_bump_z(self, dz: float) -> None:
        if self.table is None:
            return
        self.table["adjust"]["z"] = round(self.table["adjust"]["z"] + dz, 3)
        self._apply_table_adjust()

    def _table_clear_adjust(self) -> None:
        if self.table is None:
            return
        self.table["adjust"] = {"yaw_deg": 0.0, "x": 0.0, "z": 0.0,
                                "stage_z": 0.0}
        self._apply_table_adjust()
        print("[table] manual adjust cleared", file=sys.stderr)

    def _table_hand_eye(self):
        """Active T_H_C: calibrated if present, else approx flip + note."""
        import tabletop

        t = self.table
        if t["hand_eye"] is not None:
            return t["hand_eye"], False
        # Approximate: camera head-aligned (GL<->OpenCV axis flip F),
        # zero offset. EXPLICITLY approximate: usable for tabletop-scale
        # demos, never for measurement.
        q = tabletop.quat_from_mat3(tabletop.F_CV2GL)
        return ((0.0, 0.0, 0.0), q), True

    def _table_solve_handeye(self) -> None:
        t = self.table
        if t is None:
            return
        cal = t["calibrator"]
        if cal.handeye_count < 4:
            print(f"[table] need >= 4 hand-eye pairs "
                  f"(have {cal.handeye_count}); move the head, keep the "
                  "marker visible, press C again", file=sys.stderr)
            return
        try:
            (pos, quat), diag = cal.solve_hand_eye()
        except ValueError as exc:
            print(f"[table] hand-eye solve failed: {exc}", file=sys.stderr)
            return
        t["hand_eye"] = (pos, quat)
        print(f"[table] hand-eye solved: {diag['motions']} motions, "
              f"rot resid {diag['rot_resid_deg_mean']:.3f}deg, "
              f"trans resid {diag['trans_resid_m_mean'] * 1000:.1f}mm; "
              "press S to save", file=sys.stderr)

    def _table_save(self) -> None:
        import tabletop

        t = self.table
        if t is None:
            return
        anchor = t["tracker"].anchor
        payload = {
            "table": {"width_m": anchor.width_m,
                      "length_m": anchor.length_m},
            "marker": {"dict": self.args.table_dict, "id": self.args.table_id,
                       "size_m": self.args.marker_size_mm / 1000.0},
            "intrinsics": t["intrinsics"],
            "hand_eye": None,
            "anchor": anchor.as_dict()
            if t["tracker"].state != "UNINITIALIZED" else None,
            "adjust": dict(t["adjust"]),
        }
        if t["hand_eye"] is not None:
            payload["hand_eye"] = {
                "pos": list(t["hand_eye"][0]),
                "quat": list(t["hand_eye"][1]),
                "diag": dict(t["calibrator"].hand_eye_diag),
            }
        try:
            tabletop.save_calibration(t["calib_path"], payload)
            print(f"[table] saved {t['calib_path']}", file=sys.stderr)
        except OSError as exc:
            print(f"[table] save failed: {exc}", file=sys.stderr)

    def _table_restore(self) -> None:
        import tabletop

        t = self.table
        if t is None:
            return
        saved = tabletop.load_calibration(t["calib_path"])
        d = saved.get("anchor") if isinstance(saved, dict) else None
        if not isinstance(d, dict):
            print(f"[table] no anchor in {t['calib_path']} (press S first)",
                  file=sys.stderr)
            return
        try:
            anchor = tabletop.TableAnchor.from_dict(d)
        except (KeyError, TypeError, ValueError) as exc:
            print(f"[table] bad anchor in file: {exc}", file=sys.stderr)
            return
        # Restored anchors are trusted for position but the VIO world frame
        # may have moved: adopt frozen (DEGRADED) until the marker agrees.
        tr = t["tracker"]
        tr.anchor = anchor
        tr.state = "DEGRADED"
        tr.anchor.tracking_state = "DEGRADED"
        print(f"[table] anchor restored (DEGRADED, conf={anchor.confidence:.2f}); "
              "show the marker to snap in", file=sys.stderr)

    def _table_intrinsics_for(self, w: int, h: int):
        """(K, dist, approx): saved calibration scaled, else approx HFOV."""
        import tabletop

        intr = self.table["intrinsics"]
        if isinstance(intr, dict) and "K" in intr:
            try:
                import numpy as np

                K = np.array(intr["K"], dtype=float).reshape(3, 3)
                dist = np.array(intr.get("dist", [0] * 5),
                                dtype=float).reshape(-1)
                sw, sh = intr.get("width"), intr.get("height")
                if sw and sh and (sw != w or sh != h):
                    K = K.copy()
                    K[0, :] *= w / sw
                    K[1, :] *= h / sh
                return K, dist, bool(intr.get("approx", False))
            except (TypeError, ValueError):
                pass
        approx = tabletop.approx_intrinsics(w, h, self.table["approx_hfov"])
        import numpy as np

        return (np.array(approx["K"], dtype=float),
                np.array(approx["dist"], dtype=float), True)

    def _update_table(self, snap) -> None:
        import time as _time

        import tabletop

        t = self.table
        if t is None:
            return
        now = _time.monotonic()
        t["history"].push(snap.stamp, snap.pos, snap.quat, snap.stable)
        t["tracker"].note_head_pose(snap.pos, snap.quat, snap.stable, now)
        t["tracker"].mark_seen(now, snap.stable)

        # Latest camera frame (non-destructive: shared with hand track).
        cam = t["cam"]
        if t["scanning"] and not t["frozen"] and cam is not None:
            try:
                fr = cam.peek_frame()
            except Exception:
                fr = None
            if fr is not None:
                _jpeg, w, h, seq, ts_ns, arrival = fr
                t["timesync"].feed(ts_ns, arrival)
                try:
                    t["detector"].submit(_jpeg, w, h, seq, ts_ns, arrival)
                except Exception:
                    pass
        det = None
        try:
            det = t["detector"].take()
        except Exception:
            det = None
        if det is not None:
            try:
                self._table_on_detection(det, snap, now)
            except Exception:
                # One bad frame must never kill table mode; count it and
                # keep going (traceback pinpoints the culprit in the log).
                import traceback

                t["stats"]["exc"] = t["stats"].get("exc", 0) + 1
                if t["stats"]["exc"] <= 3:
                    traceback.print_exc()

        # Publish the anchor to the scene.
        tr = t["tracker"]
        if tr.has_anchor:
            from panda3d.core import LQuaternionf

            t["root"].set_pos(*tr.anchor.pos)
            w, x, y, z = tr.anchor.quat
            t["root"].set_quat(LQuaternionf(w, x, y, z))
            if t["root"].is_hidden():
                t["root"].show()
        elif self.args.provider != "desktop" and t["root"] and not t["root"].is_hidden():
            t["root"].hide()

    def _table_on_detection(self, det, snap, now) -> None:
        import numpy as np

        import tabletop

        t = self.table
        st = t["stats"]
        st["det"] += 1
        # Stale worker output (e.g. after a hitch): skip, count it.
        if now - det["arrival_mono"] > 0.5:
            st["stale"] += 1
            return
        t_img = t["timesync"].to_mono(det["ts_ns"], det["arrival_mono"])
        interp = t["history"].interpolate(t_img)
        if interp is None:
            return
        head_pos, head_quat, stable, _extrap = interp
        K, dist, is_approx = self._table_intrinsics_for(det["img_w"],
                                                        det["img_h"])
        sols = tabletop.estimate_marker_pose(
            det["corners"], self.args.marker_size_mm / 1000.0, K, dist)
        if not sols:
            return
        best = sols[0]
        # Planar ambiguity: two near-equal fits mean the tilt direction is
        # unknowable this frame -- skip rather than flip the table.
        if len(sols) > 1 and sols[1]["reproj_err"] < 2.0 \
                and best["reproj_err"] > 0.5 * sols[1]["reproj_err"]:
            st["amb"] += 1
            return
        he, approx = self._table_hand_eye()
        approx = approx or is_approx
        cal = t["calibrator"]
        status, _anchor = cal.observe(head_pos, head_quat, best["rvec"],
                                      best["tvec"], best["reproj_err"],
                                      t_img, he, approx_ok=not approx)
        if status == "accepted":
            st["acc"] += 1
        else:
            st["rej"][status] = st["rej"].get(status, 0) + 1
        st["last_err"] = float(best["reproj_err"])
        try:
            if cal.collect_handeye(head_pos, head_quat, best["rvec"],
                                   best["tvec"]):
                pass
        except Exception:
            pass
        est = cal.best_estimate()
        if est is not None:
            t["tracker"].observe_marker(est["pos"], est["quat"],
                                        est["reproj"], est["stamp"],
                                        stable, approx)

    def _table_debug_lines(self) -> list:
        t = self.table
        if t is None:
            return []
        import math as _math

        tr = t["tracker"]
        cal = t["calibrator"]
        a = tr.anchor
        st = t["stats"]
        he = "calibrated" if t["hand_eye"] is not None else "APPROX flip"
        rej = (" " + " ".join(f"{k}:{v}" for k, v in st["rej"].items())) \
            if st["rej"] else ""
        adj = t["adjust"]
        return [
            f"table: {tr.state} conf:{a.confidence:.2f} "
            f"obs:{a.obs_count} err:{a.reproj_err_px:.2f}px{rej}",
            f"table: det:{st['det']} acc:{st['acc']} amb:{st['amb']} "
            f"stale:{st['stale']} last:{st['last_err']:.2f}px "
            f"he:{he} pairs:{cal.handeye_count}",
            f"table: {'SCAN' if t['scanning'] else 'scan-off'} "
            f"{'FROZEN' if t['frozen'] else 'live'} "
            f"corr:{tr.last_correction_m * 1000:.1f}mm/"
            f"{tr.last_correction_deg:.2f}deg "
            f"adj:y{adj['yaw_deg']:.0f} x{adj['x'] * 1000:.0f} "
            f"z{adj['z'] * 1000:.0f} lift{adj['stage_z'] * 1000:.0f}",
            "Y scan N viz Z freeze S save 0 restore 1-8 adjust 9 clr C cal",
        ]

    def _nudge(self, dx: float, dy: float, dz: float) -> None:
        if self.manipulator.enabled:
            self.manipulator.nudge_selected(dx, dy, dz)

    def _yaw_selected(self, degrees: float) -> None:
        if self.manipulator.enabled:
            self.manipulator.yaw_selected(degrees)

    def _toggle_fade(self) -> None:
        on = self.fade.toggle()
        print(f"[ar] edge fade {'on' if on else 'off'} "
              f"(w={self.fade.width:.2f} s={self.fade.strength:.2f})",
              file=sys.stderr)

    def _fade_narrower(self) -> None:
        print(f"[ar] fade width {self.fade.set_width(self.fade.width - 0.02):.2f}",
              file=sys.stderr)

    def _fade_wider(self) -> None:
        print(f"[ar] fade width {self.fade.set_width(self.fade.width + 0.02):.2f}",
              file=sys.stderr)

    def _fade_weaker(self) -> None:
        print(f"[ar] fade strength "
              f"{self.fade.set_strength(self.fade.strength - 0.1):.1f}",
              file=sys.stderr)

    def _fade_stronger(self) -> None:
        print(f"[ar] fade strength "
              f"{self.fade.set_strength(self.fade.strength + 0.1):.1f}",
              file=sys.stderr)

    # -- Panda3D plumbing ---------------------------------------------------
    def _place_on_glasses(self) -> bool:
        """Move this window onto the glasses output and fullscreen it.

        Panda's own fullscreen request is issued through X11 VidMode,
        which does not exist under XWayland, so Hyprland tiles the
        window instead. Placing it via the compositor (runtime window
        management only -- no config is changed) is what actually gets
        us exclusive fullscreen on DP-1.
        """
        import json
        import subprocess

        if self.args.windowed or self.args.no_place:
            return False
        try:
            clients = json.loads(subprocess.run(
                ["hyprctl", "clients", "-j"], capture_output=True,
                text=True, timeout=10).stdout or "[]")
        except (OSError, subprocess.SubprocessError, ValueError):
            print("[ar] hyprctl unavailable; skipping auto-placement",
                  file=sys.stderr)
            return False
        addr = None
        for c in clients:
            if (c.get("pid") == os.getpid()
                    and "Viture AR PoC" in c.get("title", "")):
                addr = c.get("address")
                break
        if not addr:
            print("[ar] own window not found; skipping auto-placement",
                  file=sys.stderr)
            return False
        try:
            monitors = json.loads(subprocess.run(
                ["hyprctl", "monitors", "-j"], capture_output=True,
                text=True, timeout=10).stdout or "[]")
        except (OSError, subprocess.SubprocessError, ValueError):
            monitors = []
        blob = (self.args.monitor or GLASSES_DISPLAY_TAG).lower()
        ws = None
        for m in monitors:
            if blob in f"{m.get('name', '')} {m.get('description', '')}".lower():
                ws = (m.get("activeWorkspace") or {}).get("id")
                break
        if ws is None:
            print("[ar] glasses workspace not found; skipping auto-placement "
                  "(focus DP-1 or pass --win-origin)", file=sys.stderr)
            return False
        cmds = (f"dispatch focuswindow address:{addr}; "
                f"dispatch movetoworkspace {ws}; dispatch fullscreen 0")
        rc = subprocess.run(["hyprctl", "--batch", cmds],
                            capture_output=True, text=True,
                            timeout=10).returncode
        if rc != 0:
            print("[ar] hyprctl placement failed; window stays tiled",
                  file=sys.stderr)
            return False
        print(f"[ar] placed on glasses workspace {ws}, fullscreen requested",
              file=sys.stderr)
        return True
    def _lens_pair(self, aspect: float) -> tuple[float, float]:
        """(hfov, vfov) degrees for a viewport aspect, from CLI config.

        Vertical FOV is the anchor (provisional panel value unless
        overridden); horizontal derives from the aspect. --hfov anchors
        horizontal instead; explicit --hfov + --fov pairs are used
        verbatim (a mismatch warning fires if they fight the window).
        """
        args = self.args
        vfov = args.fov if args.fov is not None else DEFAULT_VFOV_Y_DEGREES
        if args.hfov is not None and args.fov is not None:
            implied = (math.tan(math.radians(args.hfov) / 2.0)
                       / math.tan(math.radians(args.fov) / 2.0))
            if abs(implied - aspect) / aspect > 0.02:
                print(f"[ar] WARNING: explicit hfov/vfov imply aspect "
                      f"{implied:.3f} but the window is {aspect:.3f}; "
                      f"the image will stretch", file=sys.stderr)
            return args.hfov, args.fov
        if args.hfov is not None:
            vfov = math.degrees(2.0 * math.atan(
                math.tan(math.radians(args.hfov) / 2.0) / aspect))
            return args.hfov, vfov
        hfov = math.degrees(2.0 * math.atan(
            math.tan(math.radians(vfov) / 2.0) * aspect))
        return hfov, vfov

    def _fit_lens(self, force: bool = False) -> None:
        win = self.base.win
        if win is None:  # headless smoke run
            self.lens.set_fov(60.0, DEFAULT_VFOV_Y_DEGREES)
            return
        size = (win.get_x_size(), win.get_y_size())
        if not force and size == self._last_size:
            return
        self._last_size = size
        aspect = size[0] / max(1, size[1])
        hfov, vfov = self._lens_pair(aspect)
        self.lens.set_fov(hfov, vfov)
        if self.stereo:
            eye_aspect = aspect / 2.0
            eye_hfov, eye_vfov = self._lens_pair(eye_aspect)
            for lens in self.eye_lenses:
                lens.set_fov(eye_hfov, eye_vfov)

    def _quit(self) -> None:
        self._shutdown()
        self.base.userExit()

    def _recenter(self) -> None:
        old = None
        try:
            old = self.provider.snapshot()
        except Exception:
            old = None
        try:
            self.provider.recenter()
            print("[ar] recentred", file=sys.stderr)
        except RuntimeError as exc:
            print(f"[ar] recenter failed: {exc}", file=sys.stderr)
            return
        if self.table is not None and old is not None:
            try:
                self.table["tracker"].note_origin_reset(old.pos, old.quat)
            except Exception as exc:
                print(f"[table] origin-reset carry failed ({exc})",
                      file=sys.stderr)

    def _shutdown(self) -> None:
        if getattr(self, "table", None) is not None:
            try:
                self.table["detector"].stop()
            except Exception:
                pass
            if self.table.get("cam_owned") and self.table.get("cam") is not None:
                try:
                    self.table["cam"].close()
                except Exception:
                    pass
                self.table["cam"] = None
            self.table = None
        if self.hand_tracker is not None:
            try:
                self.hand_tracker.stop()
            except Exception:
                pass
            self.hand_tracker = None
        if self.cam_stream is not None:
            try:
                self.cam_stream.close()
            except Exception:
                pass
            self.cam_stream = None
        if self.provider is not None:
            self.provider.stop()
            self.provider = None
        print(f"[ar] rendered {self.frames} frames", file=sys.stderr)

    # -- hand tracking + manipulation (opt-in; never blocks) -----------
    def _synthetic_pinch(self, now: float):
        """Keyboard fallback pinch at screen centre (no camera needed)."""
        import hand_track

        lands = [(0.5, 0.5, 0.0)] * hand_track.HAND_LANDMARK_COUNT
        return hand_track.HandState(
            (tuple(lands), "Right", 1.0, True, (0.5, 0.5), now))

    def _update_hands(self, pos, quat) -> None:
        man = self.manipulator
        if man is None:
            return
        now = time.monotonic()
        if self.hand_tracker is not None and self.cam_stream is not None:
            try:
                fr = self.cam_stream.take_frame()
            except Exception:
                fr = None
            if fr is not None:
                jpeg, w, h, _seq = fr
                try:
                    self.hand_tracker.submit_frame(jpeg, w, h, now)
                except Exception:
                    pass
        hands: list = []
        if self.hand_tracker is not None:
            try:
                hands = self.hand_tracker.get_hands()
            except Exception:
                hands = []
        elif self.hand_sim is not None and self.base.win is not None:
            hands = self.hand_sim.get_hands()
        self._last_hands = hands
        hand = hands[0] if hands else None
        if hand is None and self._sim_pinch_key and man.enabled:
            hand = self._synthetic_pinch(now)
        st = self.recognizer.update(hand, now)
        self.gesture_state = st
        man.update(st, pos, quat)
        self._update_manip_visuals(st)

    def _update_manip_visuals(self, st) -> None:
        man = self.manipulator
        show_pointer = (man.enabled and man.last_ray is not None
                        and st.state in ("hover", "pinch", "drag"))
        if show_pointer:
            (ox, oy, oz), (dx, dy, dz) = man.last_ray
            self.pointer_dot.set_pos(self.base.render,
                                     ox + dx * 2.0, oy + dy * 2.0,
                                     oz + dz * 2.0)
            self.pointer_dot.show()
        else:
            self.pointer_dot.hide()
        target = man.grabbed or man.hover_target
        if (man.enabled and target is not None and target != "stage"
                and target in self.objects):
            node = self.objects[target]
            self.select_box.set_pos(
                self.stage_root, *node.get_pos(self.stage_root))
            self.select_box.show()
        else:
            self.select_box.hide()

    # -- per-frame ----------------------------------------------------------
    def _update(self, task) -> int:
        from direct.task import Task

        import pose_math

        dt = self.base.clock.getDt()
        self._fit_lens()

        # Compositor placement (runtime only, retried a few times).
        if (not self._placed and self.frames > 0 and self.frames % 300 == 0
                and self._place_attempts < 4):
            self._place_attempts += 1
            self._placed = self._place_on_glasses()
        if hasattr(self.provider, "update"):
            self.provider.update(dt)

        snap = self.provider.snapshot() if self.provider else None
        if snap is None:
            return Task.cont  # no pose yet; hold the black frame
        pos, quat, status = snap.pos, snap.quat, snap.status
        if not self.locked:
            if not snap.stable:
                return Task.cont  # wait for VIO convergence
            try:
                self.provider.recenter()
            except RuntimeError as exc:
                print(f"[ar] recenter failed: {exc}", file=sys.stderr)
                return Task.cont
            self.locked = True
            self.world.show()
            print("[ar] tracking locked; scene anchored", file=sys.stderr)

        # Camera: positioned at the head (converted to Panda world),
        # aimed along head-forward via look_at. look_at is Panda's own
        # orientation routine, so lens/node conventions stay consistent
        # by construction; the world geometry lives under gl_space.
        # Roll defaults to gravity-level (look_at up = world +Z).
        if self.base.camera is not None:
            fwd = pose_math.quat_rotate(quat, (0.0, 0.0, -1.0))
            fp = pose_math.mat3_vec(pose_math.M_GL2PANDA, fwd)
            pp = pose_math.gl_to_panda_pos(pos)
            self.base.camera.set_pos(*pp)
            self.base.camera.look_at(pp[0] + fp[0] * LOOK_AT_DISTANCE,
                                     pp[1] + fp[1] * LOOK_AT_DISTANCE,
                                     pp[2] + fp[2] * LOOK_AT_DISTANCE)
            self.fade.follow(self.base.camera, self.base.render)

        # Hand tracking + manipulation (opt-in layer; never blocks).
        self._update_hands(pos, quat)

        # Tabletop anchor (opt-in via --table; no-op otherwise).
        if self.table is not None:
            try:
                self._update_table(snap)
            except Exception:
                import traceback

                self._table_failures = getattr(self, "_table_failures", 0) + 1
                if self._table_failures <= 3:
                    traceback.print_exc()
                if self._table_failures < 10:
                    print(f"[table] update failed "
                          f"({self._table_failures}x, keeping table mode)",
                          file=sys.stderr)
                else:
                    print("[table] update failed 10x; disabling table mode",
                          file=sys.stderr)
                    try:
                        self.table["detector"].stop()
                    except Exception:
                        pass
                    if self.table.get("cam_owned"):
                        try:
                            self.table["cam"].close()
                        except Exception:
                            pass
                    self.table = None

        self.frames += 1
        if self.args.shot and not self._shot_done \
                and self.frames >= self.args.shot_frames \
                and self.base.win is not None:
            if self.base.win.save_screenshot(self.args.shot):
                print(f"[ar] screenshot saved to {self.args.shot}",
                      file=sys.stderr)
            else:
                print(f"[ar] screenshot FAILED for {self.args.shot}",
                      file=sys.stderr)
            self._shot_done = True
        if self.args.smoke_frames and self.frames >= self.args.smoke_frames:
            print(f"[ar] smoke run complete ({self.frames} frames)",
                  file=sys.stderr)
            self._shutdown()
            self.base.userExit()
            return Task.done
        if self.frames % POSE_LOG_INTERVAL == 0:
            qw, qx, qy, qz = quat
            tag = "stable  " if status == POSE_STABLE else "unstable"
            print(f"[pose] {tag} pos [{pos[0]: .3f} {pos[1]: .3f} {pos[2]: .3f}] "
                  f"quat [{qw:.3f} {qx:.3f} {qy:.3f} {qz:.3f}] "
                  f"frames={self.frames}", file=sys.stderr)
            if self.table is not None:
                tr = self.table["tracker"]
                st = self.table["stats"]
                rej = ("/".join(f"{k}:{v}" for k, v in st["rej"].items())
                       or "-")
                print(f"[table] {tr.state} conf={tr.anchor.confidence:.2f} "
                      f"det={st['det']} acc={st['acc']} amb={st['amb']} "
                      f"stale={st.get('stale', 0)} exc={st.get('exc', 0)} "
                      f"rej={rej} last={st['last_err']:.2f}px "
                      f"scan={'on' if self.table['scanning'] else 'off'}",
                      file=sys.stderr)
        if self.frames % 10 == 0:
            self._refresh_debug(snap)
        return Task.cont

    def _refresh_debug(self, snap) -> None:
        if not self._debug_visible:
            return
        win = self.base.win
        w = win.get_x_size() if win else 0
        h = win.get_y_size() if win else 0
        fps = self.base.clock.get_average_frame_rate()
        pos, quat = snap.pos, snap.quat
        reads = misses = 0
        if hasattr(self.provider, "stats"):
            reads, misses = self.provider.stats
        lines = [
            f"device: {self.provider.name if self.provider else '-'}",
            f"6dof: {'stable' if snap.stable else 'unstable'} "
            f"age {snap.age * 1000:.0f}ms (r{reads}/m{misses})",
            f"pos [{pos[0]:+.3f} {pos[1]:+.3f} {pos[2]:+.3f}]",
            f"quat [{quat[0]:+.3f} {quat[1]:+.3f} {quat[2]:+.3f} {quat[3]:+.3f}]",
            f"mode: {'stereo' if self.stereo else 'mono'}",
            f"lens: h{self.lens.get_hfov():.1f} v{self.lens.get_vfov():.1f} "
            f"a{self.lens.get_aspect_ratio():.3f} "
            f"n{self.args.near:g} f{self.args.far:g}",
            f"res: {w}x{h} fps: {fps:.0f}",
            f"frames: {self.frames}",
            f"fade: {'off' if not self.fade.enabled else f'w{self.fade.width:.2f} s{self.fade.strength:.1f}'}",
        ]
        lines.extend(self._hand_debug_lines())
        if self.table is not None:
            lines.extend(self._table_debug_lines())
        lines.append("R recenter - D debug - F fade - Esc quit")
        for i, line in enumerate(self._debug_lines):
            if i < len(lines):
                line.setText(lines[i])
                line.show()
            else:
                line.hide()

    def _hand_debug_lines(self) -> list:
        """Hand-tracking/manipulation status rows (empty when off)."""
        man = getattr(self, "manipulator", None)
        if man is None or not man.enabled:
            return []
        tracker_on = self.hand_tracker is not None
        cam_ok = self.cam_stream is not None
        infps = self.hand_tracker.inference_fps if tracker_on else 0.0
        st = getattr(self, "gesture_state", None)
        n_hands = len(self._last_hands) if self._last_hands else 0
        return [
            f"hand: {'ON' if tracker_on else 'off(sim/key)'} "
            f"cam:{'ok' if cam_ok else '--'} inf:{infps:.0f}fps",
            f"hands:{n_hands} gesture:{st.state if st else '-'} "
            f"conf:{st.confidence if st else 0.0:.2f}",
            f"target:{man.mode}/{man.selected or '-'} "
            f"grab:{man.grabbed or '-'} hover:{man.hover_target or '-'}",
            "M manip V mode B obj U undo X reset G pinch H track",
        ]

    def _log_diagnostics(self) -> None:
        """Required startup audit: framebuffer, lens, regions, display."""
        win = self.base.win
        if win is not None:
            print(f"[diag] framebuffer: {win.get_x_size()}x{win.get_y_size()}",
                  file=sys.stderr)
        print(f"[diag] lens: hfov={self.lens.get_hfov():.2f} "
              f"vfov={self.lens.get_vfov():.2f} "
              f"aspect={self.lens.get_aspect_ratio():.4f} "
              f"near={self.args.near:g} far={self.args.far:g}",
              file=sys.stderr)
        proj = self.lens.get_projection_mat()
        for r in range(4):
            row = proj.get_row(r)
            print(f"[diag] proj row{r}: "
                  f"{row[0]:+.5f} {row[1]:+.5f} {row[2]:+.5f} {row[3]:+.5f}",
                  file=sys.stderr)
        if win is not None:
            print(f"[diag] display regions: "
                  f"{win.get_num_active_display_regions()}",
                  file=sys.stderr)
            for i, dr in enumerate(win.get_active_display_regions()):
                print(f"[diag] region {i}: dims=({dr.get_left():.2f},"
                      f"{dr.get_right():.2f},{dr.get_bottom():.2f},"
                      f"{dr.get_top():.2f}) "
                      f"cam={dr.get_camera().get_name() if dr.get_camera() else None} "
                      f"stereo={dr.get_stereo_channel() if hasattr(dr, 'get_stereo_channel') else '-'}",
                      file=sys.stderr)
        if self.stereo:
            for i, lens in enumerate(self.eye_lenses):
                print(f"[diag] eye{i}: hfov={lens.get_hfov():.2f} "
                      f"vfov={lens.get_vfov():.2f} "
                      f"aspect={lens.get_aspect_ratio():.4f}",
                      file=sys.stderr)
        mode = (self.provider.display_mode()
                if self.provider is not None and
                hasattr(self.provider, "display_mode") else None)
        print(f"[diag] glasses display mode: "
              f"{('0x%02x' % mode) if mode is not None else 'unknown'}",
              file=sys.stderr)

    def run(self) -> bool:
        if self.provider is None:
            return False
        try:
            self.provider.start()
        except (FileNotFoundError, RuntimeError) as exc:
            print(f"[ar] {exc}", file=sys.stderr)
            print("[ar] hardware unavailable; use --provider desktop "
                  "for simulation or --self-test for diagnosis.",
                  file=sys.stderr)
            self.provider = None
            return False
        print("[ar] R = recenter, D = debug, Esc/Q = quit",
              file=sys.stderr)
        if self.args.manipulate and self.args.hands == "mediapipe":
            self._start_hand_tracker()
        self._log_diagnostics()
        self.base.run()
        return True


def main(argv=None) -> int:
    args = parse_args(argv)
    if args.list_displays:
        return list_displays()
    if args.self_test:
        return viture_sdk.self_test()
    if not args.windowed and args.smoke_frames == 0 and "DISPLAY" not in os.environ \
            and not os.environ.get("WAYLAND_DISPLAY"):
        print("No display found; use --windowed on a desktop, "
              "--smoke-frames N headless, or --self-test.", file=sys.stderr)
        return 2
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__))))
    if args.render_mode == "stereo" and args.smoke_frames > 0:
        print("Stereo needs a window; smoke runs are mono.", file=sys.stderr)
        return 2
    app = VitureARApp(args)
    return 0 if app.run() else 1


if __name__ == "__main__":
    raise SystemExit(main())
