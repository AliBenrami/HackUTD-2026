import { useEffect, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { proReferences } from '../data/proReferences';
import { SWING_COMPARE_DISCLAIMER, type ComparableSwing } from '../domain/swingCompare';
import { requestPracticeCue, type CoachEvidence, type PracticeCue } from '../services/golf/client';
import { compareAndNarrate } from '../services/swing/narrator';
import { AppText } from './ui';

export function SwingCoach({ swing }: { swing: ComparableSwing }) {
  const { insights } = compareAndNarrate(swing, proReferences[0]);
  const evidence = insights
    .filter((insight) => insight.confidence === 'limited')
    .map(({ id, observation, why }) => ({ id, observation, why }));

  return <PracticeCard key={JSON.stringify(evidence)} evidence={evidence} />;
}

function PracticeCard({ evidence }: { evidence: CoachEvidence[] }) {
  const [decision, setDecision] = useState<PracticeCue | null>(null);
  const [status, setStatus] = useState<'idle' | 'loading' | 'done' | 'unavailable'>('idle');
  const pending = useRef<AbortController | null>(null);
  useEffect(() => () => {
    pending.current?.abort();
    pending.current = null;
  }, []);

  async function askCoach() {
    if (pending.current) return;
    const controller = new AbortController();
    pending.current = controller;
    setStatus('loading');
    const result = await requestPracticeCue(evidence, controller);
    if (pending.current !== controller) return;
    pending.current = null;
    setDecision(result);
    setStatus(result ? 'done' : 'unavailable');
  }

  const selected = evidence.find(({ id }) => id === decision?.evidenceId) ?? evidence[0];
  return (
    <View className="mt-5 rounded-3xl border border-white/10 bg-panel px-4 py-3">
      <AppText weight="semibold">Next practice cue</AppText>
      {selected ? (
        <>
          <AppText className="mt-2 text-xs text-slate">{decision ? 'NVIDIA Nemotron' : 'Swing comparison'}</AppText>
          <AppText className="mt-1 text-sm">
            {decision?.cue ?? 'Rehearse this part of the swing slowly, then compare it in your next recording.'}
          </AppText>
          <AppText className="mt-2 text-sm text-slate">{selected.observation}</AppText>
          <AppText className="mt-2 text-xs text-slate">{SWING_COMPARE_DISCLAIMER}</AppText>
          {status === 'unavailable' ? (
            <AppText className="mt-2 text-xs text-slate">Nemotron is unavailable. Showing the swing comparison cue.</AppText>
          ) : null}
          {status !== 'done' ? (
            <Pressable
              accessibilityRole="button"
              accessibilityState={{ disabled: status === 'loading', busy: status === 'loading' }}
              disabled={status === 'loading'}
              onPress={askCoach}
              className="min-h-11 self-start justify-center"
            >
              <AppText weight="semibold" className="text-cyan">
                {status === 'loading' ? 'Getting a cue…' : 'Get Nemotron cue'}
              </AppText>
            </Pressable>
          ) : null}
        </>
      ) : (
        <AppText className="mt-2 text-sm text-slate">This swing has no clear angle difference to coach from.</AppText>
      )}
    </View>
  );
}
