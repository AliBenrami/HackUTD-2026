"""ctypes bindings for the proprietary VITURE Glasses SDK (libglasses.so).

Mirrors the lifecycle proven by the reference C sample
(``02_ar_overlay`` + ``common/src/carina_pose.c``):

    create -> set_dof_type_carina -> initialize
        -> register_callbacks_carina -> start

and per-frame ``xr_device_provider_get_gl_pose_carina``.

Pose convention (from the SDK): OpenGL coordinates
(x -> right, y -> up, z -> backward) as
``[px, py, pz, qw, qx, qy, qz]``. Pitch and roll are gravity-anchored
by the onboard VIO; do NOT use the raw-IMU API on a Carina device
(documented "no effect for carina device").
"""

from __future__ import annotations

import ctypes
import os
import platform
import sys
import threading
import time

VITURE_USB_VENDOR_ID = 0x35CA
SYSFS_USB_ROOT = "/sys/bus/usb/devices"

SUCCESS = 0
DEVICE_TYPE_CARINA = 2

POSE_STABLE = 0
POSE_UNSTABLE = 1

# Forward prediction for get_gl_pose_carina. The public header says
# "seconds" while the reference sample passes 11e6 straight through;
# experimentally a nonzero predict issued before the first VIO sample
# blocks indefinitely, while 0.0 always returns promptly. Per
# project policy we start (and stay) at 0 and only revisit prediction
# after verifying the units against the installed SDK.
POSE_PREDICT_DEFAULT = 0.0

# Display modes (viture_protocol_public.h). The 3D SBS modes drive the
# panel as two side-by-side eye images; 0x45 is 3840x1200 @ 90Hz.
DISPLAY_MODE_1920_1080_60HZ = 0x31
DISPLAY_MODE_3840_1080_90HZ = 0x35
DISPLAY_MODE_1920_1080_90HZ = 0x33
DISPLAY_MODE_3840_1200_90HZ_SBS = 0x45


def _default_sdk_search_paths() -> list[str]:
    machine = platform.machine()
    arch_dir = "viture_arm64/aarch64" if machine == "aarch64" else "viture_x86_64/x86_64"
    here_sdk = os.path.join(os.getcwd(), "sdk", arch_dir, "libglasses.so")
    return [
        here_sdk,
        # Reference checkout with the unpacked vendor blobs (dev machine).
        f"/home/jude/Repos/Viture_AR_Playground/sdk/{arch_dir}/libglasses.so",
        f"/usr/lib/viture/{arch_dir}/libglasses.so",
        "/usr/lib/libglasses.so",
    ]


def find_sdk_lib() -> str:
    """Locate libglasses.so via $VITURE_SDK_LIB (file or dir) or known paths."""
    env = os.environ.get("VITURE_SDK_LIB", "").strip()
    if env:
        cand = env if env.endswith(".so") else os.path.join(env, "libglasses.so")
        if os.path.isfile(cand):
            return cand
        raise FileNotFoundError(
            f"VITURE_SDK_LIB={env!r} does not contain libglasses.so "
            f"(looked at {cand!r})"
        )
    for cand in _default_sdk_search_paths():
        if os.path.isfile(cand):
            return cand
    raise FileNotFoundError(
        "libglasses.so not found. Unpack the proprietary VITURE SDK and set "
        "VITURE_SDK_LIB to its arch dir "
        "(e.g. <sdk>/viture_x86_64/x86_64). See README.md."
    )


def find_glasses_pid(lib=None) -> int:
    """Scan sysfs USB for a VITURE glasses device; return its product ID.

    Prefers the SDK's own xr_device_provider_is_product_id_valid filter
    when a loaded lib is given, else accepts any 0x35CA device that is
    not the known microphone PID (0x1102).
    """
    found: int | None = None
    try:
        entries = os.listdir(SYSFS_USB_ROOT)
    except OSError as exc:
        raise RuntimeError(f"cannot scan {SYSFS_USB_ROOT}: {exc}") from exc
    for name in entries:
        if name.startswith(".") or ":" in name:
            continue
        try:
            with open(os.path.join(SYSFS_USB_ROOT, name, "idVendor")) as f:
                vid = int(f.read().strip(), 16)
            if vid != VITURE_USB_VENDOR_ID:
                continue
            with open(os.path.join(SYSFS_USB_ROOT, name, "idProduct")) as f:
                pid = int(f.read().strip(), 16)
        except (OSError, ValueError):
            continue
        if lib is not None:
            try:
                if not lib.xr_device_provider_is_product_id_valid(pid):
                    continue
            except Exception:
                pass
        if pid == 0x1102 and found is None:
            found = pid  # microphone iface; keep looking for the glasses
            continue
        return pid
    if found is not None:
        return found
    raise RuntimeError("no VITURE glasses found on USB (is the cable connected?)")


def load_lib(path: str | None = None) -> ctypes.CDLL:
    """Load libglasses.so and declare the C ABI we use."""
    lib = ctypes.CDLL(path or find_sdk_lib())

    lib.xr_device_provider_create.argtypes = [ctypes.c_int]
    lib.xr_device_provider_create.restype = ctypes.c_void_p

    lib.xr_device_provider_get_device_type.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_get_device_type.restype = ctypes.c_int

    lib.xr_device_provider_is_product_id_valid.argtypes = [ctypes.c_int]
    lib.xr_device_provider_is_product_id_valid.restype = ctypes.c_int

    lib.xr_device_provider_set_dof_type_carina.argtypes = [ctypes.c_void_p, ctypes.c_int]
    lib.xr_device_provider_set_dof_type_carina.restype = ctypes.c_int

    lib.xr_device_provider_initialize.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p]
    lib.xr_device_provider_initialize.restype = ctypes.c_int

    lib.xr_device_provider_register_callbacks_carina.argtypes = [ctypes.c_void_p] * 5
    lib.xr_device_provider_register_callbacks_carina.restype = ctypes.c_int

    lib.xr_device_provider_start.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_start.restype = ctypes.c_int

    lib.xr_device_provider_stop.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_stop.restype = ctypes.c_int

    lib.xr_device_provider_shutdown.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_shutdown.restype = ctypes.c_int

    lib.xr_device_provider_destroy.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_destroy.restype = None

    lib.xr_device_provider_get_gl_pose_carina.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
        ctypes.c_double,
        ctypes.POINTER(ctypes.c_int),
    ]
    lib.xr_device_provider_get_gl_pose_carina.restype = ctypes.c_int

    lib.xr_device_provider_reset_origin_carina.argtypes = [
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_float),
    ]
    lib.xr_device_provider_reset_origin_carina.restype = ctypes.c_int

    lib.xr_device_provider_set_log_level.argtypes = [ctypes.c_int]
    lib.xr_device_provider_set_log_level.restype = None

    lib.xr_device_provider_get_display_mode.argtypes = [ctypes.c_void_p]
    lib.xr_device_provider_get_display_mode.restype = ctypes.c_int

    lib.xr_device_provider_set_display_mode.argtypes = [ctypes.c_void_p,
                                                       ctypes.c_int]
    lib.xr_device_provider_set_display_mode.restype = ctypes.c_int

    lib.xr_camera_provider_get_camera_vid.argtypes = [ctypes.c_int]
    lib.xr_camera_provider_get_camera_vid.restype = ctypes.c_int

    lib.xr_camera_provider_get_camera_pid.argtypes = [ctypes.c_int]
    lib.xr_camera_provider_get_camera_pid.restype = ctypes.c_int

    lib.xr_camera_provider_create.argtypes = [ctypes.c_int, ctypes.c_int]
    lib.xr_camera_provider_create.restype = ctypes.c_void_p

    lib.xr_camera_provider_start.argtypes = [ctypes.c_void_p,
                                             _camera_frame_callback_type(),
                                             ctypes.c_void_p]
    lib.xr_camera_provider_start.restype = ctypes.c_int

    lib.xr_camera_provider_stop.argtypes = [ctypes.c_void_p]
    lib.xr_camera_provider_stop.restype = ctypes.c_int

    lib.xr_camera_provider_destroy.argtypes = [ctypes.c_void_p]
    lib.xr_camera_provider_destroy.restype = None

    lib.xr_camera_provider_is_streaming.argtypes = [ctypes.c_void_p]
    lib.xr_camera_provider_is_streaming.restype = ctypes.c_int

    return lib


# Mirrors XRCameraFrame in viture_camera_provider.h. Frames are
# 1920x1080@30fps MJPEG; the data pointer is valid only during the
# callback, so bytes must be copied out immediately.
class XRCameraFrame(ctypes.Structure):
    _fields_ = [
        ("data", ctypes.POINTER(ctypes.c_uint8)),
        ("size", ctypes.c_uint32),
        ("width", ctypes.c_uint32),
        ("height", ctypes.c_uint32),
        ("format", ctypes.c_int),
        ("timestamp", ctypes.c_uint64),
        ("sequence", ctypes.c_uint32),
    ]


CAMERA_FORMAT_MJPEG = 0
CAMERA_START_ATTEMPTS = 5
CAMERA_START_RETRY_S = 0.5


def _camera_frame_callback_type():
    return ctypes.CFUNCTYPE(None, ctypes.POINTER(XRCameraFrame),
                            ctypes.c_void_p)


# Linux usbfs: release interfaces a kernel driver (uvcvideo) holds.
# Python port of common/src/usb_detach.c in the reference repo.
_USBDEVFS_DISCONNECT = (0x55 << 8) | 22  # _IO('U', 22)
_USBDEVFS_IOCTL = (3 << 30) | (16 << 16) | (0x55 << 8) | 18  # _IOWR('U',18,16B)
_USBDEVFS_MAX_INTERFACES = 8


def detach_kernel_driver(vendor_id: int, product_id: int) -> bool:
    """Ask the kernel to release every interface of a USB device.

    Returns True when all interfaces are free (or were never bound).
    ENODATA/EINVAL per interface just mean "nothing bound there".
    Needs write access to the usbfs node (udev rule); not fatal --
    the device may already be free.
    """
    import errno
    import fcntl
    import struct

    busnum = devnum = None
    try:
        entries = os.listdir(SYSFS_USB_ROOT)
    except OSError:
        return False
    for name in entries:
        if name.startswith(".") or ":" in name:
            continue
        try:
            with open(os.path.join(SYSFS_USB_ROOT, name, "idVendor")) as f:
                if int(f.read().strip(), 16) != vendor_id:
                    continue
            with open(os.path.join(SYSFS_USB_ROOT, name, "idProduct")) as f:
                if int(f.read().strip(), 16) != product_id:
                    continue
            with open(os.path.join(SYSFS_USB_ROOT, name, "busnum")) as f:
                busnum = int(f.read().strip())
            with open(os.path.join(SYSFS_USB_ROOT, name, "devnum")) as f:
                devnum = int(f.read().strip())
            break
        except (OSError, ValueError):
            continue
    if busnum is None:
        print(f"[usb] device {vendor_id:04x}:{product_id:04x} not present",
              file=sys.stderr)
        return False

    node = f"/dev/bus/usb/{busnum:03d}/{devnum:03d}"
    try:
        fd = os.open(node, os.O_RDWR)
    except OSError as exc:
        print(f"[usb] cannot open {node} for writing: {exc} "
              "(install etc/70-viture.rules?)", file=sys.stderr)
        return False
    try:
        ok = True
        for ifno in range(_USBDEVFS_MAX_INTERFACES):
            cmd = struct.pack("@iiP", ifno, _USBDEVFS_DISCONNECT, 0)
            try:
                fcntl.ioctl(fd, _USBDEVFS_IOCTL, cmd)
            except OSError as exc:
                if exc.errno not in (errno.ENODATA, errno.EINVAL):
                    ok = False
        if ok:
            print(f"[usb] kernel driver detached from {node}", file=sys.stderr)
        return ok
    finally:
        os.close(fd)


def camera_ids_for(lib: ctypes.CDLL, glasses_pid: int) -> tuple[int, int]:
    """(vid, pid) of the glasses' camera, or (0, 0) if unknown."""
    try:
        vid = int(lib.xr_camera_provider_get_camera_vid(int(glasses_pid)))
        pid = int(lib.xr_camera_provider_get_camera_pid(int(glasses_pid)))
    except Exception:
        return (0, 0)
    if vid <= 0 or pid <= 0:
        return (0, 0)
    return (vid, pid)


class CarinaTracker:
    """Carina 6DoF/3DoF tracking session (Luma Ultra)."""

    def __init__(self, lib: ctypes.CDLL | None = None) -> None:
        self._lib = lib or load_lib()
        self._handle: int | None = None
        self._six_dof = True

    def _bring_up(self, product_id: int, six_dof: bool) -> None:
        lib = self._lib
        handle = lib.xr_device_provider_create(int(product_id))
        if not handle:
            raise RuntimeError("xr_device_provider_create failed")
        try:
            if lib.xr_device_provider_get_device_type(handle) != DEVICE_TYPE_CARINA:
                raise RuntimeError("device is not a Carina (Luma Ultra required)")
            # Order matters: DoF type BEFORE initialize ...
            rc = lib.xr_device_provider_set_dof_type_carina(handle, 1 if six_dof else 0)
            if rc != SUCCESS:
                raise RuntimeError(f"set_dof_type_carina failed ({rc})")
            rc = lib.xr_device_provider_initialize(handle, None, None)
            if rc != SUCCESS:
                raise RuntimeError(f"initialize failed ({rc})")
            # ... and callbacks BEFORE start (VIO captures them at start).
            # All NULL: we poll the pose per frame; VIO still consumes
            # the stereo frames internally.
            rc = lib.xr_device_provider_register_callbacks_carina(
                handle, None, None, None, None
            )
            if rc != SUCCESS:
                raise RuntimeError(f"register_callbacks_carina failed ({rc})")
            rc = lib.xr_device_provider_start(handle)
            if rc != SUCCESS:
                try:
                    lib.xr_device_provider_shutdown(handle)
                finally:
                    raise RuntimeError(f"start failed ({rc})")
        except Exception:
            lib.xr_device_provider_destroy(handle)
            raise
        self._handle = handle
        self._six_dof = six_dof

    def start(self, product_id: int, six_dof: bool = True) -> None:
        lib = self._lib
        lib.xr_device_provider_set_log_level(1)  # errors only
        try:
            self._bring_up(product_id, six_dof)
            return
        except RuntimeError as first_exc:
            # Fallback (mirrors 01_camera_feed/04_sealed_drawing): the SDK
            # drives UVC over libusb itself, so if the kernel's uvcvideo
            # holds the camera, release it and try once more. A no-op
            # detach (already free) just re-raises the original error.
            cam_vid, cam_pid = camera_ids_for(lib, product_id)
            if cam_pid and detach_kernel_driver(cam_vid, cam_pid):
                print("[pose] retrying start after camera detach",
                      file=sys.stderr)
                self._bring_up(product_id, six_dof)
                return
            raise first_exc

    def get_pose(
        self, predict: float = POSE_PREDICT_DEFAULT
    ) -> tuple[tuple[float, float, float], tuple[float, float, float, float], int] | None:
        """Poll the current head pose; None on transient failure.

        Mirrors the C sample, which ignores failed reads and keeps
        rendering with the last pose: -3/NO_DATA while the VIO converges,
        or an occasional miss, must not tear down the session.
        """
        if not self._handle:
            raise RuntimeError("tracker not started")
        pose = (ctypes.c_float * 7)()
        status = ctypes.c_int(POSE_UNSTABLE)
        rc = self._lib.xr_device_provider_get_gl_pose_carina(
            self._handle, pose, float(predict), ctypes.byref(status)
        )
        if rc != SUCCESS:
            return None
        pos = (pose[0], pose[1], pose[2])
        quat = (pose[3], pose[4], pose[5], pose[6])
        if not self._six_dof:
            pos = (0.0, 0.0, 0.0)  # 3DoF: orientation only
        return pos, quat, int(status.value)

    def recenter(self) -> None:
        """Move the tracking origin to the wearer's current pose."""
        if not self._handle:
            raise RuntimeError("tracker not started")
        pose = (ctypes.c_float * 7)()
        status = ctypes.c_int(POSE_UNSTABLE)
        rc = self._lib.xr_device_provider_get_gl_pose_carina(
            self._handle, pose, 0.0, ctypes.byref(status)
        )
        if rc != SUCCESS:
            raise RuntimeError(f"recenter read failed ({rc})")
        rc = self._lib.xr_device_provider_reset_origin_carina(self._handle, pose)
        if rc != SUCCESS:
            raise RuntimeError(f"reset_origin_carina failed ({rc})")

    def get_display_mode(self) -> int:
        """Read the glasses' current display mode (see DISPLAY_MODE_*)."""
        if not self._handle:
            raise RuntimeError("tracker not started")
        return int(self._lib.xr_device_provider_get_display_mode(self._handle))

    def set_display_mode(self, mode: int) -> None:
        """Request a display mode (e.g. SBS 3840x1200); raises on failure."""
        if not self._handle:
            raise RuntimeError("tracker not started")
        rc = self._lib.xr_device_provider_set_display_mode(self._handle,
                                                           int(mode))
        if rc != SUCCESS:
            raise RuntimeError(f"set_display_mode failed ({rc})")

    def close(self) -> None:
        if self._handle:
            try:
                self._lib.xr_device_provider_stop(self._handle)
            finally:
                try:
                    self._lib.xr_device_provider_shutdown(self._handle)
                finally:
                    self._lib.xr_device_provider_destroy(self._handle)
                    self._handle = None

    def __enter__(self) -> "CarinaTracker":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


class CameraStream:
    """MJPEG camera streaming (1920x1080@30) alongside VIO tracking.

    Mirrors 01_camera_feed/04_sealed_drawing: the SDK invokes the frame
    callback on its own camera thread; the latest JPEG is kept under a
    lock and `take_frame()` copies it out for the render thread. Proven
    to coexist with CarinaTracker by 04_sealed_drawing.
    """

    def __init__(self, lib: ctypes.CDLL | None = None) -> None:
        self._lib = lib or load_lib()
        self._handle: int | None = None
        self._callback = None  # kept alive while streaming
        self._lock = threading.Lock()
        self._latest: bytes | None = None
        self._width = 0
        self._height = 0
        self._sequence = 0
        self._ts_ns = 0
        self._arrival_mono = 0.0
        self._frames = 0

    def _on_frame(self, p_frame, _user_data) -> None:
        try:
            frame = p_frame.contents
        except ValueError:
            return
        if frame.format != CAMERA_FORMAT_MJPEG or not frame.data \
                or not frame.size:
            return
        try:
            data = ctypes.string_at(frame.data, frame.size)
        except ValueError:
            return
        with self._lock:
            self._latest = data
            self._width = int(frame.width)
            self._height = int(frame.height)
            self._sequence = int(frame.sequence)
            self._ts_ns = int(frame.timestamp)
            self._arrival_mono = time.monotonic()
            self._frames += 1

    def start(self, glasses_pid: int) -> None:
        lib = self._lib
        cam_vid, cam_pid = camera_ids_for(lib, glasses_pid)
        if not cam_pid:
            raise RuntimeError(
                f"glasses PID 0x{glasses_pid:04x} has no camera")
        print(f"[camera] camera VID=0x{cam_vid:04x} PID=0x{cam_pid:04x}",
              file=sys.stderr)
        # The camera is not immediately re-claimable after a previous
        # session: retry with backoff like the C samples.
        last_rc = SUCCESS
        for attempt in range(1, CAMERA_START_ATTEMPTS + 1):
            handle = lib.xr_camera_provider_create(int(cam_vid), int(cam_pid))
            if not handle:
                raise RuntimeError("xr_camera_provider_create failed")
            self._callback = _camera_frame_callback_type()(self._on_frame)
            last_rc = lib.xr_camera_provider_start(handle, self._callback,
                                                   None)
            if last_rc == SUCCESS:
                self._handle = handle
                print(f"[camera] streaming (attempt {attempt})",
                      file=sys.stderr)
                return
            lib.xr_camera_provider_destroy(handle)
            self._callback = None
            print(f"[camera] start failed ({last_rc}), retrying "
                  f"({attempt}/{CAMERA_START_ATTEMPTS})...", file=sys.stderr)
            time.sleep(CAMERA_START_RETRY_S)
        raise RuntimeError(
            f"camera start failed after {CAMERA_START_ATTEMPTS} attempts "
            f"({last_rc})")

    def take_frame(self) -> tuple[bytes, int, int, int] | None:
        """Newest JPEG since the last take, or None. (bytes, w, h, seq)."""
        got = self.take_frame_with_ts()
        if got is None:
            return None
        data, w, h, seq, _ts_ns, _arrival = got
        return data, w, h, seq

    def take_frame_with_ts(
            self) -> tuple[bytes, int, int, int, int, float] | None:
        """Newest JPEG + device timestamp. (bytes, w, h, seq, ts_ns, arrival).

        arrival is time.monotonic() sampled in the SDK callback thread;
        pair it with ts_ns via tabletop.TimeSync to map device time into
        the monotonic domain.
        """
        with self._lock:
            if self._latest is None:
                return None
            out = (self._latest, self._width, self._height,
                   self._sequence, self._ts_ns, self._arrival_mono)
            self._latest = None
            return out

    def peek_frame(self) -> tuple[bytes, int, int, int, int, float] | None:
        """Newest JPEG + timestamps WITHOUT consuming (non-destructive)."""
        with self._lock:
            if self._latest is None:
                return None
            return (self._latest, self._width, self._height,
                    self._sequence, self._ts_ns, self._arrival_mono)

    @property
    def frames_received(self) -> int:
        with self._lock:
            return self._frames

    def close(self) -> None:
        if self._handle:
            try:
                self._lib.xr_camera_provider_stop(self._handle)
            finally:
                self._lib.xr_camera_provider_destroy(self._handle)
                self._handle = None
        self._callback = None

    def __enter__(self) -> "CameraStream":
        return self

    def __exit__(self, *exc) -> None:
        self.close()


def self_test(max_seconds: float = 12.0) -> int:
    """Hardware check without opening a window: find glasses, track, read poses."""
    import time

    print("VITURE SDK self-test", file=sys.stderr)
    try:
        lib_path = find_sdk_lib()
    except FileNotFoundError as exc:
        print(f"[self-test] {exc}", file=sys.stderr)
        return 1
    print(f"[self-test] lib: {lib_path}", file=sys.stderr)
    lib = load_lib(lib_path)
    try:
        pid = find_glasses_pid(lib)
    except RuntimeError as exc:
        print(f"[self-test] {exc}", file=sys.stderr)
        return 1
    print(f"[self-test] glasses product id: 0x{pid:04x}", file=sys.stderr)

    tracker = CarinaTracker(lib)
    try:
        tracker.start(pid)
    except RuntimeError as exc:
        print(f"[self-test] {exc}", file=sys.stderr)
        return 1
    print("[self-test] tracking started; waiting for VIO lock (lit area helps)...",
          file=sys.stderr)
    try:
        deadline = time.monotonic() + max_seconds
        locked = False
        n = 0
        misses = 0
        while time.monotonic() < deadline:
            # predict=0.0 until lock: a nonzero predict issued before the
            # first VIO sample blocks instead of returning.
            read = tracker.get_pose(
                predict=POSE_PREDICT_DEFAULT if locked else 0.0)
            if read is None:
                misses += 1
                time.sleep(0.25)
                continue
            pos, quat, status = read
            n += 1
            tag = "stable  " if status == POSE_STABLE else "unstable"
            print(f"[pose {n:03d}] {tag} "
                  f"pos [{pos[0]: .3f} {pos[1]: .3f} {pos[2]: .3f}] "
                  f"quat [{quat[0]:.3f} {quat[1]:.3f} {quat[2]:.3f} {quat[3]:.3f}]",
                  file=sys.stderr)
            if status == POSE_STABLE and not locked:
                tracker.recenter()
                locked = True
                print("[self-test] tracking locked; origin recentred", file=sys.stderr)
                # A few post-lock reads prove the steady-state path.
                for _ in range(5):
                    time.sleep(0.12)
                    reread = tracker.get_pose()
                    if reread is None:
                        misses += 1
                        continue
                    pos, quat, status = reread
                    n += 1
                    print(f"[pose {n:03d}] {'stable  ' if status == POSE_STABLE else 'unstable'} "
                          f"pos [{pos[0]: .3f} {pos[1]: .3f} {pos[2]: .3f}]",
                          file=sys.stderr)
                break
            time.sleep(0.25)
        print(f"[self-test] read {n} poses ({misses} transient misses); "
              f"{'LOCKED' if locked else 'no stable lock (need light + visual features)'}",
              file=sys.stderr)
        return 0
    finally:
        tracker.close()
