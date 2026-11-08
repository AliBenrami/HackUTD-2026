import AsyncStorage from '@react-native-async-storage/async-storage';
import { router } from 'expo-router';
import { useEffect, useMemo, useState } from 'react';
import { Pressable, ScrollView } from 'react-native';
import { ConsistencyChallenge } from '../components/ConsistencyChallenge';
import { BackHeader, Screen, AppText } from '../components/ui';
import { ballTraces } from '../data/ballTrace';
import { swingReview, type ReviewedSwing } from '../data/swingReview';
import { appendShotIds, challengeReport, classifySwing, timingOf, type SwingRole, type TimedSwing } from '../domain/swingSession';
import type { SwingSession } from '../domain/types';
import type { MeasurementRecord } from '../services/swing/measurement';
import { useGolf } from '../state/GolfContext';

const CHALLENGE_KEY = 'golfar.consistency.v1';

type ChallengeState = { active: boolean; shotIds: string[]; passedIds: string[] };

type CatalogSwing = TimedSwing & { role: SwingRole };

function fromReview(id: string, swing: ReviewedSwing, ball: readonly { x: number; y: number }[]): CatalogSwing {
  return { id, role: classifySwing({ events: swing.events, ball }), ...timingOf(swing.events) };
}

function catalog(saved: SwingSession[], measurements: Record<string, MeasurementRecord>): CatalogSwing[] {
  const range = swingReview.map((swing, index) => fromReview(`range:${swing.id}`, swing, ballTraces[index] ?? []));
  const seen = new Set<string>();
  const recorded: CatalogSwing[] = [];
  for (const session of saved) {
    if (seen.has(session.videoId)) continue;
    seen.add(session.videoId);
    const measured = measurements[session.videoId];
    if (measured?.status !== 'ready') continue;
    measured.measured.swings.forEach((swing) => {
      recorded.push(fromReview(`${session.videoId}:${swing.id}`, swing, swing.ball ?? []));
    });
  }
  return [...range, ...recorded];
}

export default function ChallengeScreen() {
  const { swings, measurements, bag } = useGolf();
  const saved = swings.filter((swing) => swing.source !== 'demo');
  const shots = useMemo(() => catalog(saved, measurements).filter((item) => item.role === 'shot'), [measurements, saved]);
  const shotKey = shots.map((item) => item.id).join('|');
  const [challenge, setChallenge] = useState<ChallengeState>({ active: false, shotIds: [], passedIds: [] });
  const [ready, setReady] = useState(false);

  useEffect(() => {
    let alive = true;
    AsyncStorage.getItem(CHALLENGE_KEY)
      .then((raw) => {
        if (!alive || !raw) return;
        const parsed = JSON.parse(raw) as Partial<ChallengeState>;
        setChallenge({
          active: parsed.active === true,
          shotIds: Array.isArray(parsed.shotIds) ? parsed.shotIds.filter((id) => typeof id === 'string') : [],
          passedIds: Array.isArray(parsed.passedIds) ? parsed.passedIds.filter((id) => typeof id === 'string') : [],
        });
      })
      .catch(() => undefined)
      .finally(() => {
        if (alive) setReady(true);
      });
    return () => {
      alive = false;
    };
  }, []);

  useEffect(() => {
    if (!ready) return;
    void AsyncStorage.setItem(CHALLENGE_KEY, JSON.stringify(challenge));
  }, [challenge, ready]);

  useEffect(() => {
    if (!challenge.active) return;
    const available = shotKey.length === 0 ? [] : shotKey.split('|');
    setChallenge((current) => {
      const shotIds = appendShotIds(current.shotIds, available);
      if (shotIds.join('|') === current.shotIds.join('|')) return current;
      return { ...current, shotIds };
    });
  }, [challenge.active, shotKey]);

  const counted = challenge.shotIds
    .map((id) => shots.find((item) => item.id === id))
    .filter((item): item is CatalogSwing => item != null);
  const report = challengeReport(counted);

  return (
    <Screen header={<BackHeader title="Five shots" onBack={() => router.back()} />}>
      <ConsistencyChallenge
        active={challenge.active}
        report={report}
        pairLabels={null}
        onStart={() => setChallenge({ active: true, shotIds: shots.map((item) => item.id), passedIds: [] })}
        onClear={() => setChallenge({ active: false, shotIds: [], passedIds: [] })}
        onReplay={() => router.navigate('/swing')}
        onPlayClip={() => router.navigate('/swing')}
      />
      <AppText weight="semibold" className="mb-3">
        Record a shot
      </AppText>
      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8 }}>
        {bag.clubs.map((club) => (
          <Pressable
            key={club.name}
            accessibilityRole="button"
            onPress={() => router.push({ pathname: '/record', params: { club: club.name } })}
            className="min-h-14 justify-center rounded-2xl border border-white/10 bg-panel px-4"
          >
            <AppText weight="semibold">{club.name}</AppText>
            <AppText className="text-xs text-slate">{club.carry} yds</AppText>
          </Pressable>
        ))}
      </ScrollView>
    </Screen>
  );
}
