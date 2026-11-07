import AsyncStorage from '@react-native-async-storage/async-storage';
import type { BallSample, SwingCue, ReviewedSwing } from '../../data/swingReview';

const STORAGE_KEY = 'golfar.swingMeasurements.v1';

export const SWING_PHASE_MODEL = 'kinematic-v2';

export type MeasuredFrame = {
  j: ([number, number] | null)[];
  s: [number, number, number, number] | null;
  c: [number, number, number, number] | null;
  h: [number, number, number, number] | null;
};

export type SwingMeasurement = {
  fps: number;
  width: number;
  height: number;
  poseModel: string;
  phaseModel: string;
  clubModel: string | null;
  ballModel: string | null;
  disclaimer: string;
  frames: MeasuredFrame[];
  swings: ReviewedSwing[];
};

export type MeasurementRecord =
  | { status: 'pending' }
  | { status: 'failed'; message: string }
  | { status: 'ready'; measured: SwingMeasurement };

export function swingApiConfigured() {
  return Boolean(process.env.EXPO_PUBLIC_SWING_API_URL);
}

export async function analyzeSwingVideo(videoUri: string): Promise<SwingMeasurement> {
  const base = process.env.EXPO_PUBLIC_SWING_API_URL?.replace(/\/$/, '');
  if (!base) {
    throw new Error('Set EXPO_PUBLIC_SWING_API_URL to the analysis server.');
  }
  const body = new FormData();
  if (/^https?:\/\//i.test(videoUri)) {
    body.append('url', videoUri);
  } else {
    body.append('video', {
      uri: videoUri,
      name: 'swing.mp4',
      type: 'video/mp4',
    } as unknown as Blob);
  }
  const response = await fetch(`${base}/analyze`, { method: 'POST', body });
  if (!response.ok) {
    throw new Error(await errorMessage(response));
  }
  return parseMeasurement(await response.json());
}

export function parseMeasurement(value: unknown): SwingMeasurement {
  const body = requireRecord(value, 'The analysis response was incomplete.');
  const frames = asArray(body.frames, 'frames').map(parseFrame);
  if (frames.length === 0) {
    throw new Error('The analysis response had no frames.');
  }
  return {
    fps: positive(body.fps, 'fps'),
    width: positive(body.width, 'width'),
    height: positive(body.height, 'height'),
    poseModel: asString(body.poseModel, 'poseModel'),
    phaseModel: asString(body.phaseModel, 'phaseModel'),
    clubModel: body.clubModel == null ? null : asString(body.clubModel, 'clubModel'),
    ballModel: body.ballModel == null ? null : asString(body.ballModel, 'ballModel'),
    disclaimer: asString(body.disclaimer, 'disclaimer'),
    frames,
    swings: asArray(body.swings, 'swings').map(parseSwing),
  };
}

export function normalizeStored(value: unknown): Record<string, MeasurementRecord> {
  if (!value || typeof value !== 'object') return {};
  const records: Record<string, MeasurementRecord> = {};
  for (const [id, entry] of Object.entries(value as Record<string, unknown>)) {
    const record = optionalRecord(entry);
    if (!record) continue;
    if (record.status === 'failed' && typeof record.message === 'string') {
      records[id] = { status: 'failed', message: record.message };
    } else if (record.status === 'ready') {
      try {
        records[id] = { status: 'ready', measured: parseMeasurement(record.measured) };
      } catch {
        // A stored result from an older response is ignored.
      }
    }
  }
  return records;
}

export async function loadMeasurements() {
  const raw = await AsyncStorage.getItem(STORAGE_KEY);
  if (!raw) return {};
  try {
    return normalizeStored(JSON.parse(raw));
  } catch {
    return {};
  }
}

export async function saveMeasurements(records: Record<string, MeasurementRecord>) {
  const stored: Record<string, MeasurementRecord> = {};
  for (const [id, record] of Object.entries(records)) {
    if (record.status !== 'pending') stored[id] = record;
  }
  await AsyncStorage.setItem(STORAGE_KEY, JSON.stringify(stored));
}

async function errorMessage(response: Response) {
  const text = await response.text();
  try {
    const body = JSON.parse(text) as { detail?: unknown };
    if (typeof body.detail === 'string' && body.detail) return body.detail;
  } catch {
    // The server returned plain text.
  }
  return text || `Analysis failed (${response.status}).`;
}

function parseSwing(value: unknown, index: number): ReviewedSwing {
  const swing = requireRecord(value, 'A swing in the analysis response was incomplete.');
  const events = asArray(swing.events, 'events').map(parseCue);
  const ball = Array.isArray(swing.ball) ? swing.ball.map(parseBall) : [];
  return {
    id: typeof swing.id === 'number' ? swing.id : index + 1,
    events,
    ball,
  };
}

function parseBall(value: unknown): BallSample {
  const sample = requireRecord(value, 'A ball sample was incomplete.');
  return {
    frame: asNumber(sample.frame, 'frame'),
    timeS: asNumber(sample.timeS, 'timeS'),
    x: asNumber(sample.x, 'x'),
    y: asNumber(sample.y, 'y'),
    confidence: asNumber(sample.confidence, 'confidence'),
  };
}

function parseCue(value: unknown): SwingCue {
  const cue = requireRecord(value, 'A phase cue was incomplete.');
  const angles = requireRecord(cue.angles, 'A phase cue was missing angles.');
  const clubs = optionalRecord(cue.clubs) ?? {};
  return {
    name: asString(cue.name, 'name'),
    label: asString(cue.label, 'label'),
    frame: asNumber(cue.frame, 'frame'),
    timeS: asNumber(cue.timeS, 'timeS'),
    score: asNumber(cue.score, 'score'),
    tentative: cue.tentative === true,
    angles: {
      leftElbow: optionalNumber(angles.leftElbow),
      rightElbow: optionalNumber(angles.rightElbow),
      leftKnee: optionalNumber(angles.leftKnee),
      rightKnee: optionalNumber(angles.rightKnee),
      torsoTilt: optionalNumber(angles.torsoTilt),
    },
    clubs: {
      shaft: parseClub(clubs.shaft),
      clubHead: parseClub(clubs.clubHead),
      hands: parseClub(clubs.hands),
    },
    joints: Array.isArray(cue.joints) ? cue.joints.filter(isJoint) : [],
  };
}

function parseFrame(value: unknown): MeasuredFrame {
  const frame = requireRecord(value, 'A pose frame was incomplete.');
  const joints = asArray(frame.j, 'joints');
  if (joints.length !== 17) throw new Error('A pose frame did not have 17 joints.');
  return {
    j: joints.map(parsePoint),
    s: parseBox(frame.s),
    c: parseBox(frame.c),
    h: parseBox(frame.h),
  };
}

function parseClub(value: unknown) {
  const club = optionalRecord(value);
  if (!club) return null;
  const box = parseBox(club.box);
  if (!box || typeof club.confidence !== 'number') return null;
  return { confidence: club.confidence, box: box as [number, number, number, number] };
}

function parsePoint(value: unknown): [number, number] | null {
  if (value == null) return null;
  if (!Array.isArray(value) || value.length < 2) return null;
  if (typeof value[0] !== 'number' || typeof value[1] !== 'number') return null;
  return [value[0], value[1]];
}

function parseBox(value: unknown): [number, number, number, number] | null {
  if (!Array.isArray(value) || value.length !== 4) return null;
  if (value.some((item) => typeof item !== 'number')) return null;
  return [value[0], value[1], value[2], value[3]];
}

function isJoint(value: unknown): value is [number, number, number] {
  return Array.isArray(value) && value.length >= 3 && value.every((item) => typeof item === 'number');
}

function requireRecord(value: unknown, message: string) {
  const record = optionalRecord(value);
  if (!record) throw new Error(message);
  return record;
}

function optionalRecord(value: unknown) {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return null;
  return value as Record<string, unknown>;
}

function asArray(value: unknown, name: string) {
  if (!Array.isArray(value)) throw new Error(`The analysis response was missing ${name}.`);
  return value;
}

function asString(value: unknown, name: string) {
  if (typeof value !== 'string' || !value) throw new Error(`The analysis response was missing ${name}.`);
  return value;
}

function asNumber(value: unknown, name: string) {
  if (typeof value !== 'number' || !Number.isFinite(value)) throw new Error(`The analysis response was missing ${name}.`);
  return value;
}

function positive(value: unknown, name: string) {
  const number = asNumber(value, name);
  if (number <= 0) throw new Error(`The analysis response was missing ${name}.`);
  return number;
}

function optionalNumber(value: unknown) {
  if (value == null) return null;
  return typeof value === 'number' && Number.isFinite(value) ? value : null;
}
