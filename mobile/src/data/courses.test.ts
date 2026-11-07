import { describe, expect, it } from 'vitest';
import { holeScoreToInput, holesForNine, selectBestRound, summarizeHoles, sumPar, sumYards } from '../domain/scoring';
import { courses, defaultTee, getTee } from './courses';
import { buildSampleRounds } from './seed';

describe('course catalog', () => {
  it('keeps every course internally consistent', () => {
    expect(courses.length).toBeGreaterThanOrEqual(3);
    for (const course of courses) {
      const ids = new Set(course.teeSets.map((tee) => tee.id));
      expect(ids.size).toBe(course.teeSets.length);
      for (const tee of course.teeSets) {
        expect(tee.holes).toHaveLength(18);
        expect(sumPar(tee.holes)).toBe(72);
        const handicaps = tee.holes.map((hole) => hole.handicap).sort((a, b) => a - b);
        expect(handicaps).toEqual(Array.from({ length: 18 }, (_, index) => index + 1));
        expect(sumYards(tee.holes)).toBeGreaterThan(4500);
      }
      const [black, blue, white, red] = course.teeSets;
      for (let index = 0; index < 18; index += 1) {
        expect(black.holes[index].par).toBe(blue.holes[index].par);
        expect(black.holes[index].yards).toBeGreaterThanOrEqual(blue.holes[index].yards);
        expect(blue.holes[index].yards).toBeGreaterThanOrEqual(white.holes[index].yards);
        expect(white.holes[index].yards).toBeGreaterThanOrEqual(red.holes[index].yards);
      }
    }
  });

  it('matches the Cedar Ridge blue yardage used in the round preview', () => {
    const cedar = courses.find((course) => course.id === 'cedar-ridge');
    const blue = cedar ? getTee(cedar, 'cedar-ridge-blue') : undefined;
    expect(blue?.holes.find((hole) => hole.number === 7)?.yards).toBe(387);
    expect(cedar ? sumPar(holesForNine(defaultTee(cedar), 'front')) : 0).toBe(36);
    expect(cedar ? holesForNine(defaultTee(cedar), 'back') : []).toHaveLength(9);
  });
});

describe('sample rounds', () => {
  it('calculates stored sample rounds instead of hard-coded dashboard numbers', () => {
    const [rough, better] = buildSampleRounds();
    const roughStats = summarizeHoles(rough.scores.map(holeScoreToInput));
    const betterStats = summarizeHoles(better.scores.map(holeScoreToInput));
    const penaltySum = rough.scores.reduce((sum, hole) => sum + (hole.penalties ?? 0), 0);

    expect(penaltySum).toBeGreaterThan(0);
    expect(roughStats.totalStrokes).toBe(82);
    expect(roughStats.relativeToPar).toBe(10);
    expect(roughStats.birdies).toBe(1);
    expect(roughStats.pars).toBe(7);
    expect(roughStats.bogeys).toBe(9);
    expect(roughStats.doubleBogeysOrWorse).toBe(1);
    expect(roughStats.parOrBetterPct).toBeCloseTo((8 / 18) * 100);
    expect(roughStats.fairwaysTracked).toBe(14);
    expect(roughStats.fairwaysHit).toBe(9);
    expect(roughStats.averagePutts).toBeCloseTo(35 / 18);

    expect(betterStats.totalStrokes).toBe(74);
    expect(betterStats.relativeToPar).toBe(2);
    expect(betterStats.eaglesOrBetter).toBe(1);

    const best = selectBestRound([
      { id: rough.round.id, status: rough.round.status, holes: rough.scores.map(holeScoreToInput) },
      { id: better.round.id, status: better.round.status, holes: better.scores.map(holeScoreToInput) },
    ]);
    expect(best?.id).toBe(better.round.id);
  });
});
