import { Pressable, View } from 'react-native';
import type { ChallengeReport } from '../domain/swingSession';
import { AppText, Button } from './ui';

export function ConsistencyChallenge({
  active,
  report,
  pairLabels,
  onStart,
  onClear,
  onReplay,
  onPlayClip,
}: {
  active: boolean;
  report: ChallengeReport;
  pairLabels: { a: string; b: string } | null;
  onStart: () => void;
  onClear: () => void;
  onReplay: () => void;
  onPlayClip: () => void;
}) {
  const filled = Math.min(report.counted, report.limit);

  return (
    <View className="mb-5 rounded-3xl border border-white/10 bg-panel p-4">
      <View className="flex-row items-end justify-between">
        <AppText weight="semibold" className="text-lg">
          Five shots
        </AppText>
        <AppText weight="semibold" className="text-sm text-cyan">
          {filled}/{report.limit}
        </AppText>
      </View>
      <View className="mt-3 flex-row gap-1.5">
        {Array.from({ length: report.limit }, (_, index) => (
          <View key={index} className={`h-1.5 flex-1 rounded-full ${index < filled ? 'bg-cyan' : 'bg-white/10'}`} />
        ))}
      </View>
      <AppText className="mt-3 text-sm text-slate">
        Match your setup and the time from address to impact. A practice swing stays out.
      </AppText>

      {active && (report.timing || report.setupSpread != null) ? (
        <View className="mt-3 flex-row gap-2">
          {report.timing ? (
            <Metric label="Timing" value={`${report.timing.spread.toFixed(2)}s`} />
          ) : null}
          {report.setupSpread != null ? <Metric label="Setup" value={`${report.setupSpread.toFixed(1)}°`} /> : null}
        </View>
      ) : null}

      {active && pairLabels && report.pair ? (
        <AppText className="mt-3 text-sm text-slate">
          {pairLabels.a} and {pairLabels.b} are the farthest apart.
        </AppText>
      ) : null}

      <View className="mt-4 gap-2">
        {active && pairLabels ? <Button label="Play those two" onPress={onReplay} /> : null}
        {active ? null : <Button label="Start challenge" onPress={onStart} />}
        <Button label="Play the range clip" onPress={onPlayClip} variant={active && !pairLabels ? 'primary' : 'secondary'} />
      </View>
      <AppText className="mt-2 text-xs text-slate">Swing 1 in the clip is practice. Swing 2 is a shot.</AppText>

      {active ? (
        <Pressable accessibilityRole="button" onPress={onClear} className="mt-3 min-h-11 items-center justify-center">
          <AppText weight="medium" className="text-sm text-slate">
            Clear challenge
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

function Metric({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-1 rounded-2xl bg-white/5 px-3 py-2">
      <AppText className="text-xs text-slate">{label}</AppText>
      <AppText weight="semibold" className="mt-0.5 text-base">
        {value}
      </AppText>
    </View>
  );
}
