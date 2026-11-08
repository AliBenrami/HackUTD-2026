import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useState } from 'react';
import { Pressable, View } from 'react-native';
import { AppText, BackHeader, Button, Screen } from '../components/ui';
import { formatRelative } from '../domain/format';
import { courseHandicap } from '../domain/caddie';
import { holeResult, holeScoreToInput, nineSummary, summarizeHoles } from '../domain/scoring';
import { getCourse, getTee } from '../data/courses';
import { loadRecap } from '../services/golf/client';
import type { HoleScore, Round } from '../domain/types';
import { useGolf } from '../state/GolfContext';
import { resultTone } from '../theme/colors';

export default function ScorecardScreen() {
  const params = useLocalSearchParams<{ roundId?: string }>();
  const { rounds, scores, activeRound, saveHoleScore, focusHole, bag, userId } = useGolf();
  const [recap, setRecap] = useState<string[] | null>(null);
  const round =
    rounds.find((item) => item.id === params.roundId) ??
    activeRound ??
    rounds[0] ??
    null;
  const holes = round ? (scores[round.id] ?? []) : [];
  const [editing, setEditing] = useState<number | null>(null);

  useEffect(() => {
    if (!round) return;
    let alive = true;
    loadRecap(userId, round.id)
      .then((lines) => {
        if (alive) setRecap(lines);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [round, userId]);

  if (!round) {
    return (
      <Screen header={<BackHeader title="Scorecard" onBack={() => router.back()} />}>
        <AppText className="text-slate">Start a round to fill in a scorecard.</AppText>
      </Screen>
    );
  }

  const stats = summarizeHoles(holes.map(holeScoreToInput));
  const course = getCourse(round.courseId);
  const tee = course ? getTee(course, round.teeSetId) : undefined;
  const handicap =
    round?.nine === 'full' && bag.handicapIndex != null && tee?.rating != null && tee.slope != null && stats.totalPar != null
      ? courseHandicap(bag.handicapIndex, tee.slope, tee.rating, stats.totalPar)
      : null;
  const relative = stats.relativeToPar == null ? null : formatRelative(stats.relativeToPar);
  const front = holes.some((hole) => hole.holeNumber <= 9);
  const back = holes.some((hole) => hole.holeNumber >= 10);

  return (
    <Screen header={<BackHeader title="Scorecard" onBack={() => router.back()} />}>
      <AppText weight="semibold" className="text-2xl">
        {round.courseName}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">
        {round.teeSetName} tees · {round.status === 'active' ? 'In progress' : 'Finished'}
        {round.sample ? ' · Sample' : ''}
      </AppText>
      <AppText weight="semibold" className="mt-3 text-3xl" style={{ color: toneFor(stats.relativeToPar) }}>
        {relative ? `${relative.symbol} · ${relative.words}` : 'No holes saved'}
      </AppText>
      {recap ? (
        <View className="mt-4 rounded-3xl border border-white/10 bg-panel p-4">
          {recap.map((line) => (
            <AppText key={line} className="mb-2 text-sm">
              {line}
            </AppText>
          ))}
        </View>
      ) : null}
      {stats.totalStrokes != null && handicap != null ? (
        <AppText className="mt-1 text-sm text-slate">Net {stats.totalStrokes - handicap}</AppText>
      ) : null}
      {stats.totalStrokes != null ? (
        <AppText className="mt-1 text-sm text-slate">
          {stats.totalStrokes} strokes · par {stats.totalPar} on saved holes
        </AppText>
      ) : null}

      {front ? <NineTable title="Front 9" holes={holes.filter((hole) => hole.holeNumber <= 9)} round={round} editing={editing} onEdit={setEditing} onSave={saveHoleScore} onOpen={focusHole} /> : null}
      {back ? <NineTable title="Back 9" holes={holes.filter((hole) => hole.holeNumber >= 10)} round={round} editing={editing} onEdit={setEditing} onOpen={focusHole} onSave={saveHoleScore} /> : null}

      <View className="mt-4 rounded-3xl border border-white/10 bg-panel p-4">
        <Total label="Front" summary={nineSummary(holes.map(holeScoreToInput), 'front')} show={front} />
        <Total label="Back" summary={nineSummary(holes.map(holeScoreToInput), 'back')} show={back} />
        <View className="mt-3 flex-row items-center justify-between border-t border-white/10 pt-3">
          <AppText weight="semibold">Total</AppText>
          <AppText weight="semibold">
            {stats.totalStrokes ?? '—'}
            {relative ? `  ${relative.symbol}` : ''}
          </AppText>
        </View>
      </View>
    </Screen>
  );
}

function toneFor(value: number | null): string {
  if (value == null || value === 0) return '#F3F6FA';
  return resultTone(value);
}

function NineTable({
  title,
  holes,
  round,
  editing,
  onEdit,
  onSave,
  onOpen,
}: {
  title: string;
  holes: HoleScore[];
  round: Round;
  editing: number | null;
  onEdit: (hole: number | null) => void;
  onSave: (draft: {
    roundId: string;
    holeNumber: number;
    strokes: number;
    putts: number | null;
    penalties: number | null;
    fairwayHit: boolean | null;
  }) => Promise<void>;
  onOpen: (roundId: string, holeNumber: number) => Promise<void>;
}) {
  const summary = nineSummary(holes.map(holeScoreToInput), holes[0]?.holeNumber >= 10 ? 'back' : 'front');
  return (
    <View className="mt-5">
      <View className="mb-2 flex-row items-center justify-between">
        <AppText weight="medium" className="text-sm text-slate">
          {title}
        </AppText>
        <AppText className="text-xs text-slate">
          {summary.completed} of {summary.scheduled} saved
        </AppText>
      </View>
      <View className="flex-row px-3 pb-2">
        <AppText className="w-12 text-xs text-slate">Hole</AppText>
        <AppText className="w-12 text-xs text-slate">Par</AppText>
        <AppText className="flex-1 text-xs text-slate">Strokes</AppText>
        <AppText className="w-24 text-right text-xs text-slate">Result</AppText>
      </View>
      {holes.map((hole) => {
        const open = editing === hole.holeNumber;
        const played = hole.completed && hole.strokes != null;
        const result = played && hole.strokes != null ? holeResult(hole.strokes, hole.par) : null;
        const current = round.status === 'active' && round.currentHole === hole.holeNumber;
        return (
          <View key={hole.id}>
            <Pressable
              accessibilityRole="button"
              onPress={() => onEdit(open ? null : hole.holeNumber)}
              className={`min-h-12 flex-row items-center border-t border-white/10 px-3 ${
                current ? 'bg-panel' : ''
              }`}
            >
              <AppText weight={current ? 'semibold' : 'regular'} className="w-12">
                {hole.holeNumber}
              </AppText>
              <AppText className="w-12 text-slate">{hole.par}</AppText>
              <AppText className="flex-1">{played ? hole.strokes : '—'}</AppText>
              <AppText
                className="w-24 text-right text-sm"
                style={{ color: result ? resultTone(result.delta) : '#8B97A8' }}
              >
                {result ? result.label : ' '}
              </AppText>
            </Pressable>
            {open ? (
              <HoleEdit
                hole={hole}
                onSave={async (strokes) => {
                  await onSave({
                    roundId: round.id,
                    holeNumber: hole.holeNumber,
                    strokes,
                    putts: hole.putts,
                    penalties: hole.penalties,
                    fairwayHit: hole.fairwayHit,
                  });
                  onEdit(null);
                }}
                onOpenRound={
                  round.status === 'active'
                    ? async () => {
                        await onOpen(round.id, hole.holeNumber);
                        router.navigate('/round');
                      }
                    : undefined
                }
              />
            ) : null}
          </View>
        );
      })}
      <View className="flex-row items-center px-3 pt-3">
        <AppText weight="medium" className="flex-1">
          {title === 'Front 9' ? 'Out' : 'In'}
        </AppText>
        <AppText weight="medium">
          {summary.strokes ?? '—'}
          {summary.relative != null ? `  ${formatRelative(summary.relative).symbol}` : ''}
        </AppText>
      </View>
    </View>
  );
}

function HoleEdit({
  hole,
  onSave,
  onOpenRound,
}: {
  hole: HoleScore;
  onSave: (strokes: number) => Promise<void>;
  onOpenRound?: () => Promise<void>;
}) {
  const [strokes, setStrokes] = useState(hole.strokes ?? hole.par);
  return (
    <View className="mb-2 rounded-2xl bg-panel px-3 py-3">
      <View className="flex-row items-center justify-between">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Fewer strokes"
          onPress={() => setStrokes((value) => Math.max(1, value - 1))}
          className="h-11 w-11 items-center justify-center rounded-full border border-white/10"
        >
          <AppText weight="semibold">−</AppText>
        </Pressable>
        <AppText weight="semibold" className="text-2xl">
          {strokes}
        </AppText>
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="More strokes"
          onPress={() => setStrokes((value) => Math.min(15, value + 1))}
          className="h-11 w-11 items-center justify-center rounded-full border border-white/10"
        >
          <AppText weight="semibold">+</AppText>
        </Pressable>
      </View>
      <View className="mt-3">
        <Button label="Save hole" onPress={() => void onSave(strokes)} />
      </View>
      {onOpenRound ? (
        <Pressable accessibilityRole="button" onPress={() => void onOpenRound()} className="mt-3 min-h-11 items-center justify-center">
          <AppText className="text-sm text-cyan">Open in the round</AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

function Total({
  label,
  summary,
  show,
}: {
  label: string;
  summary: { strokes: number | null; relative: number | null; completed: number; scheduled: number };
  show: boolean;
}) {
  if (!show || summary.scheduled === 0) return null;
  return (
    <View className="mb-2 flex-row items-center justify-between">
      <AppText className="text-slate">{label}</AppText>
      <AppText>
        {summary.strokes ?? '—'}
        {summary.relative != null ? `  ${formatRelative(summary.relative).symbol}` : ''}
      </AppText>
    </View>
  );
}
