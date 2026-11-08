import { router } from 'expo-router';
import { useMemo, useState } from 'react';
import { Pressable, View } from 'react-native';
import { ScoreChart } from '../../components/ScoreChart';
import { AppText, Screen, Segmented } from '../../components/ui';
import {
  formatAverageRelative,
  formatCount,
  formatDecimal,
  formatPercent,
  formatRelative,
  formatWhen,
} from '../../domain/format';
import { averageByHoleNumber, holeScoreToInput, selectBestRound, summarizeHoles, type RoundStats } from '../../domain/scoring';
import type { HoleScore, Round } from '../../domain/types';
import { useGolf } from '../../state/GolfContext';
import { resultTone } from '../../theme/colors';

type Scope = 'round' | 'all';

export default function StatsScreen() {
  const { rounds, scores, activeRound, notes } = useGolf();
  const [scope, setScope] = useState<Scope>(activeRound ? 'round' : 'all');
  const focus = activeRound ?? rounds[0] ?? null;
  const roundHoles = focus ? (scores[focus.id] ?? []) : [];
  const allHoles = useMemo(
    () =>
      [...rounds]
        .reverse()
        .flatMap((round) => scores[round.id] ?? []),
    [rounds, scores],
  );
  const holes = scope === 'round' ? roundHoles : allHoles;
  const stats = summarizeHoles(holes.map(holeScoreToInput));
  const best = selectBestRound(
    rounds.map((round) => ({
      id: round.id,
      status: round.status,
      holes: (scores[round.id] ?? []).map(holeScoreToInput),
    })),
  );
  const bestRound = rounds.find((round) => round.id === best?.id) ?? null;
  const onlySamples = rounds.length > 0 && rounds.every((round) => round.sample);
  const chartCourses = rounds.filter((round, index, all) => all.findIndex((item) => item.courseId === round.courseId) === index);
  const [chartCourseId, setChartCourseId] = useState(focus?.courseId ?? chartCourses[0]?.courseId ?? '');
  const chartHoles =
    scope === 'all'
      ? averageByHoleNumber(
          rounds
            .filter((round) => round.status === 'completed' && !round.sample && round.courseId === chartCourseId)
            .map((round) => (scores[round.id] ?? []).map(holeScoreToInput)),
        )
      : stats.byHole;
  const realNotes = notes.filter((note) => !note.sample && note.strokes != null);
  const misses = realNotes.filter((note) => note.miss);
  const greens = realNotes.filter((note) => note.gir != null);

  return (
    <Screen>
      <AppText weight="semibold" className="text-2xl">
        Statistics
      </AppText>
      <AppText className="mt-1 text-sm text-slate">Averages use saved holes only.</AppText>
      {onlySamples ? (
        <AppText className="mt-2 text-sm text-slate">
          Two sample rounds are stored on this device until you play your own.
        </AppText>
      ) : null}

      <View className="mt-5">
        <Segmented
          options={[
            { value: 'round' as const, label: activeRound ? 'This round' : 'Latest round' },
            { value: 'all' as const, label: 'All rounds' },
          ]}
          value={scope}
          onChange={setScope}
        />
      </View>

      {scope === 'round' && focus ? (
        <AppText className="mt-3 text-sm text-slate">
          {focus.courseName} · {formatWhen(focus.startedAt)}
          {focus.status === 'active' ? ' · In progress' : ''}
          {focus.sample ? ' · Sample' : ''}
        </AppText>
      ) : null}

      {rounds.length === 0 ? (
        <AppText className="mt-8 text-base text-slate">
          Play a round to see your statistics. Nothing here is filled in ahead of time.
        </AppText>
      ) : (
        <>
          <ScoreHero stats={stats} />
          <View className="mt-3 flex-row gap-3">
            <Tile label="Avg / hole" value={formatDecimal(stats.averageStrokes)} hint="Strokes" />
            <Tile
              label="Par or better"
              value={formatPercent(stats.parOrBetterPct)}
              hint="Saved holes"
            />
            <Tile label="Birdies" value={formatCount(stats.birdies)} hint="One under" />
          </View>

          <AppText weight="semibold" className="mb-3 mt-8 text-lg">
            Score by hole
          </AppText>
          {scope === 'all' && chartCourses.length > 1 ? (
            <View className="mb-3 flex-row flex-wrap gap-2">
              {chartCourses.map((round) => (
                <Pressable key={round.courseId} accessibilityRole="button" onPress={() => setChartCourseId(round.courseId)} className="min-h-10 justify-center rounded-full border border-white/10 px-3">
                  <AppText className={`text-sm ${round.courseId === chartCourseId ? 'text-cyan' : ''}`}>{round.courseName}</AppText>
                </Pressable>
              ))}
            </View>
          ) : null}
          <ScoreChart holes={chartHoles} />
          {scope === 'all' ? (
            <AppText className="mt-2 text-xs text-slate">
              Average against par for each hole number, from finished rounds on the selected course. Sample rounds are left out.
            </AppText>
          ) : null}

          <AppText weight="semibold" className="mb-3 mt-8 text-lg">
            Hole results
          </AppText>
          <View className="flex-row gap-3">
            <Tile label="Eagles +" value={formatCount(stats.eaglesOrBetter)} hint="Two under or better" />
            <Tile label="Pars" value={formatCount(stats.pars)} hint="Even" />
            <Tile label="Bogeys" value={formatCount(stats.bogeys)} hint="One over" />
          </View>
          <View className="mt-3">
            <Tile
              label="Double bogey or worse"
              value={formatCount(stats.doubleBogeysOrWorse)}
              hint="Two or more over par"
            />
          </View>

          <AppText weight="semibold" className="mb-3 mt-8 text-lg">
            More detail
          </AppText>
          <Detail
            label="Average putts"
            value={stats.averagePutts == null ? 'Not recorded' : formatDecimal(stats.averagePutts)}
            hint={
              stats.averagePutts == null
                ? 'Enter putts on a hole and they will show up here.'
                : `From ${stats.puttsSampleSize} holes with putts entered.`
            }
          />
          <Detail
            label="Miss direction"
            value={
              misses.length === 0
                ? 'Not recorded'
                : `Left ${misses.filter((note) => note.miss === 'left').length} · Right ${misses.filter((note) => note.miss === 'right').length}`
            }
            hint={misses.length === 0 ? 'Mark a miss on a hole and it will show up here.' : `${misses.length} holes with a miss entered.`}
          />
          <Detail
            label="Greens in regulation"
            value={
              greens.length === 0
                ? 'Not recorded'
                : `${Math.round((greens.filter((note) => note.gir).length / greens.length) * 100)}%`
            }
            hint={greens.length === 0 ? 'Mark a green on a hole and it will show up here.' : `${greens.filter((note) => note.gir).length} of ${greens.length} holes.`}
          />
          <Detail
            label="Fairways hit"
            value={
              stats.fairwayPct == null
                ? 'Not recorded'
                : `${formatPercent(stats.fairwayPct)} · ${stats.fairwaysHit}/${stats.fairwaysTracked}`
            }
            hint="Par 3s are left out. Missed fairways count as zero, not as missing data."
          />
          <Detail
            label="Best finished round"
            value={
              best && bestRound
                ? `${bestRound.courseName} · ${formatRelative(best.relative).symbol}`
                : 'No finished round'
            }
            hint={
              best
                ? `${best.strokes} strokes, ${formatRelative(best.relative).words}. Unfinished rounds are not included.`
                : 'Finish a round to set a best score.'
            }
          />

          <AppText weight="semibold" className="mb-3 mt-8 text-lg">
            Round history
          </AppText>
          {rounds.map((round) => (
            <HistoryRow key={round.id} round={round} holes={scores[round.id] ?? []} />
          ))}
        </>
      )}
    </Screen>
  );
}

function ScoreHero({ stats }: { stats: RoundStats }) {
  if (stats.relativeToPar == null || stats.totalStrokes == null || stats.totalPar == null) {
    return (
      <View className="mt-5 rounded-3xl border border-white/10 bg-panel p-5">
        <AppText className="text-base text-slate">No saved holes in this view yet.</AppText>
      </View>
    );
  }
  const relative = formatRelative(stats.relativeToPar);
  const perHole = formatAverageRelative(stats.averageRelativeToPar ?? 0);
  return (
    <View className="mt-5 rounded-3xl border border-white/10 bg-panel p-5">
      <AppText className="text-sm text-slate">Score</AppText>
      <View className="mt-1 flex-row items-end justify-between">
        <AppText weight="semibold" className="text-5xl" style={{ color: resultTone(stats.relativeToPar) }}>
          {relative.symbol}
        </AppText>
        <View className="items-end pb-1">
          <AppText weight="medium">{stats.totalStrokes} strokes</AppText>
          <AppText className="text-sm text-slate">Par {stats.totalPar}</AppText>
        </View>
      </View>
      <AppText className="mt-2 text-base">{relative.words}</AppText>
      <AppText className="mt-1 text-sm text-slate">
        {perHole.words} · {stats.completedHoles} holes
      </AppText>
    </View>
  );
}

function Tile({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View className="flex-1 rounded-2xl border border-white/10 bg-panel px-3 py-3">
      <AppText className="text-xs text-slate">{label}</AppText>
      <AppText weight="semibold" className="mt-1 text-xl">
        {value}
      </AppText>
      <AppText className="mt-1 text-xs text-slate">{hint}</AppText>
    </View>
  );
}

function Detail({ label, value, hint }: { label: string; value: string; hint: string }) {
  return (
    <View className="mb-3 rounded-2xl border border-white/10 bg-panel px-4 py-3">
      <AppText className="text-sm text-slate">{label}</AppText>
      <AppText weight="semibold" className="mt-1 text-base">
        {value}
      </AppText>
      <AppText className="mt-1 text-xs text-slate">{hint}</AppText>
    </View>
  );
}

function HistoryRow({ round, holes }: { round: Round; holes: HoleScore[] }) {
  const stats = summarizeHoles(holes.map(holeScoreToInput));
  const relative = stats.relativeToPar == null ? null : formatRelative(stats.relativeToPar);
  return (
    <Pressable
      accessibilityRole="button"
      onPress={() => router.push({ pathname: '/scorecard', params: { roundId: round.id } })}
      className="mb-3 rounded-2xl border border-white/10 bg-panel px-4 py-3"
    >
      <View className="flex-row items-center justify-between">
        <AppText weight="medium">{round.courseName}</AppText>
        <AppText weight="semibold">{relative ? relative.symbol : '—'}</AppText>
      </View>
      <AppText className="mt-1 text-sm text-slate">
        {formatWhen(round.startedAt)} · {round.teeSetName} tees ·{' '}
        {round.status === 'active' ? 'In progress' : 'Finished'}
        {round.sample ? ' · Sample' : ''}
        {stats.totalStrokes != null ? ` · ${stats.totalStrokes} strokes` : ''}
      </AppText>
    </Pressable>
  );
}
