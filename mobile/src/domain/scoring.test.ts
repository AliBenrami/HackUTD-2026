import { describe, expect, it } from 'vitest';
import { formatAverageRelative, formatRelative } from './format';
import {
  holeResult,
  nineSummary,
  selectBestRound,
  summarizeHoles,
  type HoleInput,
} from './scoring';

function hole(partial: Partial<HoleInput> & Pick<HoleInput, 'holeNumber' | 'par'>): HoleInput {
  return {
    strokes: null,
    putts: null,
    penalties: null,
    fairwayHit: null,
    completed: false,
    ...partial,
  };
}

describe('summarizeHoles', () => {
  it('ignores unfinished holes and does not add penalty strokes again', () => {
    const stats = summarizeHoles([
      hole({
        holeNumber: 1,
        par: 4,
        strokes: 5,
        putts: null,
        penalties: 2,
        fairwayHit: true,
        completed: true,
      }),
      hole({
        holeNumber: 2,
        par: 3,
        strokes: 6,
        putts: 2,
        penalties: 1,
        completed: false,
      }),
      hole({ holeNumber: 3, par: 5, strokes: null, completed: false }),
    ]);

    expect(stats.completedHoles).toBe(1);
    expect(stats.totalStrokes).toBe(5);
    expect(stats.totalPar).toBe(4);
    expect(stats.relativeToPar).toBe(1);
    expect(stats.averageStrokes).toBe(5);
    expect(stats.averageRelativeToPar).toBe(1);
    expect(stats.parOrBetterPct).toBe(0);
    expect(stats.averagePutts).toBeNull();
    expect(stats.puttsSampleSize).toBe(0);
    expect(stats.birdies).toBe(0);
    expect(stats.bogeys).toBe(1);
  });

  it('returns unavailable statistics when no hole is complete', () => {
    const stats = summarizeHoles([
      hole({ holeNumber: 1, par: 4, strokes: 4, completed: false }),
      hole({ holeNumber: 2, par: 4, completed: true, strokes: null }),
    ]);

    expect(stats.completedHoles).toBe(0);
    expect(stats.totalStrokes).toBeNull();
    expect(stats.relativeToPar).toBeNull();
    expect(stats.averageStrokes).toBeNull();
    expect(stats.averageRelativeToPar).toBeNull();
    expect(stats.parOrBetterPct).toBeNull();
    expect(stats.birdies).toBeNull();
    expect(stats.pars).toBeNull();
    expect(stats.bogeys).toBeNull();
    expect(stats.averagePutts).toBeNull();
    expect(stats.fairwayPct).toBeNull();
    expect(stats.fairwaysHit).toBeNull();
    expect(stats.byHole).toEqual([]);
  });

  it('keeps a recorded zero distinct from a missing value', () => {
    const stats = summarizeHoles([
      hole({
        holeNumber: 1,
        par: 4,
        strokes: 4,
        putts: 0,
        fairwayHit: false,
        completed: true,
      }),
      hole({
        holeNumber: 2,
        par: 5,
        strokes: 4,
        putts: 2,
        fairwayHit: false,
        completed: true,
      }),
    ]);

    expect(stats.birdies).toBe(1);
    expect(stats.pars).toBe(1);
    expect(stats.bogeys).toBe(0);
    expect(stats.averagePutts).toBe(1);
    expect(stats.fairwaysHit).toBe(0);
    expect(stats.fairwaysTracked).toBe(2);
    expect(stats.fairwayPct).toBe(0);
    expect(stats.parOrBetterPct).toBe(100);
    expect(stats.relativeToPar).toBe(-1);
    expect(stats.averageStrokes).toBe(4);
    expect(stats.averageRelativeToPar).toBe(-0.5);
  });

  it('averages putts and fairways only across holes where they were tracked', () => {
    const stats = summarizeHoles([
      hole({ holeNumber: 1, par: 4, strokes: 4, putts: 2, fairwayHit: true, completed: true }),
      hole({ holeNumber: 2, par: 3, strokes: 3, putts: null, fairwayHit: null, completed: true }),
      hole({ holeNumber: 3, par: 5, strokes: 7, putts: 4, fairwayHit: false, completed: true }),
    ]);

    expect(stats.averagePutts).toBe(3);
    expect(stats.puttsSampleSize).toBe(2);
    expect(stats.fairwaysHit).toBe(1);
    expect(stats.fairwaysTracked).toBe(2);
    expect(stats.fairwayPct).toBe(50);
    expect(stats.doubleBogeysOrWorse).toBe(1);
    expect(stats.byHole.map((item) => item.relative)).toEqual([0, 0, 2]);
  });
});

describe('nineSummary', () => {
  it('sums only the completed holes in that nine', () => {
    const holes = [
      hole({ holeNumber: 1, par: 4, strokes: 5, completed: true }),
      hole({ holeNumber: 9, par: 4, strokes: 4, completed: true }),
      hole({ holeNumber: 10, par: 4, strokes: 6, completed: false }),
      hole({ holeNumber: 18, par: 4, strokes: 5, completed: true }),
    ];

    expect(nineSummary(holes, 'front')).toMatchObject({
      scheduled: 2,
      completed: 2,
      strokes: 9,
      par: 8,
      relative: 1,
    });
    expect(nineSummary(holes, 'back')).toMatchObject({
      scheduled: 2,
      completed: 1,
      strokes: 5,
      par: 4,
      relative: 1,
    });
  });
});

describe('selectBestRound', () => {
  it('uses finished rounds only and prefers the lower score to par', () => {
    const best = selectBestRound([
      {
        id: 'active-better',
        status: 'active',
        holes: [hole({ holeNumber: 1, par: 4, strokes: 3, completed: true })],
      },
      {
        id: 'finished-higher',
        status: 'completed',
        holes: [hole({ holeNumber: 1, par: 4, strokes: 6, completed: true })],
      },
      {
        id: 'finished-best',
        status: 'completed',
        holes: [
          hole({ holeNumber: 1, par: 4, strokes: 4, completed: true }),
          hole({ holeNumber: 2, par: 4, strokes: 5, completed: true }),
        ],
      },
      {
        id: 'empty-finished',
        status: 'completed',
        holes: [hole({ holeNumber: 1, par: 4, completed: false })],
      },
    ]);

    expect(best).toEqual({ id: 'finished-best', relative: 1, strokes: 9, par: 8 });
  });

  it('breaks ties toward fewer strokes', () => {
    const best = selectBestRound([
      {
        id: 'longer',
        status: 'completed',
        holes: [
          hole({ holeNumber: 1, par: 4, strokes: 4, completed: true }),
          hole({ holeNumber: 2, par: 4, strokes: 4, completed: true }),
        ],
      },
      {
        id: 'shorter',
        status: 'completed',
        holes: [hole({ holeNumber: 1, par: 4, strokes: 4, completed: true })],
      },
    ]);

    expect(best?.id).toBe('shorter');
  });
});

describe('hole language', () => {
  it('names common hole results in plain language', () => {
    expect(holeResult(2, 4).label).toBe('Eagle');
    expect(holeResult(3, 4)).toMatchObject({ label: 'Birdie', plain: 'One under par' });
    expect(holeResult(4, 4).label).toBe('Par');
    expect(holeResult(5, 4).plain).toBe('One over par');
    expect(holeResult(6, 4).label).toBe('Double bogey');
    expect(formatRelative(3)).toEqual({ symbol: '+3', words: '3 over par' });
    expect(formatRelative(0)).toEqual({ symbol: 'E', words: 'Even par' });
    expect(formatRelative(-2)).toEqual({ symbol: '-2', words: '2 under par' });
    expect(formatAverageRelative(0.55).words).toBe('0.6 over par per hole');
    expect(formatAverageRelative(0).symbol).toBe('E');
  });
});
