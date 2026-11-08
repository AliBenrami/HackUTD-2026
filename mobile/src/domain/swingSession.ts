/**
 * A swing with an impact cue is a shot only when the ball actually leaves.
 * The detector already drops a ball that stays on the tee, so an empty trace
 * is a practice swing. A short trace still has to move before it counts.
 */

export const CHALLENGE_SHOTS = 5;

/** Pixels of travel, in the video frame, required before a trace is a shot. */
export const BALL_MOVE_PX = 12;

/** Seconds of address-to-impact difference weighed like degrees, so timing can decide a pair. */
const TIMING_WEIGHT = 50;

const SETUP_KEYS = ['leftElbow', 'rightElbow', 'leftKnee', 'rightKnee', 'torsoTilt'] as const;

export type SwingRole = 'shot' | 'practice';

export type SetupKey = (typeof SETUP_KEYS)[number];

export type SetupAngles = Record<SetupKey, number | null>;

export type TimedSwing = {
  id: string;
  address: SetupAngles;
  /** Seconds from the address cue to the impact cue. */
  addressToImpactS: number | null;
};

export type MetricSpread = {
  low: number;
  high: number;
  spread: number;
};

export type SwingPair = {
  aId: string;
  bId: string;
  setupGap: number | null;
  timingGap: number | null;
};

export type ChallengeReport = {
  counted: number;
  limit: number;
  timing: MetricSpread | null;
  setupSpread: number | null;
  pair: SwingPair | null;
};

type Cue = {
  name: string;
  timeS: number;
  angles?: Partial<SetupAngles>;
};

type BallPoint = {
  x: number;
  y: number;
};

export function classifySwing(swing: { events: readonly { name: string }[]; ball?: readonly BallPoint[] }): SwingRole {
  if (!swing.events.some((event) => event.name === 'Impact')) return 'practice';
  const ball = swing.ball ?? [];
  if (ball.length < 2) return 'practice';
  const start = ball[0];
  const end = ball[ball.length - 1];
  const moved = Math.hypot(end.x - start.x, end.y - start.y);
  return moved >= BALL_MOVE_PX ? 'shot' : 'practice';
}

export function roleLabel(role: SwingRole): string {
  return role === 'shot' ? 'Shot' : 'Practice';
}

export function roleNote(role: SwingRole): string {
  return role === 'shot'
    ? 'The ball leaves at the impact cue, so this shot is saved.'
    : 'The ball stays put through the impact cue. This practice swing does not count.';
}

export function emptySetup(): SetupAngles {
  return {
    leftElbow: null,
    rightElbow: null,
    leftKnee: null,
    rightKnee: null,
    torsoTilt: null,
  };
}

export function timingOf(events: readonly Cue[]): { address: SetupAngles; addressToImpactS: number | null } {
  const address = events.find((event) => event.name === 'Address');
  const impact = events.find((event) => event.name === 'Impact');
  const angles = emptySetup();
  if (address?.angles) {
    for (const key of SETUP_KEYS) {
      const value = address.angles[key];
      angles[key] = typeof value === 'number' && Number.isFinite(value) ? value : null;
    }
  }
  const addressToImpactS =
    address && impact && impact.timeS >= address.timeS ? impact.timeS - address.timeS : null;
  return { address: angles, addressToImpactS };
}

export function replayWindow(events: readonly { name: string; timeS: number }[]): { start: number; end: number } | null {
  const address = events.find((event) => event.name === 'Address');
  const impact = events.find((event) => event.name === 'Impact');
  if (!address || !impact || impact.timeS < address.timeS) return null;
  return { start: address.timeS, end: impact.timeS + 0.4 };
}

/** Keep saved shots in their current order, drop ones that no longer exist, then fill up to five. */
export function appendShotIds(current: readonly string[], available: readonly string[], limit = CHALLENGE_SHOTS): string[] {
  const known = new Set(available);
  const live = current.filter((id) => known.has(id));
  const extras = available.filter((id) => !live.includes(id));
  return [...live, ...extras].slice(0, limit);
}

export function setupGap(a: SetupAngles, b: SetupAngles): number | null {
  const gaps: number[] = [];
  for (const key of SETUP_KEYS) {
    const left = a[key];
    const right = b[key];
    if (left == null || right == null) continue;
    gaps.push(Math.abs(left - right));
  }
  if (gaps.length === 0) return null;
  return gaps.reduce((total, gap) => total + gap, 0) / gaps.length;
}

export function challengeReport(shots: readonly TimedSwing[]): ChallengeReport {
  const timingValues = shots
    .map((shot) => shot.addressToImpactS)
    .filter((value): value is number => value != null && Number.isFinite(value));
  const timing =
    timingValues.length < 2
      ? null
      : {
          low: Math.min(...timingValues),
          high: Math.max(...timingValues),
          spread: Math.max(...timingValues) - Math.min(...timingValues),
        };

  const angleSpreads: number[] = [];
  for (const key of SETUP_KEYS) {
    const values = shots
      .map((shot) => shot.address[key])
      .filter((value): value is number => value != null && Number.isFinite(value));
    if (values.length < 2) continue;
    angleSpreads.push(Math.max(...values) - Math.min(...values));
  }
  const setupSpread =
    angleSpreads.length === 0 ? null : angleSpreads.reduce((total, value) => total + value, 0) / angleSpreads.length;

  let pair: SwingPair | null = null;
  for (let left = 0; left < shots.length; left += 1) {
    for (let right = left + 1; right < shots.length; right += 1) {
      const setup = setupGap(shots[left].address, shots[right].address);
      const leftTime = shots[left].addressToImpactS;
      const rightTime = shots[right].addressToImpactS;
      const timingGap = leftTime == null || rightTime == null ? null : Math.abs(leftTime - rightTime);
      const score = (setup ?? 0) + (timingGap ?? 0) * TIMING_WEIGHT;
      const best = pair == null ? -1 : (pair.setupGap ?? 0) + (pair.timingGap ?? 0) * TIMING_WEIGHT;
      if (pair == null || score > best) {
        pair = { aId: shots[left].id, bId: shots[right].id, setupGap: setup, timingGap };
      }
    }
  }

  return {
    counted: shots.length,
    limit: CHALLENGE_SHOTS,
    timing,
    setupSpread,
    pair,
  };
}
