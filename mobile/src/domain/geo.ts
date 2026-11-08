export type MapPoint = { lng: number; lat: number };

export type PlanePoint = { x: number; y: number };

export type ShotSource = 'tap' | 'phone' | 'generic';

export type Shot = {
  n: number;
  lng: number;
  lat: number;
  source: ShotSource;
};

const YARDS_PER_DEG_NORTH = 110540 * 1.0936133;
const YARDS_PER_DEG_EAST = 111320 * 1.0936133;

export function yardsBetween(a: MapPoint, b: MapPoint): number {
  const radius = 6371000 * 1.0936133;
  const phi1 = (a.lat * Math.PI) / 180;
  const phi2 = (b.lat * Math.PI) / 180;
  const dPhi = ((b.lat - a.lat) * Math.PI) / 180;
  const dLng = ((b.lng - a.lng) * Math.PI) / 180;
  const h = Math.sin(dPhi / 2) ** 2 + Math.cos(phi1) * Math.cos(phi2) * Math.sin(dLng / 2) ** 2;
  return 2 * radius * Math.asin(Math.min(1, Math.sqrt(h)));
}

export function toPlane(tee: MapPoint, green: MapPoint, point: MapPoint): PlanePoint {
  const east = (point.lng - tee.lng) * Math.cos((tee.lat * Math.PI) / 180) * YARDS_PER_DEG_EAST;
  const north = (point.lat - tee.lat) * YARDS_PER_DEG_NORTH;
  const greenEast = (green.lng - tee.lng) * Math.cos((tee.lat * Math.PI) / 180) * YARDS_PER_DEG_EAST;
  const greenNorth = (green.lat - tee.lat) * YARDS_PER_DEG_NORTH;
  const length = Math.hypot(greenEast, greenNorth) || 1;
  const alongEast = greenEast / length;
  const alongNorth = greenNorth / length;
  return {
    x: east * alongNorth - north * alongEast,
    y: east * alongEast + north * alongNorth,
  };
}

export function fromPlane(tee: MapPoint, green: MapPoint, point: PlanePoint): MapPoint {
  const greenEast = (green.lng - tee.lng) * Math.cos((tee.lat * Math.PI) / 180) * YARDS_PER_DEG_EAST;
  const greenNorth = (green.lat - tee.lat) * YARDS_PER_DEG_NORTH;
  const length = Math.hypot(greenEast, greenNorth) || 1;
  const alongEast = greenEast / length;
  const alongNorth = greenNorth / length;
  const east = point.x * alongNorth + point.y * alongEast;
  const north = -point.x * alongEast + point.y * alongNorth;
  return {
    lng: tee.lng + east / (Math.cos((tee.lat * Math.PI) / 180) * YARDS_PER_DEG_EAST),
    lat: tee.lat + north / YARDS_PER_DEG_NORTH,
  };
}

export function holeBearing(tee: MapPoint, green: MapPoint): number {
  const east = (green.lng - tee.lng) * Math.cos((tee.lat * Math.PI) / 180);
  const north = green.lat - tee.lat;
  const degrees = (Math.atan2(east, north) * 180) / Math.PI;
  return (degrees + 360) % 360;
}

export type MapRegion = {
  latitude: number;
  longitude: number;
  latitudeDelta: number;
  longitudeDelta: number;
};

export function regionFor(points: MapPoint[]): MapRegion {
  const finite = points.filter((point) => Number.isFinite(point.lng) && Number.isFinite(point.lat));
  if (finite.length === 0) {
    return { latitude: 0, longitude: 0, latitudeDelta: 0.02, longitudeDelta: 0.02 };
  }
  const lats = finite.map((point) => point.lat);
  const lngs = finite.map((point) => point.lng);
  const minLat = Math.min(...lats);
  const maxLat = Math.max(...lats);
  const minLng = Math.min(...lngs);
  const maxLng = Math.max(...lngs);
  const latitude = (minLat + maxLat) / 2;
  const longitude = (minLng + maxLng) / 2;
  const latSpan = Math.max(maxLat - minLat, 0.0022);
  const lngSpan = Math.max(maxLng - minLng, 0.0022);
  const cos = Math.cos((latitude * Math.PI) / 180) || 1;
  let latitudeDelta = latSpan * 1.7;
  let longitudeDelta = lngSpan * 1.7;
  const lngAsLat = longitudeDelta * cos;
  if (lngAsLat < latitudeDelta * 0.62) longitudeDelta = (latitudeDelta * 0.62) / cos;
  if (latitudeDelta < lngAsLat * 0.72) latitudeDelta = lngAsLat * 0.72;
  return { latitude, longitude, latitudeDelta, longitudeDelta };
}

export function shotPath(tee: MapPoint, shots: MapPoint[]): MapPoint[] {
  const marks = shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
  return marks.length ? [tee, ...marks] : [];
}

export type HoleFrame = {
  viewBox: string;
  width: number;
  height: number;
  toView: (point: MapPoint) => PlanePoint;
  fromView: (x: number, y: number) => MapPoint;
};

export function frameHole(tee: MapPoint, green: MapPoint, points: MapPoint[], aspect = 2 / 3): HoleFrame {
  const height = 160;
  const width = Math.max(height * (2 / 3), height * aspect);
  const pad = 10;
  const plane = points.map((point) => toPlane(tee, green, point));
  const xs = plane.map((point) => point.x);
  const ys = plane.map((point) => point.y);
  const minX = Math.min(...xs, -12);
  const maxX = Math.max(...xs, 12);
  const minY = Math.min(...ys, -12);
  const maxY = Math.max(...ys, 12);
  const spanX = Math.max(maxX - minX, 8);
  const spanY = Math.max(maxY - minY, 8);
  const innerW = width - pad * 2;
  const innerH = height - pad * 2;
  const uniform = Math.min(innerW / spanX, innerH / spanY);
  const scaleY = uniform;
  const scaleX = Math.min(innerW * 0.46, spanX * uniform * 3.5) / spanX;
  const offsetX = pad + (innerW - spanX * scaleX) / 2;
  const offsetY = pad + (innerH - spanY * scaleY) / 2;

  function toView(point: MapPoint): PlanePoint {
    const placed = toPlane(tee, green, point);
    return {
      x: offsetX + (placed.x - minX) * scaleX,
      y: height - offsetY - (placed.y - minY) * scaleY,
    };
  }

  function fromView(x: number, y: number): MapPoint {
    return fromPlane(tee, green, {
      x: minX + (x - offsetX) / scaleX,
      y: minY + (height - offsetY - y) / scaleY,
    });
  }

  return { viewBox: `0 0 ${width} ${height}`, width, height, toView, fromView };
}

function closestOnSegment(origin: MapPoint, end: MapPoint, point: MapPoint): { point: MapPoint; yards: number; along: number } {
  const length = yardsBetween(origin, end);
  if (length < 0.5) return { point: origin, yards: yardsBetween(origin, point), along: 0 };
  const start = toPlane(origin, end, origin);
  const target = toPlane(origin, end, point);
  const along = Math.max(0, Math.min(length, target.y));
  const snapped = fromPlane(origin, end, { x: 0, y: along });
  return { point: snapped, yards: Math.hypot(target.x, target.y - along), along };
}

export function distanceToPath(path: MapPoint[], point: MapPoint): number {
  if (path.length === 0) return Infinity;
  if (path.length === 1) return yardsBetween(path[0], point);
  let best = Infinity;
  for (let index = 0; index < path.length - 1; index += 1) {
    best = Math.min(best, closestOnSegment(path[index], path[index + 1], point).yards);
  }
  return best;
}

export function pointAlong(path: MapPoint[], yards: number): MapPoint {
  if (path.length === 0) throw new Error('A hole needs a path.');
  if (path.length === 1 || yards <= 0) return path[0];
  let left = yards;
  for (let index = 0; index < path.length - 1; index += 1) {
    const span = yardsBetween(path[index], path[index + 1]);
    if (left <= span || index === path.length - 2) {
      const t = span === 0 ? 0 : Math.max(0, Math.min(1, left / span));
      return {
        lng: path[index].lng + (path[index + 1].lng - path[index].lng) * t,
        lat: path[index].lat + (path[index + 1].lat - path[index].lat) * t,
      };
    }
    left -= span;
  }
  return path[path.length - 1];
}

export function pathLength(path: MapPoint[]): number {
  let total = 0;
  for (let index = 0; index < path.length - 1; index += 1) total += yardsBetween(path[index], path[index + 1]);
  return total;
}

export type LandingGuess = {
  point: MapPoint;
  source: 'phone' | 'generic';
  note: string;
};

const PHONE_CORRIDOR_YARDS = 90;

export function guessLanding(input: {
  path: MapPoint[];
  green: MapPoint;
  shots: MapPoint[];
  phone: MapPoint | null;
  carryYards: number;
}): LandingGuess {
  const path = input.path.length >= 2 ? input.path : [input.path[0] ?? input.green, input.green];
  const phone = input.phone;
  if (phone && distanceToPath([...path, input.green], phone) <= PHONE_CORRIDOR_YARDS) {
    return {
      point: phone,
      source: 'phone',
      note: 'This is where your phone is. The ball is usually at your feet. Move the mark if the ball is somewhere else.',
    };
  }
  const origin = input.shots.length > 0 ? input.shots[input.shots.length - 1] : path[0];
  const remaining = yardsBetween(origin, input.green);
  const point =
    remaining <= 30
      ? input.green
      : pointAlong(pathFrom(path, origin), Math.min(input.carryYards, remaining * 0.85));
  const note = phone
    ? 'Your phone is away from this hole, so this is a generic spot along the hole.'
    : 'Location is off, so this is a generic spot along the hole.';
  return { point, source: 'generic', note };
}

function pathFrom(path: MapPoint[], origin: MapPoint): MapPoint[] {
  let bestIndex = 0;
  let best = Infinity;
  for (let index = 0; index < path.length; index += 1) {
    const gap = yardsBetween(path[index], origin);
    if (gap < best) {
      best = gap;
      bestIndex = index;
    }
  }
  return [origin, ...path.slice(bestIndex + 1)];
}

export function placeShot(shots: Shot[], point: MapPoint, source: ShotSource): Shot[] {
  if (!Number.isFinite(point.lng) || !Number.isFinite(point.lat)) return shots;
  const last = shots[shots.length - 1];
  const correcting = source === 'tap' && (last?.source === 'phone' || last?.source === 'generic');
  const next = correcting ? shots.slice(0, -1) : shots;
  return [...next, { n: next.length + 1, lng: point.lng, lat: point.lat, source }];
}
