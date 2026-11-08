import { useState } from 'react';
import { Pressable, ScrollView, StyleSheet, View } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';
import { proReference, proReferences } from '../data/proReferences';
import type { ReviewedSwing } from '../data/swingReview';
import { SWING_COMPARE_DISCLAIMER, type MetricComparison } from '../domain/swingCompare';
import { compareAndNarrate } from '../services/swing/narrator';
import { colors } from '../theme/colors';
import { AppText } from './ui';

export function SwingCompare({ swing, phaseName }: { swing: ReviewedSwing; phaseName: string }) {
  const [proId, setProId] = useState(proReferences[0].id);
  const reference = proReference(proId);
  const { packet } = compareAndNarrate(swing, reference);
  const phase = packet.phases.find((item) => item.phase === phaseName) ?? packet.phases[0];
  const lead = phase?.metrics.find((metric) => metric.key === 'leadElbow') ?? null;
  const trail = phase?.metrics.find((metric) => metric.key === 'trailElbow') ?? null;
  const focus = biggestGap([lead, trail].filter((metric): metric is MetricComparison => metric != null));
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
      {phase ? (
        <View className="mt-4 flex-row gap-2">
          <FigureCard
            title="You"
            phase={phase.phase}
            lead={lead?.user ?? null}
            trail={trail?.user ?? null}
            focus={focus?.key ?? null}
            tone="you"
          />
          <FigureCard
            title={who}
            phase={phase.phase}
            lead={lead?.typical ?? null}
            trail={trail?.typical ?? null}
            focus={focus?.key ?? null}
            tone="pro"
          />
        </View>
      ) : null}

      <View className="mt-3 rounded-3xl border border-white/10 bg-panel px-4 py-3">
        <AppText weight="semibold">Do better</AppText>
        <AppText className="mt-1 text-sm">{betterLine(focus, who)}</AppText>
        <AppText className="mt-2 text-xs text-slate">{SWING_COMPARE_DISCLAIMER}</AppText>
      </View>
    </View>
  );
}

function FigureCard({
  title,
  phase,
  lead,
  trail,
  focus,
  tone,
}: {
  title: string;
  phase: string;
  lead: number | null;
  trail: number | null;
  focus: 'leadElbow' | 'trailElbow' | null;
  tone: 'you' | 'pro';
}) {
  return (
    <View className="flex-1 rounded-3xl border border-white/10 bg-panel px-2 pb-3 pt-3">
      <AppText weight="semibold" className="text-center text-sm">
        {title}
      </AppText>
      <View style={{ height: 168 }}>
        <ArmFigure phase={phase} lead={lead} trail={trail} focus={focus} tone={tone} />
      </View>
      <AppText className={`mt-1 text-center text-xs ${focus === 'leadElbow' ? 'text-cyan' : 'text-slate'}`}>
        {`Lead ${lead == null ? '—' : `${Math.round(lead)}°`}`}
      </AppText>
      <AppText className={`mt-0.5 text-center text-xs ${focus === 'trailElbow' ? 'text-cyan' : 'text-slate'}`}>
        {`Trail ${trail == null ? '—' : `${Math.round(trail)}°`}`}
      </AppText>
    </View>
  );
}

function biggestGap(metrics: MetricComparison[]): MetricComparison | null {
  const ranked = metrics.filter((metric) => metric.delta != null && metric.status === 'outside');
  ranked.sort((left, right) => Math.abs(right.delta ?? 0) - Math.abs(left.delta ?? 0));
  return ranked[0] ?? null;
}

function betterLine(metric: MetricComparison | null, who: string) {
  if (!metric || metric.delta == null) return `This position sits with ${who}. Nothing stands out to change.`;
  const amount = Math.round(Math.abs(metric.delta));
  if (amount < 8) return `This position sits with ${who}. Nothing stands out to change.`;
  if (metric.key === 'trailElbow') {
    return metric.delta < 0
      ? `Open the trail elbow about ${amount}°. ${who} is less tucked here.`
      : `Bend the trail elbow about ${amount}° so it stays closer to your side, the way ${who} does.`;
  }
  return metric.delta < 0
    ? `Straighten the lead arm about ${amount}°. ${who} holds a wider arc here.`
    : `Soften the lead arm about ${amount}°. ${who} keeps a little bend here.`;
}

type Point = { x: number; y: number };

const ARM_AIM: Record<string, { lead: number; trail: number }> = {
  Address: { lead: 108, trail: 72 },
  'Toe-up': { lead: 35, trail: 78 },
  'Mid-backswing': { lead: -10, trail: 25 },
  Top: { lead: -95, trail: -25 },
  'Mid-downswing': { lead: 25, trail: 55 },
  Impact: { lead: 102, trail: 68 },
  'Mid-follow-through': { lead: 190, trail: 150 },
  Finish: { lead: 235, trail: 205 },
};

function pointFrom(origin: Point, degrees: number, length: number): Point {
  const rad = (degrees * Math.PI) / 180;
  return { x: origin.x + Math.cos(rad) * length, y: origin.y + Math.sin(rad) * length };
}

function forearm(shoulder: Point, elbow: Point, angle: number): Point {
  const bend = ((180 - Math.min(180, Math.max(55, angle))) * Math.PI) / 180;
  const upper = Math.atan2(elbow.y - shoulder.y, elbow.x - shoulder.x);
  const towardBody = elbow.x <= 50 ? 1 : -1;
  const aim = upper + towardBody * bend;
  return { x: elbow.x + Math.cos(aim) * 16, y: elbow.y + Math.sin(aim) * 16 };
}

function ArmFigure({
  phase,
  lead,
  trail,
  focus,
  tone,
}: {
  phase: string;
  lead: number | null;
  trail: number | null;
  focus: 'leadElbow' | 'trailElbow' | null;
  tone: 'you' | 'pro';
}) {
  const aim = ARM_AIM[phase] ?? ARM_AIM.Address;
  const leadShoulder = { x: 40, y: 42 };
  const trailShoulder = { x: 60, y: 42 };
  const leadElbow = pointFrom(leadShoulder, aim.lead, 22);
  const trailElbow = pointFrom(trailShoulder, aim.trail, 22);
  const leadWrist = lead == null ? null : forearm(leadShoulder, leadElbow, lead);
  const trailWrist = trail == null ? null : forearm(trailShoulder, trailElbow, trail);
  const bone = tone === 'you' ? colors.cyan : colors.mist;
  const hot = colors.magenta;

  return (
    <Svg viewBox="0 0 100 120" width="100%" height="100%">
      <Line x1={50} y1={28} x2={50} y2={74} stroke={bone} strokeWidth={2.2} strokeLinecap="round" />
      <Line x1={40} y1={42} x2={60} y2={42} stroke={bone} strokeWidth={2.2} strokeLinecap="round" />
      <Circle cx={50} cy={20} r={7} fill={bone} />
      <Arm shoulder={leadShoulder} elbow={leadElbow} wrist={leadWrist} color={focus === 'leadElbow' ? hot : bone} />
      <Arm shoulder={trailShoulder} elbow={trailElbow} wrist={trailWrist} color={focus === 'trailElbow' ? hot : bone} />
      {leadWrist && trailWrist ? (
        <Line
          x1={(leadWrist.x + trailWrist.x) / 2}
          y1={(leadWrist.y + trailWrist.y) / 2}
          x2={(leadWrist.x + trailWrist.x) / 2 + (leadWrist.x - leadElbow.x) * 0.7}
          y2={(leadWrist.y + trailWrist.y) / 2 + (leadWrist.y - leadElbow.y) * 0.7}
          stroke={colors.violet}
          strokeWidth={1.6}
          strokeLinecap="round"
        />
      ) : null}
    </Svg>
  );
}

function Arm({ shoulder, elbow, wrist, color }: { shoulder: Point; elbow: Point; wrist: Point | null; color: string }) {
  return (
    <>
      <Line x1={shoulder.x} y1={shoulder.y} x2={elbow.x} y2={elbow.y} stroke={color} strokeWidth={2.4} strokeLinecap="round" />
      {wrist ? <Line x1={elbow.x} y1={elbow.y} x2={wrist.x} y2={wrist.y} stroke={color} strokeWidth={2.4} strokeLinecap="round" /> : null}
      <Circle cx={elbow.x} cy={elbow.y} r={2.3} fill={color} />
    </>
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
});
