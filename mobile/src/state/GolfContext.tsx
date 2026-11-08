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
import { buildSampleRounds } from '../data/seed';
import { getCourse } from '../data/courses';
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
import { angleVector, STARTER_BAG, type ClubCarry } from '../domain/caddie';
import { arBridge, defaultPreferences, simulatedDevice } from '../services/ar/bridge';
import { loadBag, loadNotes, saveBag, saveNote, saveSwingDocument, type Bag, type HoleNote } from '../services/golf/client';
import {
  analyzeSwingVideo,
  loadMeasurements,
  saveMeasurements,
  swingApiConfigured,
  type MeasurementRecord,
} from '../services/swing/measurement';

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
  measurements: Record<string, MeasurementRecord>;
  analyzeSwing: (videoId: string, videoUri: string) => Promise<void>;
  userId: string;
  bag: Bag;
  notes: HoleNote[];
  saveHoleNote: (note: HoleNote) => Promise<void>;
  updateBag: (clubs: ClubCarry[], handicapIndex: number | null) => Promise<void>;
  signOut: () => Promise<void>;
};

const GolfContext = createContext<GolfContextValue | null>(null);

const PREVIEW_ROUND = 'preview-round';

function PreviewGolf({ children }: { children: ReactNode }) {
  const course = getCourse('duck-creek-golf-club');
  const tee = course?.teeSets.find((item) => item.name === 'Blue') ?? course?.teeSets[0];
  const samples = useMemo(() => buildSampleRounds(), []);
  const [currentHole, setCurrentHole] = useState(1);
  const [status, setStatus] = useState<'active' | 'completed'>('active');
  const [name, setName] = useState('Preview');
  const [preferences, setPreferences] = useState<ARPreferences>({
    ...defaultPreferences,
    hud: { ...defaultPreferences.hud, showWind: true },
  });
  const [bag, setBag] = useState<Bag>({
    clubs: STARTER_BAG,
    handicapIndex: 12,
    starter: true,
    tendencies: { holes: 0, misses: {} },
  });
  const [notes, setNotes] = useState<HoleNote[]>([]);
  const [scores, setScores] = useState<Record<string, HoleScore[]>>(() => {
    const live: HoleScore[] = (tee?.holes ?? []).map((hole) => ({
      id: `${PREVIEW_ROUND}-${hole.number}`,
      roundId: PREVIEW_ROUND,
      holeNumber: hole.number,
      par: hole.par,
      yards: hole.yards,
      strokes: null,
      putts: null,
      penalties: null,
      fairwayHit: null,
      completed: false,
    }));
    const seeded: Record<string, HoleScore[]> = { [PREVIEW_ROUND]: live };
    for (const sample of buildSampleRounds()) seeded[sample.round.id] = sample.scores;
    return seeded;
  });

  const value = useMemo<GolfContextValue>(() => {
    const activeRound: Round | null = course && tee && status === 'active'
      ? {
          id: PREVIEW_ROUND,
          playerId: 'preview',
          courseId: course.id,
          courseName: course.name,
          teeSetId: tee.id,
          teeSetName: tee.name,
          nine: 'full',
          startedAt: new Date().toISOString(),
          completedAt: null,
          status: 'active',
          currentHole,
          sample: false,
        }
      : null;
    const rounds = [
      ...(course && tee
        ? [{
            id: PREVIEW_ROUND,
            playerId: 'preview',
            courseId: course.id,
            courseName: course.name,
            teeSetId: tee.id,
            teeSetName: tee.name,
            nine: 'full' as const,
            startedAt: new Date().toISOString(),
            completedAt: status === 'completed' ? new Date().toISOString() : null,
            status,
            currentHole,
            sample: false,
          }]
        : []),
      ...samples.map((sample) => sample.round),
    ];
    return {
      player: { id: 'preview', name, createdAt: new Date().toISOString() },
      rounds,
      scores,
      swings: [],
      preferences,
      recentCourseIds: ['duck-creek-golf-club'],
      activeRound,
      startRound: async (nextCourse, nextTee) => {
        setStatus('active');
        setCurrentHole(1);
        setScores((current) => ({
          ...current,
          [PREVIEW_ROUND]: nextTee.holes.map((hole) => ({
            id: `${PREVIEW_ROUND}-${hole.number}`,
            roundId: PREVIEW_ROUND,
            holeNumber: hole.number,
            par: hole.par,
            yards: hole.yards,
            strokes: null,
            putts: null,
            penalties: null,
            fairwayHit: null,
            completed: false,
          })),
        }));
        void nextCourse;
      },
      saveHoleScore: async (draft) => {
        setScores((current) => ({
          ...current,
          [draft.roundId]: (current[draft.roundId] ?? []).map((hole) =>
            hole.holeNumber === draft.holeNumber
              ? { ...hole, strokes: draft.strokes, putts: draft.putts, penalties: draft.penalties, fairwayHit: draft.fairwayHit, completed: true }
              : hole,
          ),
        }));
      },
      focusHole: async (_roundId, holeNumber) => setCurrentHole(holeNumber),
      endRound: async () => setStatus('completed'),
      noteCourse: async () => undefined,
      updatePlayerName: async (next) => setName(next.trim() || 'Preview'),
      updatePreferences: async (next) => setPreferences(next),
      setDeviceLinked: async (linked) => setPreferences((current) => ({ ...current, device: { ...current.device, linked } })),
      recordSwing: async () => undefined,
      removeSwing: async () => undefined,
      measurements: {},
      analyzeSwing: async () => undefined,
      userId: 'preview',
      bag,
      notes,
      saveHoleNote: async (note) => {
        setNotes((current) => [...current.filter((item) => item.roundId !== note.roundId || item.holeNumber !== note.holeNumber), note]);
      },
      updateBag: async (clubs, handicapIndex) => setBag({ clubs, handicapIndex, starter: false, tendencies: bag.tendencies }),
      signOut: async () => undefined,
    };
  }, [bag, course, currentHole, name, notes, preferences, samples, scores, status, tee]);

  return <GolfContext.Provider value={value}>{children}</GolfContext.Provider>;
}

export function GolfProvider({ children }: { children: ReactNode }) {
  if (process.env.EXPO_PUBLIC_PREVIEW === '1') return <PreviewGolf>{children}</PreviewGolf>;
  return <AccountGolf>{children}</AccountGolf>;
}

function AccountGolf({ children }: { children: ReactNode }) {
  const [session, setSession] = useState<Session | null | undefined>(undefined);
  const [snapshot, setSnapshot] = useState<Snapshot | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [measurements, setMeasurements] = useState<Record<string, MeasurementRecord>>({});
  const [bag, setBag] = useState<Bag>({ clubs: STARTER_BAG, handicapIndex: null, starter: true, tendencies: { holes: 0, misses: {} } });
  const [notes, setNotes] = useState<HoleNote[]>([]);

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

  useEffect(() => {
    let alive = true;
    loadMeasurements()
      .then((stored) => {
        if (alive) setMeasurements((current) => ({ ...stored, ...current }));
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, []);

  const runAnalysis = useCallback(async (videoId: string, videoUri: string, club: string) => {
    setMeasurements((current) => ({ ...current, [videoId]: { status: 'pending' } }));
    try {
      const measured = await analyzeSwingVideo(videoUri);
      const userId = session?.user.id;
      if (userId) {
        void saveSwingDocument({
          userId,
          videoId,
          club,
          angleVector: angleVector(measured.swings[0]?.events ?? []),
          measured,
        }).catch(() => undefined);
      }
      setMeasurements((current) => {
        const next = { ...current, [videoId]: { status: 'ready' as const, measured } };
        void saveMeasurements(next);
        return next;
      });
    } catch (analysisError) {
      const message = analysisError instanceof Error ? analysisError.message : 'Pose analysis failed.';
      setMeasurements((current) => {
        const next = { ...current, [videoId]: { status: 'failed' as const, message } };
        void saveMeasurements(next);
        return next;
      });
    }
  }, [session]);

  useEffect(() => {
    if (!session) return;
    let alive = true;
    loadBag(session.user.id)
      .then((next) => {
        if (alive) setBag(next);
      })
      .catch(() => undefined);
    loadNotes(session.user.id)
      .then((next) => {
        if (alive) setNotes(next);
      })
      .catch(() => undefined);
    return () => {
      alive = false;
    };
  }, [session]);

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
        const { videoId } = await recordRemoteSwing(input);
        await reload();
        if (swingApiConfigured()) void runAnalysis(videoId, input.videoUri, input.club);
      },
      removeSwing: async (swingId) => {
        const videoId = snapshot.swings.find((swing) => swing.id === swingId)?.videoId;
        await deleteRemoteSwing(swingId);
        if (videoId) {
          setMeasurements((current) => {
            const next = { ...current };
            delete next[videoId];
            void saveMeasurements(next);
            return next;
          });
        }
        await reload();
      },
      measurements,
      analyzeSwing: (videoId, videoUri) => runAnalysis(videoId, videoUri, 'Club'),
      userId: session?.user.id ?? '',
      bag,
      notes,
      saveHoleNote: async (note) => {
        setNotes((current) => {
          const rest = current.filter((item) => item.roundId !== note.roundId || item.holeNumber !== note.holeNumber);
          return [...rest, note];
        });
        if (session) await saveNote(session.user.id, note).catch(() => undefined);
      },
      updateBag: async (clubs, handicapIndex) => {
        if (!session) return;
        const next = await saveBag(session.user.id, clubs, handicapIndex);
        setBag(next);
      },
      signOut: async () => {
        await supabase.auth.signOut();
      },
    };
  }, [bag, notes, reload, runAnalysis, session, snapshot, measurements]);

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
