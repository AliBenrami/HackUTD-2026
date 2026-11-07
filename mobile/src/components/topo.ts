export type TopoContour = {
  d: string;
  color: string;
  width: number;
};

export type TopoModel = {
  viewBox: string;
  fairway: string;
  contours: TopoContour[];
  green: { cx: number; cy: number };
  tee: { cx: number; cy: number };
  bunker: { cx: number; cy: number };
};

const COLS = 46;
const ROWS = 30;
const VIEW_W = 100;
const VIEW_H = 66;

type Point = { x: number; y: number };
type Segment = { a: Point; b: Point };

export function seedFromString(input: string): number {
  let hash = 2166136261;
  for (let index = 0; index < input.length; index += 1) {
    hash ^= input.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0) % 9973 || 1;
}

function fade(t: number): number {
  return t * t * (3 - 2 * t);
}

function hash2(ix: number, iy: number, seed: number): number {
  const value = Math.sin(ix * 127.1 + iy * 311.7 + seed * 74.7) * 43758.5453;
  return value - Math.floor(value);
}

function valueNoise(x: number, y: number, seed: number): number {
  const x0 = Math.floor(x);
  const y0 = Math.floor(y);
  const tx = fade(x - x0);
  const ty = fade(y - y0);
  const v00 = hash2(x0, y0, seed);
  const v10 = hash2(x0 + 1, y0, seed);
  const v01 = hash2(x0, y0 + 1, seed);
  const v11 = hash2(x0 + 1, y0 + 1, seed);
  const top = v00 + (v10 - v00) * tx;
  const bottom = v01 + (v11 - v01) * tx;
  return top + (bottom - top) * ty;
}

function fbm(x: number, y: number, seed: number): number {
  return (
    0.56 * valueNoise(x, y, seed) +
    0.28 * valueNoise(x * 2.05, y * 2.05, seed + 17) +
    0.16 * valueNoise(x * 4.1, y * 4.1, seed + 43)
  );
}

export function fairwayPoint(t: number, seed: number): Point {
  const bend = ((seed % 100) / 100 - 0.5) * 0.36;
  const sway = Math.sin(t * Math.PI) * bend;
  return {
    x: 0.15 + t * 0.68,
    y: Math.min(0.9, Math.max(0.1, 0.78 - t * 0.56 + sway)),
  };
}

function heightAt(nx: number, ny: number, seed: number): number {
  let height = fbm(nx * 3.1 + 0.2, ny * 3.1 + 0.4, seed);
  let minDistance = 1;
  let nearestT = 0;
  for (let step = 0; step <= 24; step += 1) {
    const t = step / 24;
    const point = fairwayPoint(t, seed);
    const distance = Math.hypot(nx - point.x, (ny - point.y) * 1.15);
    if (distance < minDistance) {
      minDistance = distance;
      nearestT = t;
    }
  }
  const width = 0.07 + nearestT * 0.018;
  const corridor = Math.exp(-(minDistance * minDistance) / (2 * width * width));
  height = height * (1 - 0.75 * corridor) + 0.36 * corridor;

  const green = fairwayPoint(0.97, seed);
  const greenDistance = Math.hypot(nx - green.x, ny - green.y);
  height += Math.exp(-(greenDistance * greenDistance) / (2 * 0.028 * 0.028)) * 0.2;

  const bunker = { x: green.x - 0.09, y: Math.min(0.92, green.y + 0.07) };
  const bunkerDistance = Math.hypot(nx - bunker.x, ny - bunker.y);
  height -= Math.exp(-(bunkerDistance * bunkerDistance) / (2 * 0.016 * 0.016)) * 0.22;

  return Math.min(1, Math.max(0, height));
}

function interpolate(a: number, b: number, level: number): number {
  const delta = b - a;
  if (Math.abs(delta) < 1e-6) return 0.5;
  return Math.min(1, Math.max(0, (level - a) / delta));
}

function edgePoint(edge: number, x: number, y: number, t: number): Point {
  if (edge === 0) return { x: x + t, y };
  if (edge === 1) return { x: x + 1, y: y + t };
  if (edge === 2) return { x: x + 1 - t, y: y + 1 };
  return { x, y: y + 1 - t };
}

const CASES: number[][] = [
  [],
  [3, 0],
  [0, 1],
  [3, 1],
  [1, 2],
  [3, 0, 1, 2],
  [0, 2],
  [3, 2],
  [2, 3],
  [0, 2],
  [0, 1, 2, 3],
  [1, 2],
  [1, 3],
  [0, 1],
  [0, 3],
  [],
];

function segmentsForLevel(field: number[][], level: number): Segment[] {
  const segments: Segment[] = [];
  for (let y = 0; y < ROWS - 1; y += 1) {
    for (let x = 0; x < COLS - 1; x += 1) {
      const tl = field[y][x];
      const tr = field[y][x + 1];
      const br = field[y + 1][x + 1];
      const bl = field[y + 1][x];
      const index =
        (tl >= level ? 1 : 0) |
        (tr >= level ? 2 : 0) |
        (br >= level ? 4 : 0) |
        (bl >= level ? 8 : 0);
      const edges = CASES[index];
      const values = [tl, tr, br, bl];
      const ts = [
        interpolate(values[0], values[1], level),
        interpolate(values[1], values[2], level),
        interpolate(values[2], values[3], level),
        interpolate(values[3], values[0], level),
      ];
      for (let cursor = 0; cursor < edges.length; cursor += 2) {
        segments.push({
          a: edgePoint(edges[cursor], x, y, ts[edges[cursor]]),
          b: edgePoint(edges[cursor + 1], x, y, ts[edges[cursor + 1]]),
        });
      }
    }
  }
  return segments;
}

function near(a: Point, b: Point): boolean {
  return Math.abs(a.x - b.x) < 0.02 && Math.abs(a.y - b.y) < 0.02;
}

function chain(segments: Segment[]): Point[][] {
  const unused = segments.slice();
  const lines: Point[][] = [];
  while (unused.length > 0) {
    const first = unused.pop();
    if (!first) break;
    const line = [first.a, first.b];
    let extended = true;
    while (extended) {
      extended = false;
      const start = line[0];
      const end = line[line.length - 1];
      for (let index = unused.length - 1; index >= 0; index -= 1) {
        const segment = unused[index];
        if (near(segment.a, end)) {
          line.push(segment.b);
        } else if (near(segment.b, end)) {
          line.push(segment.a);
        } else if (near(segment.a, start)) {
          line.unshift(segment.b);
        } else if (near(segment.b, start)) {
          line.unshift(segment.a);
        } else {
          continue;
        }
        unused.splice(index, 1);
        extended = true;
        break;
      }
    }
    if (line.length > 3) lines.push(line);
  }
  return lines;
}

function scale(point: Point): Point {
  return {
    x: (point.x / (COLS - 1)) * VIEW_W,
    y: (point.y / (ROWS - 1)) * VIEW_H,
  };
}

function toPath(line: Point[]): string {
  return line
    .map((point, index) => {
      const scaled = scale(point);
      const command = index === 0 ? 'M' : 'L';
      return `${command}${scaled.x.toFixed(1)} ${scaled.y.toFixed(1)}`;
    })
    .join(' ');
}

function contourColor(level: number): { color: string; width: number } {
  if (level >= 0.78) return { color: 'rgba(232,121,249,0.85)', width: 0.7 };
  if (level >= 0.64) return { color: 'rgba(0,217,232,0.8)', width: 0.65 };
  if (level >= 0.5) return { color: 'rgba(0,217,232,0.45)', width: 0.5 };
  return { color: 'rgba(139,92,246,0.5)', width: 0.45 };
}

function polyline(points: Point[]): string {
  return points
    .map((point, index) => {
      const command = index === 0 ? 'M' : 'L';
      return `${command}${point.x.toFixed(1)} ${point.y.toFixed(1)}`;
    })
    .join(' ');
}

export function buildTopo(seedKey: string): TopoModel {
  const seed = seedFromString(seedKey);
  const field: number[][] = [];
  for (let y = 0; y < ROWS; y += 1) {
    const row: number[] = [];
    for (let x = 0; x < COLS; x += 1) {
      row.push(heightAt(x / (COLS - 1), y / (ROWS - 1), seed));
    }
    field.push(row);
  }

  const levels = [0.34, 0.42, 0.5, 0.58, 0.66, 0.74, 0.82];
  const contours: TopoContour[] = [];
  for (const level of levels) {
    const style = contourColor(level);
    for (const line of chain(segmentsForLevel(field, level))) {
      contours.push({ d: toPath(line), ...style });
    }
  }

  const center = Array.from({ length: 18 }, (_, index) => {
    const point = fairwayPoint(index / 17, seed);
    return scale({ x: point.x * (COLS - 1), y: point.y * (ROWS - 1) });
  });
  const greenPoint = fairwayPoint(0.97, seed);
  const teePoint = fairwayPoint(0.04, seed);
  const green = scale({ x: greenPoint.x * (COLS - 1), y: greenPoint.y * (ROWS - 1) });
  const tee = scale({ x: teePoint.x * (COLS - 1), y: teePoint.y * (ROWS - 1) });
  const bunker = {
    cx: Math.max(4, green.x - 7),
    cy: Math.min(VIEW_H - 4, green.y + 5),
  };

  return {
    viewBox: `0 0 ${VIEW_W} ${VIEW_H}`,
    fairway: polyline(center),
    contours,
    green: { cx: green.x, cy: green.y },
    tee: { cx: tee.x, cy: tee.y },
    bunker,
  };
}
