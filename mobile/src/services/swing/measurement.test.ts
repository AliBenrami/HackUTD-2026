import { describe, expect, it } from 'vitest';
import { normalizeStored, parseMeasurement } from './measurement';

const payload = {
  fps: 30,
  width: 1080,
  height: 1920,
  poseModel: 'mediapipe-pose-landmarker-lite',
  phaseModel: 'kinematic-v1',
  clubModel: null,
  ballModel: null,
  disclaimer: 'This is an observation from the video, and there is no guaranteed certainty.',
  frames: [
    {
      j: Array.from({ length: 17 }, () => [10, 20]),
      s: null,
      c: null,
      h: [1, 2, 3, 4],
    },
  ],
  swings: [
    {
      id: 1,
      events: [
        {
          name: 'Top',
          label: 'Top',
          frame: 0,
          timeS: 0,
          score: 0.8,
          tentative: false,
          angles: { leftElbow: 140, rightElbow: 100, leftKnee: 160, rightKnee: 160, torsoTilt: 18 },
          clubs: { shaft: null, clubHead: null, hands: { confidence: 1, box: [1, 2, 3, 4] } },
          joints: [],
        },
      ],
    },
  ],
};

describe('swing measurement', () => {
  it('reads the analysis payload', () => {
    const measured = parseMeasurement(payload);
    expect(measured.swings[0]?.events[0]?.angles.leftElbow).toBe(140);
    expect(measured.frames[0]?.h).toEqual([1, 2, 3, 4]);
    expect(measured.clubModel).toBeNull();
    expect(measured.swings[0]?.ball).toEqual([]);
  });

  it('rejects a frame that is not a 17-point pose', () => {
    expect(() => parseMeasurement({ ...payload, frames: [{ j: [[1, 2]], s: null, c: null, h: null }] })).toThrow(/17/);
  });

  it('keeps saved results and drops a pending job', () => {
    const stored = normalizeStored({
      ready: { status: 'ready', measured: payload },
      waiting: { status: 'pending' },
      broken: { status: 'ready', measured: { fps: 30 } },
      failed: { status: 'failed', message: 'The video could not be opened.' },
    });
    expect(stored.ready?.status).toBe('ready');
    expect(stored.waiting).toBeUndefined();
    expect(stored.broken).toBeUndefined();
    expect(stored.failed).toEqual({ status: 'failed', message: 'The video could not be opened.' });
  });
});
