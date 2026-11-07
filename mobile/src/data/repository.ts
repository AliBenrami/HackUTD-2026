import type { SQLiteDatabase } from 'expo-sqlite';
import { holesForNine } from '../domain/scoring';
import type {
  ARPreferences,
  Course,
  HoleScore,
  HudPreferences,
  NineSelection,
  Player,
  Round,
  SwingAnalysisResult,
  SwingSession,
  SwingSource,
  TeeSet,
} from '../domain/types';
import { defaultPreferences } from '../services/ar/bridge';
import { createId } from '../lib/id';
import { buildDemoSwing, buildSampleRounds } from './seed';

export type Snapshot = {
  player: Player;
  rounds: Round[];
  scores: Record<string, HoleScore[]>;
  swings: SwingSession[];
  preferences: ARPreferences;
  recentCourseIds: string[];
};

type RoundRow = {
  id: string;
  player_id: string;
  course_id: string;
  course_name: string;
  tee_set_id: string;
  tee_set_name: string;
  nine: NineSelection;
  started_at: string;
  completed_at: string | null;
  status: Round['status'];
  current_hole: number;
  sample: number;
};

type ScoreRow = {
  id: string;
  round_id: string;
  hole_number: number;
  par: number;
  yards: number;
  strokes: number | null;
  putts: number | null;
  penalties: number | null;
  fairway_hit: number | null;
  completed: number;
};

type SwingRow = {
  id: string;
  created_at: string;
  source: SwingSource;
  video_uri: string | null;
  club: string;
  status: SwingSession['status'];
  analysis_json: string | null;
};

function flag(value: number | null): boolean | null {
  if (value == null) return null;
  return value !== 0;
}

function mapRound(row: RoundRow): Round {
  return {
    id: row.id,
    playerId: row.player_id,
    courseId: row.course_id,
    courseName: row.course_name,
    teeSetId: row.tee_set_id,
    teeSetName: row.tee_set_name,
    nine: row.nine,
    startedAt: row.started_at,
    completedAt: row.completed_at,
    status: row.status,
    currentHole: row.current_hole,
    sample: row.sample === 1,
  };
}

function mapScore(row: ScoreRow): HoleScore {
  return {
    id: row.id,
    roundId: row.round_id,
    holeNumber: row.hole_number,
    par: row.par,
    yards: row.yards,
    strokes: row.strokes,
    putts: row.putts,
    penalties: row.penalties,
    fairwayHit: flag(row.fairway_hit),
    completed: row.completed === 1,
  };
}

function mapSwing(row: SwingRow): SwingSession {
  let analysis: SwingAnalysisResult | null = null;
  if (row.analysis_json) {
    try {
      analysis = JSON.parse(row.analysis_json) as SwingAnalysisResult;
    } catch {
      analysis = null;
    }
  }
  return {
    id: row.id,
    videoId: row.id,
    createdAt: row.created_at,
    source: row.source,
    videoUri: row.video_uri,
    storagePath: null,
    club: row.club,
    status: row.status,
    analysis,
  };
}

export async function seedDatabase(db: SQLiteDatabase): Promise<void> {
  const now = new Date().toISOString();
  await db.runAsync(
    'INSERT INTO player (id, name, created_at) VALUES (?, ?, ?)',
    'local-player',
    'You',
    now,
  );
  await savePreferences(db, defaultPreferences);

  for (const draft of buildSampleRounds()) {
    await insertRound(db, draft.round, draft.scores);
  }

  const demo = buildDemoSwing();
  await db.runAsync(
    `INSERT INTO swing_sessions (id, created_at, source, video_uri, club, status, analysis_json)
     VALUES (?, ?, ?, ?, ?, ?, ?)`,
    demo.id,
    demo.createdAt,
    demo.source,
    demo.videoUri,
    demo.club,
    demo.status,
    JSON.stringify(demo.analysis),
  );
}

async function insertRound(db: SQLiteDatabase, round: Round, scores: HoleScore[]): Promise<void> {
  await db.runAsync(
    `INSERT INTO rounds (
      id, player_id, course_id, course_name, tee_set_id, tee_set_name, nine,
      started_at, completed_at, status, current_hole, sample
    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    round.id,
    round.playerId,
    round.courseId,
    round.courseName,
    round.teeSetId,
    round.teeSetName,
    round.nine,
    round.startedAt,
    round.completedAt,
    round.status,
    round.currentHole,
    round.sample ? 1 : 0,
  );

  for (const score of scores) {
    await db.runAsync(
      `INSERT INTO hole_scores (
        id, round_id, hole_number, par, yards, strokes, putts, penalties, fairway_hit, completed
      ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
      score.id,
      score.roundId,
      score.holeNumber,
      score.par,
      score.yards,
      score.strokes,
      score.putts,
      score.penalties,
      score.fairwayHit == null ? null : score.fairwayHit ? 1 : 0,
      score.completed ? 1 : 0,
    );
  }
}

export async function loadSnapshot(db: SQLiteDatabase): Promise<Snapshot> {
  const player = await db.getFirstAsync<Player>(
    'SELECT id, name, created_at as createdAt FROM player LIMIT 1',
  );
  if (!player) throw new Error('Player record is missing.');

  const roundRows = await db.getAllAsync<RoundRow>('SELECT * FROM rounds ORDER BY started_at DESC');
  const scoreRows = await db.getAllAsync<ScoreRow>(
    'SELECT * FROM hole_scores ORDER BY hole_number ASC',
  );
  const swingRows = await db.getAllAsync<SwingRow>(
    'SELECT * FROM swing_sessions ORDER BY created_at DESC',
  );
  const recent = await db.getAllAsync<{ course_id: string }>(
    'SELECT course_id FROM recent_courses ORDER BY selected_at DESC LIMIT 6',
  );
  const preferences = await readPreferences(db);
  const scores: Record<string, HoleScore[]> = {};
  for (const row of scoreRows) {
    const score = mapScore(row);
    const list = scores[score.roundId] ?? [];
    list.push(score);
    scores[score.roundId] = list;
  }

  return {
    player,
    rounds: roundRows.map(mapRound),
    scores,
    swings: swingRows.map(mapSwing),
    preferences,
    recentCourseIds: recent.map((row) => row.course_id),
  };
}

async function readPreferences(db: SQLiteDatabase): Promise<ARPreferences> {
  const row = await db.getFirstAsync<{
    units: ARPreferences['units'];
    hud_json: string;
    sync_scores: number;
    device_json: string;
    last_sync_at: string | null;
  }>('SELECT * FROM preferences WHERE id = 1');
  if (!row) return defaultPreferences;
  try {
    return {
      units: row.units,
      hud: JSON.parse(row.hud_json) as HudPreferences,
      syncScores: row.sync_scores === 1,
      device: JSON.parse(row.device_json) as ARPreferences['device'],
      lastSyncAt: row.last_sync_at,
    };
  } catch {
    return defaultPreferences;
  }
}

export async function savePreferences(db: SQLiteDatabase, preferences: ARPreferences): Promise<void> {
  await db.runAsync(
    `INSERT INTO preferences (id, units, hud_json, sync_scores, device_json, last_sync_at)
     VALUES (1, ?, ?, ?, ?, ?)
     ON CONFLICT(id) DO UPDATE SET
       units = excluded.units,
       hud_json = excluded.hud_json,
       sync_scores = excluded.sync_scores,
       device_json = excluded.device_json,
       last_sync_at = excluded.last_sync_at`,
    preferences.units,
    JSON.stringify(preferences.hud),
    preferences.syncScores ? 1 : 0,
    JSON.stringify(preferences.device),
    preferences.lastSyncAt,
  );
}

export async function renamePlayer(db: SQLiteDatabase, playerId: string, name: string): Promise<void> {
  const next = name.trim() || 'You';
  await db.runAsync('UPDATE player SET name = ? WHERE id = ?', next, playerId);
}

export async function rememberCourse(db: SQLiteDatabase, courseId: string): Promise<void> {
  await db.runAsync(
    `INSERT INTO recent_courses (course_id, selected_at) VALUES (?, ?)
     ON CONFLICT(course_id) DO UPDATE SET selected_at = excluded.selected_at`,
    courseId,
    new Date().toISOString(),
  );
}

export async function startRound(
  db: SQLiteDatabase,
  input: { playerId: string; course: Course; tee: TeeSet; nine: NineSelection },
): Promise<string> {
  const active = await db.getFirstAsync<{ id: string }>(
    "SELECT id FROM rounds WHERE status = 'active' LIMIT 1",
  );
  if (active) throw new Error('A round is already in progress.');

  const holes = holesForNine(input.tee, input.nine);
  const roundId = createId('round');
  const round: Round = {
    id: roundId,
    playerId: input.playerId,
    courseId: input.course.id,
    courseName: input.course.name,
    teeSetId: input.tee.id,
    teeSetName: input.tee.name,
    nine: input.nine,
    startedAt: new Date().toISOString(),
    completedAt: null,
    status: 'active',
    currentHole: holes[0]?.number ?? 1,
    sample: false,
  };
  const scores: HoleScore[] = holes.map((hole) => ({
    id: createId('hole'),
    roundId,
    holeNumber: hole.number,
    par: hole.par,
    yards: hole.yards,
    strokes: null,
    putts: null,
    penalties: null,
    fairwayHit: null,
    completed: false,
  }));
  await insertRound(db, round, scores);
  await rememberCourse(db, input.course.id);
  return roundId;
}

export type HoleDraft = {
  roundId: string;
  holeNumber: number;
  strokes: number;
  putts: number | null;
  penalties: number | null;
  fairwayHit: boolean | null;
};

export async function saveHole(db: SQLiteDatabase, draft: HoleDraft): Promise<void> {
  const existing = await db.getFirstAsync<{ par: number }>(
    'SELECT par FROM hole_scores WHERE round_id = ? AND hole_number = ?',
    draft.roundId,
    draft.holeNumber,
  );
  if (!existing) throw new Error('That hole is not part of this round.');

  const strokes = Math.max(1, Math.round(draft.strokes));
  const penalties =
    draft.penalties == null ? null : Math.max(0, Math.min(Math.round(draft.penalties), strokes));
  const putts = draft.putts == null ? null : Math.max(0, Math.min(Math.round(draft.putts), strokes));
  const fairway = existing.par === 3 || draft.fairwayHit == null ? null : draft.fairwayHit ? 1 : 0;

  await db.runAsync(
    `UPDATE hole_scores
     SET strokes = ?, putts = ?, penalties = ?, fairway_hit = ?, completed = 1
     WHERE round_id = ? AND hole_number = ?`,
    strokes,
    putts,
    penalties,
    fairway,
    draft.roundId,
    draft.holeNumber,
  );

  const remaining = await db.getFirstAsync<{ count: number }>(
    'SELECT COUNT(*) as count FROM hole_scores WHERE round_id = ? AND completed = 0',
    draft.roundId,
  );
  if ((remaining?.count ?? 0) === 0) {
    await db.runAsync(
      `UPDATE rounds
       SET status = 'completed', completed_at = COALESCE(completed_at, ?)
       WHERE id = ?`,
      new Date().toISOString(),
      draft.roundId,
    );
  }
}

export async function setCurrentHole(
  db: SQLiteDatabase,
  roundId: string,
  holeNumber: number,
): Promise<void> {
  await db.runAsync(
    'UPDATE rounds SET current_hole = ? WHERE id = ?',
    holeNumber,
    roundId,
  );
}

export async function finishRound(db: SQLiteDatabase, roundId: string): Promise<void> {
  await db.runAsync(
    `UPDATE rounds
     SET status = 'completed', completed_at = COALESCE(completed_at, ?)
     WHERE id = ?`,
    new Date().toISOString(),
    roundId,
  );
}

export async function addSwing(
  db: SQLiteDatabase,
  input: {
    source: Exclude<SwingSource, 'demo'>;
    videoUri: string;
    club: string;
    analysis: SwingAnalysisResult;
  },
): Promise<string> {
  const id = createId('swing');
  await db.runAsync(
    `INSERT INTO swing_sessions (id, created_at, source, video_uri, club, status, analysis_json)
     VALUES (?, ?, ?, ?, ?, 'ready', ?)`,
    id,
    new Date().toISOString(),
    input.source,
    input.videoUri,
    input.club,
    JSON.stringify(input.analysis),
  );
  return id;
}
