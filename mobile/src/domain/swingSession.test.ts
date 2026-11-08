import { describe, expect, it } from 'vitest';
import { ballTraces } from '../data/ballTrace';
import { swingReview } from '../data/swingReview';
import {
  appendShotIds,
  challengeReport,
  classifySwing,
  emptySetup,
  replayWindow,
  timingOf,
  type TimedSwing,
} from './swingSession';

describe('shot and practice swing', () => {
  it('reads the range clip as one practice swing and one shot', () => {
    const roles = swingReview.map((swing, index) =>
      classifySwing({ events: swing.events, ball: ballTraces[index] }),
    );
    expect(roles).toEqual(['practice', 'shot']);
  });

  it('keeps a swing that never shows an impact cue as practice', () => {
    expect(classifySwing({ events: [{ name: 'Address' }], ball: [{ x: 0, y: 0 }, { x: 40, y: 40 }] })).toBe(
      'practice',
    );
  });

  it('keeps a ball that only jitters at the tee as practice', () => {
    expect(
      classifySwing({
        events: [{ name: 'Impact' }],
        ball: [
          { x: 100, y: 100 },
          { x: 104, y: 103 },
        ],
      }),
    ).toBe('practice');
  });
});

describe('five-shot consistency', () => {
  it('measures the range clip timings from address to impact', () => {
    const [first, second] = swingReview.map((swing) => timingOf(swing.events));
    expect(first.addressToImpactS).toBeCloseTo(1.9);
    expect(second.addressToImpactS).toBeCloseTo(14.3 - 12.433333);
    expect(first.address.leftElbow).toBe(160.9);
    expect(second.address.torsoTilt).toBe(29.6);
    expect(replayWindow(swingReview[1].events)?.start).toBeCloseTo(12.433333);
  });

  it('keeps saved shots, ignores practice swings, and stops at five', () => {
    expect(appendShotIds(['shot-a', 'gone'], ['shot-a', 'shot-b', 'shot-c'], 2)).toEqual(['shot-a', 'shot-b']);
    expect(appendShotIds(['a', 'b', 'c', 'd', 'e'], ['a', 'b', 'c', 'd', 'e', 'f'], 5)).toEqual([
      'a',
      'b',
      'c',
      'd',
      'e',
    ]);
  });

  it('names the pair whose setup and timing differ most', () => {
    const shots: TimedSwing[] = [
      shot('near-a', 1.2, 160),
      shot('near-b', 1.25, 162),
      shot('outlier', 1.8, 140),
    ];
    const report = challengeReport(shots);
    expect(report.counted).toBe(3);
    expect(report.timing?.spread).toBeCloseTo(0.6);
    expect(report.setupSpread).toBeCloseTo(22);
    expect(report.pair?.aId).toBe('near-a');
    expect(report.pair?.bId).toBe('outlier');
    expect(report.pair?.timingGap).toBeCloseTo(0.6);
  });

  it('waits for a second shot before naming a pair', () => {
    expect(challengeReport([shot('only', 1.4, 150)]).pair).toBeNull();
  });
});

function shot(id: string, addressToImpactS: number, elbow: number): TimedSwing {
  return {
    id,
    addressToImpactS,
    address: { ...emptySetup(), leftElbow: elbow, rightElbow: elbow },
  };
}
