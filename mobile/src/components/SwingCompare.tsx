import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import { proReference, proReferences } from '../data/proReferences';
import type { ReviewedSwing } from '../data/swingReview';
import { gapPhrase, SWING_COMPARE_DISCLAIMER, type MetricComparison, type SwingInsight } from '../domain/swingCompare';
import { compareAndNarrate } from '../services/swing/narrator';
import { colors } from '../theme/colors';
import { AppText } from './ui';

const CAVEAT_LABEL = {
  tentative: 'Uncertain · tentative phase',
  'low-score': 'Uncertain · low phase score',
  'large-gap': 'Uncertain · large gap',
} as const;

function degrees(value: number | null) {
  return value == null ? 'Unavailable' : `${value.toFixed(1)}°`;
}

function referenceDegrees(value: number | null) {
  return value == null ? 'Unavailable' : `${Math.round(value)}°`;
}

export function SwingCompare({ swing, phaseName }: { swing: ReviewedSwing; phaseName: string }) {
  const [proId, setProId] = useState(proReferences[0].id);
  const reference = proReference(proId);
  const { packet, insights } = compareAndNarrate(swing, reference);
  const phase = packet.phases.find((item) => item.phase === phaseName) ?? packet.phases[0];
  const ordered = [
    ...insights.filter((insight) => insight.phase === phaseName),
    ...insights.filter((insight) => insight.phase !== phaseName),
  ];
  const who = reference.name.split(' ')[0];

  return (
    <View className="mt-6">
      <AppText weight="semibold" className="text-lg">
        Compare
      </AppText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.row}>
        {proReferences.map((item) => {
          const selected = item.id === reference.id;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="button"
              accessibilityLabel={`Compare with ${item.name}`}
              accessibilityState={{ selected }}
              onPress={() => setProId(item.id)}
              style={[styles.chip, selected && styles.chipSelected]}
            >
              <AppText weight="semibold" className="text-sm" style={{ color: selected ? colors.ink : colors.mist }}>
                {item.name}
              </AppText>
            </Pressable>
          );
        })}
      </ScrollView>
      <AppText className="mt-3 text-sm text-slate">{reference.summary}</AppText>
      <AppText className="mt-1 text-xs text-slate">{reference.sourceNote}</AppText>

      {phase ? (
        <View className="mt-4">
          <View className="min-h-9 flex-row items-center">
            <AppText className="flex-1 text-slate">{phase.phase}</AppText>
            <AppText className="w-20 text-right text-slate">You</AppText>
            <AppText className="w-20 text-right text-slate">{who}</AppText>
          </View>
          {phase.metrics.map((metric) => (
            <MetricRow key={metric.key} metric={metric} />
          ))}
          <AppText className="mt-2 text-xs text-slate">
            Lead is the left arm on this right-handed comparison. 180° is straight. Knees and torso stay in the reading above.
          </AppText>
        </View>
      ) : null}

      <AppText weight="semibold" className="mt-5">
        Observations
      </AppText>
      <AppText className="mt-1 text-sm text-slate">{SWING_COMPARE_DISCLAIMER}</AppText>
      {ordered.length === 0 ? (
        <AppText className="mt-3 text-sm text-slate">
          These angles sit inside the reference band, so there is nothing further to call out.
        </AppText>
      ) : (
        <View className="mt-3" style={styles.notes}>
          {ordered.map((insight) => (
            <InsightCard key={insight.id} insight={insight} active={insight.phase === phaseName} />
          ))}
        </View>
      )}
    </View>
  );
}

function MetricRow({ metric }: { metric: MetricComparison }) {
  const userText = metric.status === 'unusable' ? 'Unusable' : degrees(metric.user);
  const gap =
    metric.delta == null || (metric.status !== 'inside' && metric.status !== 'outside')
      ? null
      : gapPhrase(metric.delta, metric.status === 'inside');
  const quiet = metric.status === 'unusable' || metric.status === 'missing';
  return (
    <View className="border-t border-white/10 py-2.5">
      <View className="flex-row items-center">
        <AppText className="flex-1">{metric.label}</AppText>
        <AppText className={`w-20 text-right ${quiet ? 'text-slate' : ''}`}>{userText}</AppText>
        <AppText className="w-20 text-right">{referenceDegrees(metric.typical)}</AppText>
      </View>
      {gap ? <AppText className="mt-1 text-right text-sm text-slate">{gap}</AppText> : null}
    </View>
  );
}

function InsightCard({ insight, active }: { insight: SwingInsight; active: boolean }) {
  const tag = insight.caveat ? CAVEAT_LABEL[insight.caveat] : 'Uncertain';
  return (
    <View style={[styles.card, active && styles.cardActive]}>
      <AppText weight="semibold">{insight.title}</AppText>
      <AppText className="mt-1 text-xs text-slate">{tag}</AppText>
      <AppText className="mt-2 text-sm">{insight.observation}</AppText>
      <AppText className="mt-2 text-sm text-slate">{insight.why}</AppText>
    </View>
  );
}

const styles = StyleSheet.create({
  row: { gap: 8, paddingTop: 12 },
  chip: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(243,246,250,0.16)',
    backgroundColor: colors.panel,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  chipSelected: {
    backgroundColor: colors.cyan,
    borderColor: colors.cyan,
  },
  notes: { gap: 10 },
  card: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(243,246,250,0.08)',
    backgroundColor: colors.panel,
    paddingHorizontal: 14,
    paddingVertical: 12,
  },
  cardActive: {
    borderColor: colors.cyan,
  },
});
