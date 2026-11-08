#!/usr/bin/env python3
"""Print-accurate ArUco table target + checkerboard for camera calibration.

ArUco mode (default): renders marker id 42 from DICT_6X6_250 at an exact
millimetre size on a white sheet, plus a JSON sidecar carrying the
physical parameters the tracker needs (dict, id, size) so the app never
hardcodes them in two places.

Checkerboard mode: renders an asymmetric-safe square checkerboard at an
exact square size for intrinsics calibration (see docs: capture ~20
views, run OpenCV calibrateCamera, save K/dist to table_calib.json).

Physical size is only as true as your printer: print at 100% (no
fit-to-page), then verify the outer ruler marks with calipers and edit
the JSON if you re-scale. A 1% scale error is a 1% table-size error.

Usage:
    uv run python scripts/make_table_target.py [--mode aruco|checkerboard]
        [--marker-size-mm 100] [--dict DICT_6X6_250] [--id 42]
        [--dpi 300] [--out build/table_target]
    # checkerboard extras:
        [--squares-w 9] [--squares-h 6] [--square-mm 25]

Output: <out>.png + <out>.json
"""

from __future__ import annotations

import argparse
import json
import math
import os
import sys


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__,
                                formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--mode", default="aruco", choices=("aruco", "checkerboard"))
    p.add_argument("--marker-size-mm", type=float, default=100.0)
    p.add_argument("--dict", dest="dict_name", default="DICT_6X6_250")
    p.add_argument("--id", dest="marker_id", type=int, default=42)
    p.add_argument("--dpi", type=float, default=300.0)
    p.add_argument("--out", default="build/table_target")
    p.add_argument("--squares-w", type=int, default=9)
    p.add_argument("--squares-h", type=int, default=6)
    p.add_argument("--square-mm", type=float, default=25.0)
    p.add_argument("--border-mm", type=float, default=15.0,
                   help="white margin around the pattern")
    return p.parse_args(argv)


def mm_to_px(mm, dpi):
    return max(1, int(round(mm / 25.4 * dpi)))


def main(argv=None) -> int:
    args = parse_args(argv)
    import cv2

    import numpy as np

    aruco = cv2.aruco
    os.makedirs(os.path.dirname(os.path.abspath(args.out)) or ".", exist_ok=True)

    if args.mode == "aruco":
        dict_id = getattr(aruco, args.dict_name, None)
        if dict_id is None:
            print(f"unknown aruco dict {args.dict_name!r}", file=sys.stderr)
            return 2
        dictionary = aruco.getPredefinedDictionary(dict_id)
        # Render the marker at high resolution, then place exact-size.
        marker_px = 1200
        marker = aruco.generateImageMarker(dictionary, args.marker_id, marker_px)
        body_px = mm_to_px(args.marker_size_mm, args.dpi)
        margin_px = mm_to_px(args.border_mm, args.dpi)
        marker_rs = cv2.resize(marker, (body_px, body_px),
                               interpolation=cv2.INTER_NEAREST)
        sheet = np.full((body_px + 2 * margin_px, body_px + 2 * margin_px),
                        255, dtype=np.uint8)
        sheet[margin_px:margin_px + body_px, margin_px:margin_px + body_px] = marker_rs
        # Ruler ticks every 10 mm along the top (verify print scale).
        tick_every = mm_to_px(10.0, args.dpi)
        for x in range(0, sheet.shape[1], tick_every):
            h = mm_to_px(5.0 if (x // tick_every) % 2 else 10.0, args.dpi)
            sheet[0:h, x:x + max(1, mm_to_px(0.5, args.dpi))] = 0
        ok = cv2.imwrite(args.out + ".png", sheet)
        sidecar = {
            "mode": "aruco",
            "dict": args.dict_name,
            "marker_id": args.marker_id,
            "marker_size_m": args.marker_size_mm / 1000.0,
            "marker_size_mm": args.marker_size_mm,
            "dpi": args.dpi,
            "png": os.path.basename(args.out + ".png"),
        }
    else:
        w, h, sq = args.squares_w, args.squares_h, args.square_mm
        sq_px = mm_to_px(sq, args.dpi)
        margin_px = mm_to_px(args.border_mm, args.dpi)
        sheet = np.full((h * sq_px + 2 * margin_px, w * sq_px + 2 * margin_px),
                        255, dtype=np.uint8)
        for iy in range(h):
            for ix in range(w):
                if (ix + iy) % 2 == 0:
                    sheet[margin_px + iy * sq_px:margin_px + (iy + 1) * sq_px,
                          margin_px + ix * sq_px:margin_px + (ix + 1) * sq_px] = 0
        ok = cv2.imwrite(args.out + ".png", sheet)
        sidecar = {
            "mode": "checkerboard",
            "squares_w": w,
            "squares_h": h,
            "square_size_m": sq / 1000.0,
            "square_mm": sq,
            "dpi": args.dpi,
            "png": os.path.basename(args.out + ".png"),
        }
    if not ok:
        print(f"failed to write {args.out}.png", file=sys.stderr)
        return 1
    with open(args.out + ".json", "w") as f:
        json.dump(sidecar, f, indent=2)
    print(f"wrote {args.out}.png + {args.out}.json")
    print("PRINT AT 100% SCALE, then verify size with a ruler.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
