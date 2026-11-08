# AR PoC — native optical AR on VITURE Luma Ultra

Single Python + Panda3D application that renders marker-anchored miniature
golf (or calibration wireframes) on the VITURE Luma Ultra's physical display.
The Carina 6DoF head pose moves the camera. No virtual monitors or desktop capture,
no video passthrough in the default path: one fullscreen window on the
glasses output, pure-black clear (invisible on the additive combiner),
only virtual geometry emits light.

## Continuous Neon Cyber Golf terrain

The default scene is a seeded floating industrial island, not modular course
tiles. `src/course_generator.py` creates start/end areas and 2–4 intermediate
controls, then uses three Chaikin passes for a smooth, overshoot-free route. A
low-frequency domain-warped macro field (3 octaves) plus one broad angled
seeded ridge forms the base relief; a corner mesa and an opposite basin add
two deliberate silhouettes. Blend is flat in the corridor core and cubic into
the noisier field; start and target pads flatten. Route endpoints inset to
±38% of the terrain width so widened landing pads stay inside the diorama.

At the default table size the island uses 54×34 cm. Rendering, height/slope
queries, validation and the static Bullet collision mesh use the same function
and vertices (the fairway ribbon samples exact rendered-triangle height with
a 1.2 mm offset, edges +2.0 mm, marks +1.4 mm; 9 cross-sections). Terrain mesh
normals are smooth, shared and normalized; the beveled sidewall has corrected
outward winding plus a cyan perimeter trim. A dark-teal fairway ribbon and
lime dashes mark the route; dark-rimmed irregular plasma pools with bright halo
rings represent hazards. Procedural sphere (22 mm default, 20–43 mm
configurable), target rings, barriers and crystals replace prior golf-specific
models. Sparse city props (18–34 mm, `max` sizing, ≥ fairway×0.85 clearance,
upright street-facing) come from the external reodesuxz pack. The
cyberpunk-only manifest has no traditional-asset fallback.

Difficulty changes geometry: Easy has two gentle controls, a 12.0 cm
fairway, low relief and no blockers; Medium has three controls, a 9.0 cm
corridor, moderate relief and partial direct-line barriers; Hard has four
controls, a 6.5 cm corridor, stronger elevation, direct barriers and three
plasma areas. Validation checks table bounds, ball-radius clearance, finite
terrain, route-center slopes, object footprints and direct-line interference.
100/100 seeds per difficulty pass at 60×40 cm (Nov 2026 desktop run, zero
rejections). This is geometric evidence, not proof of stroke-level playability.

Scale ownership remains `table-stage → golf-stage-root` (position/yaw) `→
course-scale-root` (only scale owner) `→ golf-course`. Terrain is authored as
final metres divided by design scale; the 22 mm ball alone compensates by
1/scale. Atomic regeneration removes the old visual and Bullet subtree without
touching tracking, anchor, camera, or physical obstacles. Physical overlays
query terrain height while preserving measured table-local XY.

Materials and light: `src/cyber_theme.py` centralizes the sRGB-authored
palette (converted to linear exactly once for the sRGB framebuffer),
per-pixel ambient/key/fill lights with shader-auto, and reusable
metallic/emissive materials. Vertex-coloured terrain/ribbon carry no
MaterialAttrib so vertex colours drive lighting without double tint;
neon geometry uses flat node colour with lights off. Imported glTF colours
stay untouched except emission ×0.8 and a roughness/metallic lift for
non-emissive props. Texture filtering is linear-mag, trilinear-mip-min,
about 8× anisotropic.

Controls: Alt+1/2/3 difficulty, Alt+G random, Alt+R current seed, Alt+Z
previous, Alt+F cyber style proof, Alt+S/L save/load, Alt+T seed entry, Alt+V
route debug, Alt+N neon, and Alt+B optional desktop bloom (Quality preset
enables it; Balanced keeps it off). Presets are
Performance (65², fixed-function, no sRGB, MSAA 2 requested) /
Balanced, the default (97², per-pixel, sRGB, MSAA 4 requested) /
Quality (129², per-pixel, sRGB, MSAA 8 requested, bloom on); this AMD driver
reports actual MSAA 8 in every mode with 24-bit RGB/depth. Bloom is
`--bloom-threshold 0.70 --bloom-intensity 0.55 --bloom-size small` with blend
`(.30,.40,.30,0.0)`; bloom buffers report MSAA 4/8 so AA survives the
compositor. Pure-black clear remains intact; bloom is unnecessary for
readability and stays disabled for stereo. `--graphics-debug` logs
framebuffer/MSAA, mesh/geom/texture counts, preset/shader/filter/bloom and
FPS (about 120 FPS Balanced/Quality here).

## Physical-object obstacles (experimental)

`src/physical_obstacles.py` receives latest-only JPEGs from the existing
`CameraStream`, the existing `TimeSync`/`PoseHistory` pose at frame time, the
current table anchor and camera-to-head transform. A worker undistorts each
RGB frame and homography-warps the known table plane to a 500 px/m canonical
image (configurable). Views over 40 degrees from overhead or with under 65%
coverage are rejected. Seven good empty-table views form an in-memory median
reference (no automatic background adaptation). The central 14 cm around the
default marker is masked; Shift+M masks another selected permanent feature.
Lighting-normalized Lab colour differences, shadow suppression, morphology and
connected contours yield approximate tabletop-plane footprints. Five matched
observations confirm an object; eight fully visible, baseline-matching empty
observations remove it. Offscreen regions do not count toward removal. Camera
work runs in a latest-only worker; submissions are capped at 5 Hz. A recognized
hand from the existing *optional* MediaPipe hand tracker suppresses the whole
frame; without that tracker, temporal stability is the only hand filter.

`src/obstacle_visuals.py` attaches stable table-local nodes under `table-stage`
(siblings of the independently nudged golf stage), loading cyberpunk crates,
generators, holograms or barriers on demand. Colliders are simple static Panda3D
`CollisionSphere`/`CollisionBox` proxies on solid mask bit 1 or water hazard
bit 2; no ball dynamics are provided. Shift+V switches between a bright
footprint ring and a full model. There is no real-world occlusion. Default
visual/collider height is an **unmeasured** 5.5 cm. Layout save/reload is
explicit and bound to table configuration and saved calibration, not portable.
The session-only reference is invalidated when hand-eye or anchor is restored.

For a live test: establish a LOCKED/APPROX marker anchor and clear the real
course, Shift+B, wait for `[obstacle] baseline captured`, place an object,
remove the hand, walk around and verify it stays table-locked. Repeat with a
second object, then remove one and observe hysteretic removal (Shift+X if
uncertain). Shift+A toggles automatic mode; Shift+S collects manual candidates
even when auto is off. `--obstacle-debug` displays RGB, top-down image,
reference, mask and candidate/accepted overlays on the laptop only. Enable
`--hands mediapipe --manipulate` for the optional hand suppression path.

**Not hardware-verified.** Projection uses approximate intrinsics and a
camera-to-head flip unless machine-local calibration exists. Plane homography
misplaces tall objects and cannot recover contact geometry or metric height;
false positives from hands/shadows and false negatives for low-contrast or
marker-adjacent objects remain possible. No measured detection or placement
error is available; calibrate and validate through the glasses before claiming
alignment. Stereo depth/segmentation and ball physics are deferred.

## Architecture

```text
VITURE Luma Ultra
  USB -> libglasses.so (ctypes) -> providers.ViturePoseProvider
                                        (background poll thread, 120 Hz,
                                         immutable snapshots + lock)
  DP  -> Hyprland output DP-1 -> fullscreen Panda3D window
                                    persistent table / golf scene
                                   per-frame: pose -> look_at camera
```

* **Pose math** (`src/pose_math.py`, pure stdlib): GL <-> Panda basis
  change, Hamilton quats, rigid-matrix inverse. Unit-tested
  (`tests/test_pose_math.py`): identity, XYZ translations, yaw, pitch,
  roll, combined, both inversion directions, head-to-view round trip.
* **Camera**: the world lives under one `gl_space` node (GL numbers);
  the camera is positioned in Panda space and aimed with `look_at`
  along head-forward. `look_at` is Panda's own orientation routine, so
  lens/node conventions stay consistent by construction (verified
  pixel-identical against `look_at` ground truth in offscreen renders).
  Roll defaults to gravity-level. A direct `set_quat` of the SDK
  quaternion was tried and rejected: Panda cameras look along local
  +Y while the SDK pose assumes a -Z-looking camera, and composing
  through Panda's quat conventions faced the wrong way in testing.
* **Providers** (`src/providers.py`): `viture` (hardware, background
  poll thread), `desktop` (absolute mouse-look + arrows/Space/C),
  `synthetic` (slow orbit for headless smoke tests). All emit the same
  GL-frame pose; the renderer cannot tell them apart.

## Why no virtual monitors

The glasses are already a physical DisplayPort monitor. The app opens
one fullscreen window on that output (auto-detected via
`hyprctl monitors -j`, overridable with `--monitor`/`--win-origin`)
and then moves + fullscreens it onto the glasses workspace via
`hyprctl` dispatch (runtime window management only -- Panda's own
X11-VidMode fullscreen request does not exist under XWayland, so the
compositor would otherwise tile the window). Use `--no-place` to skip
the auto-placement. There is nothing to capture, mirror, or place:
the world exists once, the camera moves through it. Objects outside
the panel FOV simply wait until you look at them.

## Setup

```sh
nix develop
uv sync

# NixOS: configure services.udev.extraRules, rebuild and replug.
# See HANDOFF.md for this machine's pending rebuild failure.
```

The checked-in `etc/70-viture.rules` is a reference for mutable systems;
NixOS uses `/etc/nixos/viture.nix` instead. The proprietary SDK is resolved from
`$VITURE_SDK_LIB`, defaulting to the reference checkout's unpacked
blobs (never vendored).

## Launch

```sh
uv run python src/ar_poc.py --self-test          # hardware check, no window
uv run python src/ar_poc.py --list-displays      # find the glasses output
uv run python src/ar_poc.py --provider desktop --windowed   # sim preview
uv run python src/ar_poc.py --provider desktop --windowed --calibrate  # rig
uv run python src/ar_poc.py                      # glasses, auto mode
uv run python src/ar_poc.py --render-mode stereo # side-by-side
uv run python src/ar_poc.py --smoke-frames 60    # headless check
```

Fullscreen auto-targets the VITURE output (move + real fullscreen via
`hyprctl` dispatch; `--no-place` skips it). Controls: **R** recentre,
**D** debug overlay, **Esc/Q** quit. The old world-space grid has been
removed; only the marker-aligned table outline remains in table mode.

## Render modes

* `mono` (default unless the window is >= 3800 wide): one camera.
* `stereo`: two half-width display regions, two cameras separated by
  `--ipd` (default 0.063 m), parallel (no toe-in), green `L`/`R`
  badges visible only to their own eye (camera masks) as a routing
  test. `--swap-eyes` exchanges the assignment for diagnostics.
* `auto`: stereo iff the window is SBS-wide.

FOV (`--fov`, default 29 deg vertical) and IPD are provisional --
not calibrated to the panel optics. 29 deg derives from the advertised
~52 deg diagonal at 16:10 (atan-mapped, not the diagonal reused as a
horizontal angle). `--hfov` anchors horizontal instead; passing both
uses them verbatim with a stretch warning if they fight the window.
`--near`/`--far` set the clip planes (default 0.05/50 m). No
distortion shaders (no verified optical parameters exist). Per-eye
aspect is handled; no stretching.

`--request-sbs` asks the glasses (SDK display-mode API) for
3840x1200@90 SBS, then verifies. EXPERIMENTAL.

## Rendering-area audit (what was checked, what was found)

* **Framebuffer vs display**: the app requests the detected output's
  native size (1920x1200 for DP-1, not a hardcoded 1920x1080 -- the
  old constant would letterbox or stretch). Startup `[diag]` lines
  log framebuffer, lens (hfov/vfov/aspect/near/far), the full
  projection matrix, and every display region with dimensions,
  camera, and stereo channel.
* **Lens audit** (offscreen): `set_fov(h, v)` sets horizontal then
  vertical (verified by readback); single-arg `set_fov` sets a SQUARE
  frustum and is never used; `set_aspect_ratio` mutates vfov, so the
  app derives hfov from the live framebuffer aspect every frame
  (Wayland applies the final size asynchronously -- the drawable is
  re-queried per frame, mirroring the C reference).
* **Stereo subdivision**: two mono regions (0,0.5)/(0.5,1.0), each
  with its own perspective lens at half aspect -- verified in
  screenshots (independent L/R routing via camera masks, visible
  parallax, no stretch).
* **Placement**: Panda's X11 fullscreen request is a VidMode call that
  does not exist under XWayland, so Hyprland tiled the window (seen:
  630x368 logical on the laptop panel). The app now moves its own
  window onto the glasses workspace and real-fullscreens it via
  `hyprctl` dispatch (verified: client shows ws 4, fs 2,
  1920x1200 on DP-1, `-o DP-1` capture fills the frame edge to edge).
* **Calibration rig** (`--calibrate`): frustum-filling border, corner
  markers, center crosshair, and 5/10/15/20 deg rings with degree
  labels, independent of the AR scene. If a border edge or corner
  marker is missing on the glasses, that side is clipped by optics
  or compositor -- not by the scene (the rig provably reaches the
  framebuffer edge: the DP-1 capture shows markers at all four
  corners and the border spanning the full width).
* **Near/far**: 0.05/50 m; the cube at 1.2-1.5 m sits comfortably
  inside; no clipping of scene content observed.

## Optics vs software (verdict)

After the fixes above, the software provably uses the entire physical
display: fullscreen 1920x1200 on DP-1, frustum matched to the panel
aspect, calibration geometry reaching every edge and corner of the
captured output. What remains is physical, not software:

* The panel's ~52-degree diagonal field is genuinely narrow -- the
  "small virtual monitor" feeling is the optics, not cropping. No
  projection change can show more than the display emits.
* Edge cut-off while wearing the glasses is the eyebox: move the
  eyes and the image clips. The calibration rig distinguishes this
  (markers visible in a static capture but clipping with eye
  movement = eyebox, not software).
* Registration against the real world stays approximate until true
  per-eye optical parameters (not a diagonal spec) are known; do not
  present widened FOV numbers as genuine optical FOV.

## Recentering

`R` (or provider start after first stable pose) calls
`reset_origin_carina` with the current pose: position + yaw re-anchor
in front of the wearer; pitch/roll stay gravity-anchored (VIO-owned).

## Diagnostics

Debug overlay (D): device, tracking status, pose age (ms since last
SDK sample -- proves the background thread is alive), position,
quaternion, mode, resolution, fps, frame state. Terminal logs
every 90 frames otherwise (the glasses are hard to read).

Tracking failure modes: poses stop (`age` climbs) but the last valid
pose is held -- the scene freezes instead of flying away; overlay
stays hidden (black) until the first stable sample.

## Optical edge fade (--no-fade to disable; F toggles at runtime)

A camera-following quad carrying a tiny GLSL shader multiplies the
scene toward black at the viewport edges (`smoothstep` on rectangular
edge distance, default width 10% of the half-view, full strength).
Tied to clip-space NDC, so it is viewport-relative by construction and
per-eye independent in stereo (verified: each half fades at its own
edges, no double application). The debug HUD lives in a later display
region and stays unfaded. Runtime: **F** toggle, **[**/**]** width,
**-**/**=** strength (also `--fade-width`, `--fade-strength`).

Verified pixel-level on mono + stereo screenshots (calibration rig):
smooth falloff, no projection change, world-locking intact, black
stays black, disabling restores the exact original render. GPU cost is
one fullscreen quad with a ~10-line shader (no measurable fps change).

## Optical edge fade (`--no-fade` to disable; `F` toggles live)

A camera-following quad carrying a tiny GLSL shader multiplies the
scene toward black at the viewport edges (`smoothstep` on rectangular
edge distance, default width 10% of the half-view, full strength).
Black is optically transparent on the additive combiner, so softening
the cutoff reduces the "screen door" feeling without changing any
geometry, poses, or projection. Tied to clip-space NDC, so it is
viewport-relative by construction and per-eye independent in stereo
(verified: each half fades at its own edges, no double application).
The debug HUD lives in a later display region and stays unfaded.

Runtime: **F** toggle, **[**/**]** width -/+, **-**/**=** strength
(also `--fade-width`, `--fade-strength`). Verified pixel-level on
mono + stereo screenshots (calibration rig): smooth falloff, no
projection change, world-locking intact, black stays black, disabling
restores the exact original render. GPU cost is one fullscreen quad
with a ~10-line shader (no measurable fps change).

## Hand tracking + manipulation (--manipulate to enable)

No native hand API exists in the Linux SDK (headers checked), so hands
come from the glasses' own RGB camera + MediaPipe Hand Landmarker
(`src/hand_track.py`), fully decoupled from rendering:

```text
CameraStream (USB MJPEG, own thread)
  -> take_frame() latest-only mailbox -> HandTracker worker thread
  -> MediaPipe VIDEO mode (~15-30 ms/frame, non-blocking)
  -> get_hands() latest HandState list (never blocks, never queues)
```

Each `HandState` carries 21 normalized landmarks, handedness,
confidence, pinch position and a timestamp. The render thread only
ever reads the latest result; if inference slows down, frames are
dropped, never queued.

Model: `models/hand_landmarker.task` (downloaded once from Google's
bucket; git-ignored). Deps: `mediapipe` + `numpy` via uv (needs system
`libxcb`, provided by the flake).

### Coordinate mapping (approximate -- read this)

MediaPipe landmarks are NOT metric positions. The app builds a
**ray** from the normalized pointer (`src/pointer.py`):

* Pinhole model, square pixels, principal point at image centre,
  configurable horizontal FOV (default 70 deg -- plausible, NOT
  measured on this camera).
* Camera assumed at the head origin, axes aligned with the head
  frame (configurable translation offset, default zero). **The real
  camera is offset from the eye; this is an explicit approximation.**
* `flip_x`/`flip_y` flags available if the stream turns out mirrored
  or rotated (default: upright, unmirrored -- world-facing camera).
* The ray is transformed by the live head pose (same Hamilton path
  as rendering), then intersected with a camera-facing manipulation
  plane. All motion is a delta of successive intersections.

### Interaction model

`GestureRecognizer` (pure logic, unit-tested): idle/hover/pinch/drag
with hysteresis (engage < 0.05, release > 0.07 normalized thumb-index
distance), 2-frame confirmation, EMA smoothing, deadzone, loss
timeout with freeze-then-release (no jumps on reacquire), stale-frame
and low-confidence rejection.

`SceneManipulator` owns a `stage_root` node; all world objects live
beneath it. Stage mode drags the whole world along the ray-plane
intersection delta; object mode ray-selects (4 deg cone) then drags
the single object (grab offset preserved, no snapping). Undo stack,
stage reset, keyboard nudge (IJKL + O/P), yaw (,/.), all guarded by an
explicit enable flag -- disabled manipulation can never move the
scene, and cancelling a drag restores the grab pose.

Desktop-sim note: while manipulation is enabled, mouse-look is
suspended (the mouse aims the hand pointer only). Otherwise pointing
at an object swings the view away from it and drags go backwards --
verified by test. Arrows still move the head; R recentres.

Flags: `--manipulate`, `--hands mediapipe|sim` (default sim),
`--hand-model`, `--manip-mode stage|object`, `--select-cone`,
`--sensitivity`. Keys: **M** on/off, **V** stage/object, **B** cycle
object, **U** undo, **X** reset stage, **G** pinch (keyboard/mouse
fallback), **H** hand tracker on/off. Desktop sim: mouse = pointer,
**G** or left mouse = pinch.

## Known limitations / unverified on hardware

* **SBS output switching did not engage on this unit.** `set` to
  `0x45` returned success but the mode never appeared (no DRM change);
  other mode writes behaved inconsistently (register-only effects).
  The physical output stayed 1920x1200@120 throughout. Stereo is
  therefore verified offscreen only (split, masks, indicators,
  aspect); **mono is the hardware-verified path.**
* FOV is an estimate from the ~52-degree diagonal; registration
  against the real world is approximate until panel optics are known.
* Roll is gravity-levelled (look_at default up); head-tilt roll does
  not tilt the world.
* The video panel from the earlier video-see-through iteration is
  isolated behind `--video-panel` (legacy, out of scope).
* Predict time is 0 (task requirement; revisit after SDK units check).
* **Live pinch-drag with a real hand** is implemented and unit-tested
  (synthetic sequences incl. noise, loss, reacquire) and the pipeline
  was verified live (30 fps inference, real hand detected at 0.98
  confidence, `hover` state, pointer indicator). Confirming a full
  grab-move-release with your own hand is the remaining live step.

## Tabletop AR (automatic for golf/gallery; `--table` for calibration scene)

Virtual objects sit on the real physical table and stay put while you
move. A printed ArUco marker (default DICT_6X6_250 id 42, 100 mm)
defines the table frame (x right, y up-in-plane, z normal, centred);
the glasses RGB camera detects it, and the anchor chain
`T_W_T = T_W_H @ T_H_C @ T_C_M` pins the world to the table:

* `T_W_H`: live 6DoF VIO pose, interpolated to the camera frame time.
* `T_H_C`: camera-to-head extrinsics. Factory state is an **explicitly
  approximate** head-aligned flip (zero offset, labelled APPROX);
  press **C** after moving the head through diverse rotations to solve
  the real thing (Park-Martin AX=XB, needs >= 4 pairs about mixed
  axes -- single-axis motion is rejected as degenerate), then **S**.
* `T_C_M`: IPPE_SQUARE marker pose. Planar ambiguity (two near-equal
  fits) skips the frame rather than flipping the table.

Anchor states: UNINITIALIZED -> LOCKED/APPROX -> DEGRADED (marker gone
> 1 s or tracking unstable) -> LOST (> 10 s, head teleport, or blind
recenter). Small residuals get a damped correction, medium ones a
logged single-step snap, large single frames are outliers until 5
consistent samples force a relock. R recenter carries the anchor
(position + yaw) into the new world frame.

Flags: `--table --table-w --table-l --marker-size-mm --table-dict
--table-id --table-calib (default table_calib.json)
--table-approx-hfov` (assumed camera HFOV until intrinsics are
calibrated). Keys: **Y** scan on/off, **N** debug viz, **Z** freeze,
**S** save, **0** restore, **1/2** object lift, **3/4** anchor yaw,
**5/6** anchor x, **7/8** anchor z, **9** clear adjust, **C** hand-eye
solve (note: C is also the desktop-sim down key -- table work
assumes the viture provider).
`scripts/make_table_target.py` prints the marker at exact millimetre
size (+ JSON sidecar) and a checkerboard for intrinsics calibration.

Verification history and current status (see [HANDOFF.md](HANDOFF.md) for
the current handoff and live acceptance steps):

* 84 tests passed at the latest handoff (`PYTHONPATH=src uv run python -m
  unittest discover -s tests`), covering pose conversion, hand input,
  anchor/calibrator/detector behavior and real downloaded golf assets.
* Live: glasses camera streams 1920x1080@30 MJPEG; **device
  timestamps are always 0 in this SDK build**, so TimeSync runs on the
  arrival-time fallback path by design (verified working). Detector
  runs clean on real frames (no false positives over 5 samples of a
  lit indoor scene; synthetic-marker files decode as id 42).
  Headless smoke (default and `--table`) and a live windowed `--table`
  run render cleanly for thousands of frames. Full `--table` app on
  the glasses (DP-1, 6DoF locked, camera + detector + tracker live):
  healthy, anchor correctly UNINITIALIZED with no marker in view.
* A later user run **did** acquire an APPROX anchor and reported much
  better table behavior after state-machine repairs. It also exposed
  `reject-inconsistent` floods and DEGRADED recovery gaps that were then
  addressed in code. This is not a measurement of tabletop accuracy, and
  there has been **no live walk-around acceptance for the new golf scene**.

Acceptance (needs printed marker + glasses free):

* A: marker fullscreen on screen -> detector ids [42], corners sane.
* B: point glasses at marker, Y -> state APPROX, conf rising.
* C: **C** after diverse motion -> rot resid < 0.5 deg.
* D: walk around table -> objects stay (< 2 cm drift by eye).
* E: cover marker 3 s -> DEGRADED, frozen; uncover -> snaps back.
* F: R recenter -> anchor carried, no jump.
* G: **S**, restart, **0** -> anchor restored as DEGRADED.
* Hand-camera calibration (FOV 70 deg, zero extrinsics) is explicitly
  approximate; treat grab alignment as experimental, not metric.
