import { holesForNine } from '../domain/scoring';
import type { HoleScore, NineSelection, Round, SwingAnalysisResult } from '../domain/types';
import { courses, getCourse, getTee } from './courses';
import { DEMO_ANALYSIS } from '../services/swing/analyzer';

export type SampleRoundDraft = {
  round: Round;
  scores: HoleScore[];
};

type StrokeRow = [strokes: number, putts: number, penalties: number, fairway: boolean | null];

function daysAgo(days: number, hour: number): string {
  const date = new Date();
  date.setDate(date.getDate() - days);
  date.setHours(hour, 12, 0, 0);
  return date.toISOString();
}

function buildRound(
  id: string,
  courseId: string,
  teeName: string,
  nine: NineSelection,
  startedAt: string,
  rows: StrokeRow[],
): SampleRoundDraft {
  const course = getCourse(courseId);
  if (!course) throw new Error(`Missing course ${courseId}`);
  const tee = course.teeSets.find((item) => item.name === teeName);
  if (!tee) throw new Error(`Missing tee ${teeName}`);
  const holes = holesForNine(tee, nine);
  if (holes.length !== rows.length) {
    throw new Error(`Sample ${id} has ${rows.length} rows for ${holes.length} holes`);
  }

  const scores: HoleScore[] = holes.map((hole, index) => {
    const [strokes, putts, penalties, fairway] = rows[index];
    return {
      id: `${id}-h${hole.number}`,
      roundId: id,
      holeNumber: hole.number,
      par: hole.par,
      yards: hole.yards,
      strokes,
      putts,
      penalties,
      fairwayHit: hole.par === 3 ? null : fairway,
      completed: true,
    };
  });

  return {
    round: {
      id,
      playerId: 'local-player',
      courseId: course.id,
      courseName: course.name,
      teeSetId: tee.id,
      teeSetName: tee.name,
      nine,
      startedAt,
      completedAt: new Date(new Date(startedAt).getTime() + 4 * 60 * 60 * 1000).toISOString(),
      status: 'completed',
      currentHole: holes[holes.length - 1].number,
      sample: true,
    },
    scores,
  };
}

const cedarRough: StrokeRow[] = [
  [4, 2, 0, true],
  [6, 2, 1, false],
  [3, 2, 0, null],
  [5, 2, 0, true],
  [4, 2, 0, true],
  [4, 2, 1, null],
  [3, 1, 0, true],
  [6, 2, 0, false],
  [5, 2, 0, true],
  [4, 2, 0, true],
  [5, 2, 0, false],
  [3, 1, 0, null],
  [7, 3, 1, false],
  [5, 2, 0, true],
  [4, 2, 0, true],
  [3, 2, 0, null],
  [6, 2, 0, true],
  [5, 2, 0, false],
];

const cedarBetter: StrokeRow[] = [
  [4, 2, 0, true],
  [6, 2, 0, false],
  [3, 2, 0, null],
  [6, 2, 0, true],
  [5, 2, 0, true],
  [3, 1, 0, null],
  [3, 1, 0, true],
  [3, 2, 0, true],
  [4, 2, 0, true],
  [4, 2, 0, true],
  [4, 2, 0, false],
  [2, 1, 0, null],
  [6, 2, 0, true],
  [4, 2, 0, true],
  [4, 2, 0, true],
  [3, 2, 0, null],
  [5, 2, 0, true],
  [5, 2, 0, false],
];

export function buildSampleRounds(): SampleRoundDraft[] {
  return [
    buildRound('round-sample-cedar-82', 'cedar-ridge', 'White', 'full', daysAgo(6, 9), cedarRough),
    buildRound('round-sample-cedar-74', 'cedar-ridge', 'White', 'full', daysAgo(2, 14), cedarBetter),
  ];
}

export function buildDemoSwing(analysis: SwingAnalysisResult = DEMO_ANALYSIS) {
  return {
    id: 'swing-demo',
    videoId: 'swing-demo',
    createdAt: daysAgo(12, 11),
    source: 'demo' as const,
    videoUri: null,
    storagePath: null,
    club: 'Driver',
    status: 'demo' as const,
    analysis,
  };
}

export function assertSampleCoursesExist(): void {
  const cedar = getCourse('cedar-ridge');
  const blue = cedar ? getTee(cedar, 'cedar-ridge-blue') : undefined;
  if (!blue || blue.holes[6]?.yards !== 387) {
    throw new Error('Cedar Ridge blue tee hole 7 must be 387 yards');
  }
  if (courses.length < 1) throw new Error('Course catalog is empty');
}
