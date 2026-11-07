import type { HoleInfo, HoleScore, NineSelection, TeeSet } from './types';

export type HoleInput = {
  holeNumber: number;
  par: number;
  strokes: number | null;
  putts: number | null;
  penalties: number | null;
  fairwayHit: boolean | null;
  completed: boolean;
};

export type HoleResult = {
  delta: number;
  label: string;
  plain: string;
};

export type HoleStat = {
  holeNumber: number;
  par: number;
  strokes: number;
  relative: number;
};

export type RoundStats = {
  completedHoles: number;
  totalStrokes: number | null;
  totalPar: number | null;
  relativeToPar: number | null;
  averageStrokes: number | null;
  averageRelativeToPar: number | null;
  parOrBetterPct: number | null;
  eaglesOrBetter: number | null;
  birdies: number | null;
  pars: number | null;
  bogeys: number | null;
  doubleBogeysOrWorse: number | null;
  averagePutts: number | null;
  puttsSampleSize: number;
  fairwayPct: number | null;
  fairwaysHit: number | null;
  fairwaysTracked: number;
  byHole: HoleStat[];
};

export type NineStats = {
  nine: 'front' | 'back';
  scheduled: number;
  completed: number;
  strokes: number | null;
  par: number | null;
  relative: number | null;
};

export function isScoredHole(hole: HoleInput): hole is HoleInput & { strokes: number } {
  return hole.completed && hole.strokes != null && hole.strokes > 0;
}

export function scoreToPar(strokes: number, par: number): number {
  return strokes - par;
}

export function holeResult(strokes: number, par: number): HoleResult {
  const delta = scoreToPar(strokes, par);
  if (delta <= -3) {
    return { delta, label: 'Albatross', plain: `${Math.abs(delta)} under par` };
  }
  if (delta === -2) return { delta, label: 'Eagle', plain: 'Two under par' };
  if (delta === -1) return { delta, label: 'Birdie', plain: 'One under par' };
  if (delta === 0) return { delta, label: 'Par', plain: 'Even par' };
  if (delta === 1) return { delta, label: 'Bogey', plain: 'One over par' };
  if (delta === 2) return { delta, label: 'Double bogey', plain: 'Two over par' };
  if (delta === 3) return { delta, label: 'Triple bogey', plain: 'Three over par' };
  return { delta, label: `${delta} over`, plain: `${delta} over par` };
}

export function summarizeHoles(holes: HoleInput[]): RoundStats {
  const done = holes.filter(isScoredHole);
  const byHole = done.map((hole) => ({
    holeNumber: hole.holeNumber,
    par: hole.par,
    strokes: hole.strokes,
    relative: scoreToPar(hole.strokes, hole.par),
  }));

  if (done.length === 0) {
    return {
      completedHoles: 0,
      totalStrokes: null,
      totalPar: null,
      relativeToPar: null,
      averageStrokes: null,
      averageRelativeToPar: null,
      parOrBetterPct: null,
      eaglesOrBetter: null,
      birdies: null,
      pars: null,
      bogeys: null,
      doubleBogeysOrWorse: null,
      averagePutts: null,
      puttsSampleSize: 0,
      fairwayPct: null,
      fairwaysHit: null,
      fairwaysTracked: 0,
      byHole: [],
    };
  }

  const totalStrokes = byHole.reduce((sum, hole) => sum + hole.strokes, 0);
  const totalPar = byHole.reduce((sum, hole) => sum + hole.par, 0);
  const relativeToPar = totalStrokes - totalPar;
  const withPutts = done.filter((hole) => hole.putts != null);
  const trackedFairways = done.filter((hole) => hole.fairwayHit != null);
  const fairwaysHit = trackedFairways.filter((hole) => hole.fairwayHit === true).length;

  return {
    completedHoles: done.length,
    totalStrokes,
    totalPar,
    relativeToPar,
    averageStrokes: totalStrokes / done.length,
    averageRelativeToPar: relativeToPar / done.length,
    parOrBetterPct: (byHole.filter((hole) => hole.relative <= 0).length / done.length) * 100,
    eaglesOrBetter: byHole.filter((hole) => hole.relative <= -2).length,
    birdies: byHole.filter((hole) => hole.relative === -1).length,
    pars: byHole.filter((hole) => hole.relative === 0).length,
    bogeys: byHole.filter((hole) => hole.relative === 1).length,
    doubleBogeysOrWorse: byHole.filter((hole) => hole.relative >= 2).length,
    averagePutts:
      withPutts.length === 0
        ? null
        : withPutts.reduce((sum, hole) => sum + (hole.putts ?? 0), 0) / withPutts.length,
    puttsSampleSize: withPutts.length,
    fairwayPct: trackedFairways.length === 0 ? null : (fairwaysHit / trackedFairways.length) * 100,
    fairwaysHit: trackedFairways.length === 0 ? null : fairwaysHit,
    fairwaysTracked: trackedFairways.length,
    byHole,
  };
}

export function nineSummary(holes: HoleInput[], nine: 'front' | 'back'): NineStats {
  const scheduled = holes.filter((hole) =>
    nine === 'front' ? hole.holeNumber <= 9 : hole.holeNumber >= 10,
  );
  const stats = summarizeHoles(scheduled);
  return {
    nine,
    scheduled: scheduled.length,
    completed: stats.completedHoles,
    strokes: stats.totalStrokes,
    par: stats.totalPar,
    relative: stats.relativeToPar,
  };
}

export function selectBestRound(
  rounds: { id: string; status: string; holes: HoleInput[] }[],
): { id: string; relative: number; strokes: number; par: number } | null {
  let best: { id: string; relative: number; strokes: number; par: number } | null = null;

  for (const round of rounds) {
    if (round.status !== 'completed') continue;
    const stats = summarizeHoles(round.holes);
    if (stats.relativeToPar == null || stats.totalStrokes == null || stats.totalPar == null) {
      continue;
    }
    const candidate = {
      id: round.id,
      relative: stats.relativeToPar,
      strokes: stats.totalStrokes,
      par: stats.totalPar,
    };
    const better =
      best == null ||
      candidate.relative < best.relative ||
      (candidate.relative === best.relative && candidate.strokes < best.strokes);
    if (better) best = candidate;
  }

  return best;
}

export function holesForNine(tee: TeeSet, nine: NineSelection): HoleInfo[] {
  if (nine === 'front') return tee.holes.filter((hole) => hole.number <= 9);
  if (nine === 'back') return tee.holes.filter((hole) => hole.number >= 10);
  return tee.holes;
}

export function sumPar(holes: Pick<HoleInfo, 'par'>[]): number {
  return holes.reduce((total, hole) => total + hole.par, 0);
}

export function sumYards(holes: Pick<HoleInfo, 'yards'>[]): number {
  return holes.reduce((total, hole) => total + hole.yards, 0);
}

export function holeScoreToInput(score: HoleScore): HoleInput {
  return {
    holeNumber: score.holeNumber,
    par: score.par,
    strokes: score.strokes,
    putts: score.putts,
    penalties: score.penalties,
    fairwayHit: score.fairwayHit,
    completed: score.completed,
  };
}
