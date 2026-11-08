"""Export Python v5 course fixtures for the Unity parity check."""

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ar" / "src"))
from course_generator import DIFFICULTIES, generate, height_and_slope, terrain_normal


def fixture(seed, difficulty, **options):
    inputs = dict(seed=seed, width_m=.60, length_m=.40, difficulty=difficulty,
                  decoration_count=4)
    inputs.update(options)
    layout = generate(**inputs)
    terrain = layout["terrain"]
    points = [layout["start"], layout["hole"], layout["route"][len(layout["route"]) // 2]]
    points += [[terrain["width_m"] * x, terrain["length_m"] * y]
               for x, y in [(-.45, -.40), (-.32, .33), (.31, -.35), (.43, .42)]]
    samples = []
    for x, y in points:
        height, slope = height_and_slope(layout, x, y, .002 / layout["course_scale"])
        samples.append(dict(x=x, y=y, height=height, slope=slope, normal=terrain_normal(layout, x, y)))
    return dict(inputs=inputs, layout=layout, samples=samples)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("output", type=Path)
    args = parser.parse_args()
    fixtures = [fixture(seed, mode) for mode in DIFFICULTIES for seed in range(100)]
    fixtures.extend([
        fixture(4242, "medium", decoration_count=6),
        fixture(9, "medium", course_scale=.40, grid_size=129, decoration_count=7),
        fixture(18, "easy", ball_diameter_m=.043, grid_size=65, edge_margin_m=.05),
        fixture(77, "medium", reserved=[(.22, .12, .025, .025)], course_scale=.20),
        fixture(-2147483648, "easy", decoration_count=0),
        fixture(2147483647, "hard", grid_size=129),
    ])
    args.output.write_text(json.dumps(fixtures, separators=(",", ":")) + "\n")
    print(f"Wrote {len(fixtures)} reference courses to {args.output}")


if __name__ == "__main__":
    main()
