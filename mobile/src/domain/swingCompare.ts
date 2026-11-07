/**
 * Compares a mapped swing with a professional reference model.
 *
 * Elbow figures are included angles: 180° is straight, and a smaller number is more bent.
 * Analyzed swings are compared as right-handed, so the left arm is the lead arm.
 * A future pose model should emit these phase names and the same angles.
 * Copy for the screen comes from a narrator (template today, LLM later) so the
 * measurements and the wording can change independently.
 */

export const COMPARE_PHASES = [
  'Address',
  'Toe-up',
  'Mid-backswing',
  'Top',
  'Mid-downswing',
  'Impact',
  'Mid-follow-through',
  'Finish',
] as const;

export const SWING_COMPARE_DISCLAIMER =
  'This is an observation based on your pose angles and a reference model. There is no guaranteed certainty.';

/** Same bar the swing screen uses for a low phase score. */
export const PHASE_SCORE_CUTOFF = 0.6;

const MIN_GAP = 15;
const EXTREME_GAP = 40;
const MIN_ELBOW = 55;
const MAX_ELBOW = 180;
export const INSIGHT_LIMIT = 3;

export type SwingMetricKey = 'leadElbow' | 'trailElbow';

export type AngleBand = {
  typical: number;
  low: number;
  high: number;
};

export type ProPhase = {
  name: string;
  angles: Partial<Record<SwingMetricKey, AngleBand>>;
};

export type MetricExplanation = {
  userMoreBent: string;
  userStraighter: string;
};

export type ProReference = {
  id: string;
  name: string;
  kind: 'reference-model';
  summary: string;
  sourceNote: string;
  /** Ranked ahead of other gaps when choosing which observations to show. */
  emphasis: readonly SwingMetricKey[];
  phases: readonly ProPhase[];
  explanations?: Partial<Record<SwingMetricKey, Partial<MetricExplanation>>>;
};

export type ComparableSwing = {
  id: number;
  events: Array<{
    name: string;
    score: number;
    tentative: boolean;
    angles: {
      leftElbow: number | null;
      rightElbow: number | null;
    };
  }>;
};

export type MetricStatus = 'inside' | 'outside' | 'unusable' | 'missing';

export type MetricComparison = {
  key: SwingMetricKey;
  label: string;
  user: number | null;
  typical: number | null;
  low: number | null;
  high: number | null;
  delta: number | null;
  status: MetricStatus;
};

export type PhaseComparison = {
  phase: string;
  score: number;
  tentative: boolean;
  metrics: MetricComparison[];
};

export type ComparisonPacket = {
  version: 1;
  userSwingId: number;
  handedness: 'right';
  referenceId: string;
  referenceKind: 'reference-model';
  disclaimer: string;
  phases: PhaseComparison[];
};

export type InsightCaveat = 'tentative' | 'low-score' | 'large-gap';

export type NotableRow = {
  phase: string;
  metric: SwingMetricKey;
  label: string;
  user: number;
  typical: number;
  low: number;
  high: number;
  delta: number;
  gap: number;
  phaseScore: number;
  tentative: boolean;
  confidence: 'limited' | 'low';
  caveat: InsightCaveat | null;
  /** True when the degree gap is large enough that the pose estimate may be off. */
  extreme: boolean;
  direction: 'more-bent' | 'straighter';
};

export type SwingInsight = {
  id: string;
  phase: string;
  metric: SwingMetricKey;
  title: string;
  observation: string;
  why: string;
  confidence: 'limited' | 'low';
  caveat: InsightCaveat | null;
  disclaimer: string;
  gap: number;
};

export type LlmInsightRequest = {
  version: 1;
  task: string;
  disclaimer: string;
  assumptions: string[];
  reference: {
    id: string;
    name: string;
    kind: 'reference-model';
    sourceNote: string;
  };
  rows: Array<NotableRow & { whyHint: string }>;
};

const METRICS: ReadonlyArray<{ key: SwingMetricKey; label: string; side: 'leftElbow' | 'rightElbow' }> = [
  { key: 'leadElbow', label: 'Lead elbow', side: 'leftElbow' },
  { key: 'trailElbow', label: 'Trail elbow', side: 'rightElbow' },
];

const DEFAULT_EXPLANATIONS: Record<SwingMetricKey, MetricExplanation> = {
  leadElbow: {
    userMoreBent:
      'This reference keeps the lead arm longer here. Extra bend shortens the arc the club travels on, and a deep fold is the part that stands out.',
    userStraighter:
      'This reference keeps a little bend in the lead arm, enough to deliver the club while the joint stays soft. A side camera can also make an arm look straighter than it is.',
  },
  trailElbow: {
    userMoreBent:
      'This reference keeps a moderate bend so the elbow stays tucked toward the ribs, which can help the club shallow on the way down. The angle is elbow bend, a stand-in for how close the arm sits to the body.',
    userStraighter:
      'This reference bends the trail elbow more, the tucked arm with the elbow closer to the ribcage. That tuck can help the club stay shallow, and the angle only stands in for the gap to the body.',
  },
};

const PHASE_PHRASE: Record<string, string> = {
  Address: 'at address',
  'Toe-up': 'at toe-up',
  'Mid-backswing': 'in the mid-backswing',
  Top: 'at the top',
  'Mid-downswing': 'in the mid-downswing',
  Impact: 'at impact',
  'Mid-follow-through': 'in the follow-through',
  Finish: 'at the finish',
};

export function phasePhrase(phase: string) {
  return PHASE_PHRASE[phase] ?? `at ${phase}`;
}

export function gapPhrase(delta: number, inside: boolean) {
  const amount = Math.round(Math.abs(delta));
  if (amount === 0) return 'Matches the reference';
  const direction = delta < 0 ? 'more bent' : 'straighter';
  return inside ? `${amount}° ${direction} · inside the band` : `${amount}° ${direction}`;
}

function usableElbow(value: number | null): value is number {
  return value != null && Number.isFinite(value) && value >= MIN_ELBOW && value <= MAX_ELBOW;
}

function caveatFor(score: number, tentative: boolean, gap: number): InsightCaveat | null {
  if (tentative) return 'tentative';
  if (score < PHASE_SCORE_CUTOFF) return 'low-score';
  if (gap > EXTREME_GAP) return 'large-gap';
  return null;
}

export function compareSwing(swing: ComparableSwing, reference: ProReference): ComparisonPacket {
  const byPhase = new Map(reference.phases.map((phase) => [phase.name, phase]));
  return {
    version: 1,
    userSwingId: swing.id,
    handedness: 'right',
    referenceId: reference.id,
    referenceKind: reference.kind,
    disclaimer: SWING_COMPARE_DISCLAIMER,
    phases: swing.events.map((event) => {
      const referencePhase = byPhase.get(event.name);
      return {
        phase: event.name,
        score: event.score,
        tentative: event.tentative,
        metrics: METRICS.map((metric) => {
          const band = referencePhase?.angles[metric.key];
          const user = event.angles[metric.side];
          if (!band || user == null) {
            return {
              key: metric.key,
              label: metric.label,
              user,
              typical: band?.typical ?? null,
              low: band?.low ?? null,
              high: band?.high ?? null,
              delta: null,
              status: 'missing' as const,
            };
          }
          if (!usableElbow(user)) {
            return {
              key: metric.key,
              label: metric.label,
              user,
              typical: band.typical,
              low: band.low,
              high: band.high,
              delta: null,
              status: 'unusable' as const,
            };
          }
          const delta = user - band.typical;
          const inside = user >= band.low && user <= band.high;
          return {
            key: metric.key,
            label: metric.label,
            user,
            typical: band.typical,
            low: band.low,
            high: band.high,
            delta,
            status: inside ? ('inside' as const) : ('outside' as const),
          };
        }),
      };
    }),
  };
}

export function notableRows(packet: ComparisonPacket, reference: ProReference): NotableRow[] {
  const rows: NotableRow[] = [];
  for (const phase of packet.phases) {
    for (const metric of phase.metrics) {
      if (metric.status !== 'outside' || metric.user == null || metric.delta == null || metric.typical == null || metric.low == null || metric.high == null) {
        continue;
      }
      const gap = Math.abs(metric.delta);
      if (gap < MIN_GAP) continue;
      const caveat = caveatFor(phase.score, phase.tentative, gap);
      rows.push({
        phase: phase.phase,
        metric: metric.key,
        label: metric.label,
        user: metric.user,
        typical: metric.typical,
        low: metric.low,
        high: metric.high,
        delta: metric.delta,
        gap,
        phaseScore: phase.score,
        tentative: phase.tentative,
        confidence: caveat == null ? 'limited' : 'low',
        caveat,
        extreme: gap > EXTREME_GAP,
        direction: metric.delta < 0 ? 'more-bent' : 'straighter',
      });
    }
  }
  const emphasis = new Set(reference.emphasis);
  rows.sort((a, b) => {
    const tier = Number(a.confidence === 'low') - Number(b.confidence === 'low');
    if (tier !== 0) return tier;
    const featured = Number(!emphasis.has(a.metric)) - Number(!emphasis.has(b.metric));
    if (featured !== 0) return featured;
    return b.gap - a.gap;
  });
  return rows;
}

export function whyFor(reference: ProReference, row: NotableRow) {
  const custom = reference.explanations?.[row.metric];
  const base = DEFAULT_EXPLANATIONS[row.metric];
  if (row.direction === 'more-bent') return custom?.userMoreBent ?? base.userMoreBent;
  return custom?.userStraighter ?? base.userStraighter;
}

export function observationText(reference: ProReference, row: NotableRow) {
  const who = reference.name.split(' ')[0];
  const amount = Math.round(row.gap);
  const direction = row.direction === 'more-bent' ? 'more bent' : 'straighter';
  const estimate = row.extreme ? ' A gap this large can also come from the pose estimate.' : '';
  return `Your ${row.label.toLowerCase()} reads ${row.user.toFixed(1)}° ${phasePhrase(row.phase)}. ${who}'s reference is about ${Math.round(row.typical)}°. Yours is ${amount}° ${direction}.${estimate}`;
}

export function narrateComparison(packet: ComparisonPacket, reference: ProReference): SwingInsight[] {
  return notableRows(packet, reference)
    .slice(0, INSIGHT_LIMIT)
    .map((row) => ({
      id: `${reference.id}:${row.phase}:${row.metric}`,
      phase: row.phase,
      metric: row.metric,
      title: `${row.label} ${phasePhrase(row.phase)}`,
      observation: observationText(reference, row),
      why: whyFor(reference, row),
      confidence: row.confidence,
      caveat: row.caveat,
      disclaimer: packet.disclaimer,
      gap: row.gap,
    }));
}

/**
 * Structured input for a later model. It carries angles and the reference note,
 * and it leaves out video, joint coordinates, and club boxes.
 */
export function buildLlmInsightRequest(packet: ComparisonPacket, reference: ProReference): LlmInsightRequest {
  return {
    version: 1,
    task: 'Rewrite each row as an observation and a short reason. Keep the degrees. Say there is no guaranteed certainty. Do not promise a better score, and do not give medical advice.',
    disclaimer: packet.disclaimer,
    assumptions: [
      'The swing is compared as right-handed, so the left arm is the lead arm.',
      'Elbow figures are included angles. 180° is straight.',
      'Reference values are a model, not a captured swing from this player.',
    ],
    reference: {
      id: reference.id,
      name: reference.name,
      kind: reference.kind,
      sourceNote: reference.sourceNote,
    },
    rows: notableRows(packet, reference).map((row) => ({
      ...row,
      whyHint: whyFor(reference, row),
    })),
  };
}
