import type { Session } from '@supabase/supabase-js';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { View } from 'react-native';
import { AuthScreen } from '../components/AuthScreen';
import { AppText } from '../components/ui';
import { holeScoreToInput, summarizeHoles } from '../domain/scoring';
import type {
  ARPreferences,
  Course,
  HoleScore,
  NineSelection,
  Player,
  Round,
  SwingSession,
  TeeSet,
} from '../domain/types';
import type { HoleDraft, Snapshot } from '../data/repository';
import {
  deleteRemoteSwing,
  finishRemoteRound,
  loadRemoteSnapshot,
  recordRemoteSwing,
  rememberRemoteCourse,
  renameRemotePlayer,
  saveRemoteHole,
  saveRemotePreferences,
  setRemoteHole,
  startRemoteRound,
} from '../data/remote';
import { supabase } from '../lib/supabase';
import { arBridge, simulatedDevice } from '../services/ar/bridge';

type GolfContextValue = {
  player: Player;
  rounds: Round[];
  scores: Record<string, HoleScore[]>;
  swings: SwingSession[];
  preferences: ARPreferences;
  recentCourseIds: string[];
  activeRound: Round | null;
  startRound: (course: Course, tee: TeeSet, nine: NineSelection) => Promise<void>;
  saveHoleScore: (draft: HoleDraft) => Promise<void>;
  focusHole: (roundId: string, holeNumber: number) => Promise<void>;
  endRound: (roundId: string) => Promise<void>;
  noteCourse: (courseId: string) => Promise<void>;
  updatePlayerName: (name: string) => Promise<void>;
  updatePreferences: (preferences: ARPreferences) => Promise<void>;
  setDeviceLinked: (linked: boolean) => Promise<void>;
  recordSwing: (input: { source: 'camera' | 'import'; videoUri: string; club: string }) => Promise<void>;
  removeSwing: (swingId: string) => Promise<void>;
  signOut: () => Promise<void>;
};

const GolfContext = createContext<GolfContextValue | null>(null);

export function GolfProvider({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    supabase.auth.getSession().then(({ data }) => {
      if (alive) setSession(data.session);
    });
    const { data } = supabase.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      if (!next) setSnapshot(null);
    });
    return () => {
      alive = false;
      data.subscription.unsubscribe();
    };
  }, []);

  const reload = useCallback(async () => {
    const { data } = await supabase.auth.getSession();
    if (!data.session) return;
    setSnapshot(await loadRemoteSnapshot(data.session));
  }, []);

  useEffect(() => {
    if (!session) return;
    let alive = true;
    loadRemoteSnapshot(session)
      .then((next) => {
        if (alive) setSnapshot(next);
      })
      .catch((loadError: unknown) => {
        if (alive) {
          setError(loadError instanceof Error ? loadError.message : 'The saved rounds could not be read.');
        }
      });
    return () => {
      alive = false;
    };
  }, [session]);

  const value = useMemo<GolfContextValue | null>(() => {
    if (!snapshot) return null;
    const activeRound = snapshot.rounds.find((round) => round.status === 'active') ?? null;
    return {
      ...snapshot,
      activeRound,
      startRound: async (course, tee, nine) => {
        await startRemoteRound({ courseId: course.id, teeSetId: tee.id, nine });
        await reload();
      },
      saveHoleScore: async (draft) => {
        await saveRemoteHole(draft);
        const holes = snapshot.scores[draft.roundId] ?? [];
        const hole = holes.find((item) => item.holeNumber === draft.holeNumber);
        const nextHoles = holes.map((item) =>
          item.holeNumber === draft.holeNumber
            ? {
                ...item,
                strokes: draft.strokes,
                putts: draft.putts,
                penalties: draft.penalties,
                fairwayHit: hole?.par === 3 ? null : draft.fairwayHit,
                completed: true,
              }
            : item,
        );
        const stats = summarizeHoles(nextHoles.map(holeScoreToInput));
        const round = snapshot.rounds.find((item) => item.id === draft.roundId);
        if (round && hole) {
          const result = await arBridge.pushScore(
            {
              version: 1,
              roundId: round.id,
              courseId: round.courseId,
              holeNumber: draft.holeNumber,
              strokes: draft.strokes,
              par: hole.par,
              relativeToPar: draft.strokes - hole.par,
              roundRelativeToPar: stats.relativeToPar,
              updatedAt: new Date().toISOString(),
            },
            snapshot.preferences,
          );
          if (result.accepted && result.syncedAt) {
            await saveRemotePreferences({ ...snapshot.preferences, lastSyncAt: result.syncedAt });
          }
        }
        await reload();
      },
      focusHole: async (roundId, holeNumber) => {
        await setRemoteHole(roundId, holeNumber);
        await reload();
      },
      endRound: async (roundId) => {
        await finishRemoteRound(roundId);
        await reload();
      },
      noteCourse: async (courseId) => {
        await rememberRemoteCourse(courseId);
        await reload();
      },
      updatePlayerName: async (name) => {
        await renameRemotePlayer(name);
        await reload();
      },
      updatePreferences: async (preferences) => {
        await saveRemotePreferences(preferences);
        await reload();
      },
      setDeviceLinked: async (linked) => {
        await saveRemotePreferences({
          ...snapshot.preferences,
          device: simulatedDevice(linked),
          lastSyncAt: linked ? snapshot.preferences.lastSyncAt : null,
        });
        await reload();
      },
      recordSwing: async (input) => {
        await recordRemoteSwing(input);
        await reload();
      },
      removeSwing: async (swingId) => {
        await deleteRemoteSwing(swingId);
        await reload();
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    };
  }, [reload, snapshot]);

  if (error) {
    return (
      <View className="flex-1 items-center justify-center bg-ink px-8">
        <AppText weight="semibold" className="text-center text-xl">
          Saved rounds could not be opened.
        </AppText>
        <AppText className="mt-3 text-center text-sm text-slate">{error}</AppText>
      </View>
    );
  }

  if (session === undefined || (session && !value && !error)) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <AppText className="text-slate">Loading rounds…</AppText>
      </View>
    );
  }

  if (!session) {
    return <AuthScreen />;
  }

  if (!value) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <AppText className="text-slate">Loading rounds…</AppText>
      </View>
    );
  }
  return <GolfContext.Provider value={value}>{children}</GolfContext.Provider>;
}

export function useGolf(): GolfContextValue {
  const value = useContext(GolfContext);
  if (!value) throw new Error('useGolf must be used inside GolfProvider');
  return value;
}
