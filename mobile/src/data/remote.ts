import type { Session } from '@supabase/supabase-js';
import { getCourse, getTee } from './courses';
import { buildSampleRounds } from './seed';
import { holesForNine } from '../domain/scoring';
import type {
  ARPreferences,
  HoleScore,
  NineSelection,
  Round,
  SwingSession,
  Units,
} from '../domain/types';
import { defaultPreferences, simulatedDevice } from '../services/ar/bridge';
import { supabase } from '../lib/supabase';
import type { HoleDraft, Snapshot } from './repository';

const BUCKET = 'swing-videos';

type PreferenceRow = {
  units: Units;
  show_distance: boolean;
  show_elevation: boolean;
  show_score: boolean;
  show_wind: boolean;
  sync_scores: boolean;
  device_name: string;
  device_model: string;
  device_connected: boolean;
  device_battery: number | null;
  device_firmware: string | null;
  last_sync_at: string | null;
};

function requireUser(session: Session) {
  return session.user;
}

function holeFacts(courseId: string, teeSetId: string, holeNumber: number) {
  const course = getCourse(courseId);
  const tee = course ? getTee(course, teeSetId) : undefined;
  const hole = tee?.holes.find((item) => item.number === holeNumber);
  if (!course || !tee || !hole) {
    throw new Error('That hole is not on the selected tee.');
  }
  return { course, tee, hole };
}

function mapPreferences(row: PreferenceRow | null): ARPreferences {
  if (!row) return defaultPreferences;
  return {
    units: row.units,
    hud: {
      showDistance: row.show_distance,
      showElevation: row.show_elevation,
      showScore: row.show_score,
      showWind: row.show_wind,
    },
    syncScores: row.sync_scores,
    device: {
      id: 'visor-horizon',
      name: row.device_name,
      model: row.device_model,
      connected: row.device_connected,
      battery: row.device_battery,
      firmware: row.device_firmware,
    },
    lastSyncAt: row.last_sync_at,
  };
}

async function ensureSampleRounds(userId: string) {
  const existing = await supabase.from('rounds').select('id', { count: 'exact', head: true });
  if (existing.error) throw existing.error;
  if ((existing.count ?? 0) > 0) return;

  for (const draft of buildSampleRounds()) {
    const roundId = crypto.randomUUID();
    const inserted = await supabase.from('rounds').insert({
      id: roundId,
      user_id: userId,
      course_id: draft.round.courseId,
      tee_set_id: draft.round.teeSetId,
      nine: draft.round.nine,
      started_at: draft.round.startedAt,
      completed_at: draft.round.completedAt,
      status: draft.round.status,
      current_hole: draft.round.currentHole,
      sample: true,
    });
    if (inserted.error) throw inserted.error;
    const scores = await supabase.from('hole_scores').insert(
      draft.scores.map((score) => ({
        round_id: roundId,
        hole_number: score.holeNumber,
        strokes: score.strokes,
        putts: score.putts,
        penalties: score.penalties,
        fairway_hit: score.fairwayHit,
        completed: true,
      })),
    );
    if (scores.error) throw scores.error;
  }
}

export async function loadRemoteSnapshot(session: Session): Promise<Snapshot> {
  const user = requireUser(session);
  await ensureSampleRounds(user.id);

  const [profile, preferences, rounds, scores, videos, swings, recent] = await Promise.all([
    supabase.from('profiles').select('id, display_name, created_at').eq('id', user.id).single(),
    supabase.from('preferences').select('*').eq('user_id', user.id).maybeSingle(),
    supabase.from('rounds').select('*').order('started_at', { ascending: false }),
    supabase.from('hole_scores').select('*').order('hole_number', { ascending: true }),
    supabase.from('swing_videos').select('*').order('created_at', { ascending: false }),
    supabase.from('swings').select('*').order('position', { ascending: true }),
    supabase.from('recent_courses').select('course_id, selected_at').order('selected_at', { ascending: false }).limit(6),
  ]);

  for (const result of [profile, preferences, rounds, scores, videos, swings, recent]) {
    if (result.error) throw result.error;
  }
  if (!profile.data) throw new Error('Your profile could not be opened.');

  const scoreRows = scores.data ?? [];
  const scoreMap: Record<string, HoleScore[]> = {};
  const roundRows = rounds.data ?? [];
  for (const round of roundRows) {
    const rows = scoreRows.filter((score) => score.round_id === round.id);
    scoreMap[round.id] = rows.map((score) => {
      const { hole } = holeFacts(round.course_id, round.tee_set_id, score.hole_number);
      return {
        id: `${round.id}-${score.hole_number}`,
        roundId: round.id,
        holeNumber: score.hole_number,
        par: hole.par,
        yards: hole.yards,
        strokes: score.strokes,
        putts: score.putts,
        penalties: score.penalties,
        fairwayHit: hole.par === 3 ? null : score.fairway_hit,
        completed: score.completed,
      };
    });
  }

  const paths = (videos.data ?? []).map((video) => video.storage_path);
  const signed = paths.length
    ? await supabase.storage.from(BUCKET).createSignedUrls(paths, 60 * 60)
    : { data: [], error: null };
  if (signed.error) throw signed.error;
  const urls = new Map((signed.data ?? []).map((item) => [item.path, item.signedUrl]));

  const swingRows: SwingSession[] = [];
  for (const video of videos.data ?? []) {
    const children = (swings.data ?? []).filter((swing) => swing.video_id === video.id);
    for (const swing of children) {
      swingRows.push({
        id: swing.id,
        videoId: video.id,
        createdAt: swing.created_at,
        source: video.source,
        videoUri: urls.get(video.storage_path) ?? null,
        storagePath: video.storage_path,
        club: video.club,
        status: 'ready',
        analysis: null,
      });
    }
  }

  return {
    player: {
      id: profile.data.id,
      name: profile.data.display_name,
      createdAt: profile.data.created_at,
    },
    rounds: roundRows.map((round) => {
      const course = getCourse(round.course_id);
      const tee = course ? getTee(course, round.tee_set_id) : undefined;
      return {
        id: round.id,
        playerId: round.user_id,
        courseId: round.course_id,
        courseName: course?.name ?? round.course_id,
        teeSetId: round.tee_set_id,
        teeSetName: tee?.name ?? round.tee_set_id,
        nine: round.nine,
        startedAt: round.started_at,
        completedAt: round.completed_at,
        status: round.status,
        currentHole: round.current_hole,
        sample: round.sample,
      } satisfies Round;
    }),
    scores: scoreMap,
    swings: swingRows,
    preferences: mapPreferences(preferences.data),
    recentCourseIds: (recent.data ?? []).map((row) => row.course_id),
  };
}

export async function saveRemotePreferences(preferences: ARPreferences) {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) throw userError ?? new Error('Sign in again.');
  const device = preferences.device.connected ? preferences.device : simulatedDevice(false);
  const saved = await supabase.from('preferences').upsert({
    user_id: userData.user.id,
    units: preferences.units,
    show_distance: preferences.hud.showDistance,
    show_elevation: preferences.hud.showElevation,
    show_score: preferences.hud.showScore,
    show_wind: preferences.hud.showWind,
    sync_scores: preferences.syncScores,
    device_name: device.name,
    device_model: device.model,
    device_connected: device.connected,
    device_battery: device.battery,
    device_firmware: device.firmware,
    last_sync_at: preferences.lastSyncAt,
  });
  if (saved.error) throw saved.error;
}

export async function renameRemotePlayer(name: string) {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) throw userError ?? new Error('Sign in again.');
  const saved = await supabase
    .from('profiles')
    .update({ display_name: name.trim() || 'You' })
    .eq('id', userData.user.id);
  if (saved.error) throw saved.error;
}

export async function rememberRemoteCourse(courseId: string) {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) throw userError ?? new Error('Sign in again.');
  const saved = await supabase.from('recent_courses').upsert({
    user_id: userData.user.id,
    course_id: courseId,
    selected_at: new Date().toISOString(),
  });
  if (saved.error) throw saved.error;
}

export async function startRemoteRound(input: {
  courseId: string;
  teeSetId: string;
  nine: NineSelection;
}) {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) throw userError ?? new Error('Sign in again.');
  const active = await supabase.from('rounds').select('id').eq('status', 'active').limit(1);
  if (active.error) throw active.error;
  if (active.data?.length) throw new Error('A round is already in progress.');

  const course = getCourse(input.courseId);
  const tee = course ? getTee(course, input.teeSetId) : undefined;
  if (!tee) throw new Error('That tee is not on this course.');
  const holes = holesForNine(tee, input.nine);
  const roundId = crypto.randomUUID();
  const inserted = await supabase.from('rounds').insert({
    id: roundId,
    user_id: userData.user.id,
    course_id: input.courseId,
    tee_set_id: input.teeSetId,
    nine: input.nine,
    status: 'active',
    current_hole: holes[0]?.number ?? 1,
    sample: false,
  });
  if (inserted.error) throw inserted.error;
  const scores = await supabase.from('hole_scores').insert(
    holes.map((item) => ({
      round_id: roundId,
      hole_number: item.number,
      completed: false,
    })),
  );
  if (scores.error) throw scores.error;
  await rememberRemoteCourse(input.courseId);
  return roundId;
}

export async function saveRemoteHole(draft: HoleDraft) {
  const round = await supabase
    .from('rounds')
    .select('course_id, tee_set_id')
    .eq('id', draft.roundId)
    .single();
  if (round.error) throw round.error;
  const { hole } = holeFacts(round.data.course_id, round.data.tee_set_id, draft.holeNumber);
  const strokes = Math.max(1, Math.round(draft.strokes));
  const penalties =
    draft.penalties == null ? null : Math.max(0, Math.min(Math.round(draft.penalties), strokes));
  const putts = draft.putts == null ? null : Math.max(0, Math.min(Math.round(draft.putts), strokes));
  const saved = await supabase
    .from('hole_scores')
    .update({
      strokes,
      putts,
      penalties,
      fairway_hit: hole.par === 3 ? null : draft.fairwayHit,
      completed: true,
    })
    .eq('round_id', draft.roundId)
    .eq('hole_number', draft.holeNumber);
  if (saved.error) throw saved.error;

  const remaining = await supabase
    .from('hole_scores')
    .select('hole_number', { count: 'exact', head: true })
    .eq('round_id', draft.roundId)
    .eq('completed', false);
  if (remaining.error) throw remaining.error;
  if ((remaining.count ?? 0) === 0) {
    await finishRemoteRound(draft.roundId);
  }
}

export async function setRemoteHole(roundId: string, holeNumber: number) {
  const saved = await supabase.from('rounds').update({ current_hole: holeNumber }).eq('id', roundId);
  if (saved.error) throw saved.error;
}

export async function finishRemoteRound(roundId: string) {
  const existing = await supabase.from('rounds').select('completed_at').eq('id', roundId).single();
  if (existing.error) throw existing.error;
  const saved = await supabase
    .from('rounds')
    .update({
      status: 'completed',
      completed_at: existing.data.completed_at ?? new Date().toISOString(),
    })
    .eq('id', roundId);
  if (saved.error) throw saved.error;
}

export async function recordRemoteSwing(input: { source: 'camera' | 'import'; videoUri: string; club: string }): Promise<{ videoId: string }> {
  const { data: userData, error: userError } = await supabase.auth.getUser();
  if (userError || !userData.user) throw userError ?? new Error('Sign in again.');
  const response = await fetch(input.videoUri);
  const body = await response.blob();
  const type = body.type || 'video/mp4';
  const ext = type.includes('webm') ? 'webm' : type.includes('quicktime') ? 'mov' : 'mp4';
  const videoId = crypto.randomUUID();
  const path = `${userData.user.id}/${videoId}.${ext}`;
  const uploaded = await supabase.storage.from(BUCKET).upload(path, body, { contentType: type });
  if (uploaded.error) throw uploaded.error;
  const video = await supabase.from('swing_videos').insert({
    id: videoId,
    user_id: userData.user.id,
    club: input.club,
    source: input.source,
    storage_path: path,
  });
  if (video.error) throw video.error;
  const swing = await supabase.from('swings').insert({
    id: crypto.randomUUID(),
    video_id: videoId,
    position: 1,
  });
  if (swing.error) throw swing.error;
  return { videoId };
}

export async function deleteRemoteSwing(swingId: string) {
  const swing = await supabase.from('swings').select('id, video_id').eq('id', swingId).single();
  if (swing.error) throw swing.error;
  const removed = await supabase.from('swings').delete().eq('id', swingId);
  if (removed.error) throw removed.error;
  const remaining = await supabase
    .from('swings')
    .select('id', { count: 'exact', head: true })
    .eq('video_id', swing.data.video_id);
  if (remaining.error) throw remaining.error;
  if ((remaining.count ?? 0) > 0) return;
  const video = await supabase.from('swing_videos').select('storage_path').eq('id', swing.data.video_id).single();
  if (video.error) throw video.error;
  const file = await supabase.storage.from(BUCKET).remove([video.data.storage_path]);
  if (file.error) throw file.error;
  const deleted = await supabase.from('swing_videos').delete().eq('id', swing.data.video_id);
  if (deleted.error) throw deleted.error;
}
