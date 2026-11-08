import { router } from 'expo-router';
import { ChevronLeft, ChevronRight, Minus, Plus } from 'lucide-react-native';
import { useCallback, useEffect, useRef, useState, type ReactNode } from 'react';
import { Alert, Pressable, View } from 'react-native';
import Animated, { useAnimatedStyle, useSharedValue, withSequence, withTiming } from 'react-native-reanimated';
import { HoleRail } from '../../components/HoleRail';
import { HoleTools, type HoleDraft } from '../../components/HoleTools';
import { TopoMap } from '../../components/TopoMap';
import { holeDrawing } from '../../data/courseMaps';
import { getCourse } from '../../data/courses';
import { AppText, Button, IconButton, Screen } from '../../components/ui';
import { formatDistance, formatRelative } from '../../domain/format';
import { holeResult, holeScoreToInput, summarizeHoles } from '../../domain/scoring';
import type { HoleScore } from '../../domain/types';
import { hapticSelect, hapticSuccess } from '../../lib/haptics';
import { useReducedMotion } from '../../hooks/useReducedMotion';
import { requestRecap } from '../../services/golf/client';
import { useGolf } from '../../state/GolfContext';
import { colors, resultTone } from '../../theme/colors';

export default function RoundScreen() {
  const { activeRound, scores, preferences, saveHoleScore, focusHole, endRound } = useGolf();
  const holes = activeRound ? (scores[activeRound.id] ?? []) : [];
  const current = holes.find((hole) => hole.holeNumber === activeRound?.currentHole) ?? holes[0];

  if (!activeRound || !current) {
    return (
      <Screen>
        <AppText weight="semibold" className="text-2xl">
          Round
        </AppText>
        <View className="mt-5 h-48 overflow-hidden rounded-3xl border border-white/10 bg-panel">
          <TopoMap seed="no-round" animate sketch />
        </View>
        <AppText className="mt-4 text-base text-slate">
          No round is in progress. Pick a course when you are ready to keep score.
        </AppText>
        <View className="mt-6">
          <Button label="Choose a course" onPress={() => router.push('/course')} />
        </View>
      </Screen>
    );
  }

  return (
    <ActiveRound
      key={`${activeRound.id}-${current.holeNumber}`}
      roundId={activeRound.id}
      courseId={activeRound.courseId}
      courseName={activeRound.courseName}
      teeName={activeRound.teeSetName}
      sample={activeRound.sample}
      status={activeRound.status}
      hole={current}
      holes={holes}
      units={preferences.units}
      onSave={saveHoleScore}
      onFocus={(holeNumber) => focusHole(activeRound.id, holeNumber)}
      onFinish={() => endRound(activeRound.id)}
    />
  );
}

function ActiveRound({
  roundId,
  courseId,
  courseName,
  teeName,
  sample,
  status,
  hole,
  holes,
  units,
  onSave,
  onFocus,
  onFinish,
}: {
  roundId: string;
  courseId: string;
  courseName: string;
  teeName: string;
  sample: boolean;
  status: 'active' | 'completed';
  hole: HoleScore;
  holes: HoleScore[];
  units: 'yards' | 'meters';
  onSave: (draft: {
    roundId: string;
    holeNumber: number;
    strokes: number;
    putts: number | null;
    penalties: number | null;
    fairwayHit: boolean | null;
  }) => Promise<void>;
  onFocus: (holeNumber: number) => Promise<void>;
  onFinish: () => Promise<void>;
}) {
  const { userId, bag, notes, saveHoleNote, preferences } = useGolf();
  const reduced = useReducedMotion();
  const tools = useRef<HoleDraft>({ miss: null, gir: null, pin: 'middle', shots: [], club: null, cardId: null });
  const onTools = useCallback((draft: HoleDraft) => {
    tools.current = draft;
  }, []);
  const savedNote = notes.find((note) => note.roundId === roundId && note.holeNumber === hole.holeNumber) ?? null;
  const mapped = holeDrawing(courseId, hole.holeNumber, teeName);
  const catalogHole = getCourse(courseId)
    ?.teeSets.find((tee) => tee.name === teeName)
    ?.holes.find((item) => item.number === hole.holeNumber);
  const [strokes, setStrokes] = useState(hole.strokes ?? hole.par);
  const [putts, setPutts] = useState<number | null>(hole.putts);
  const [penalties, setPenalties] = useState<number | null>(hole.penalties);
  const [fairway, setFairway] = useState<boolean | null>(hole.fairwayHit);
  const [advanced, setAdvanced] = useState(false);
  const [flash, setFlash] = useState<string | null>(null);
  const scale = useSharedValue(1);
  const skipPulse = useRef(true);

  useEffect(() => {
    if (!flash) return;
    const timer = setTimeout(() => setFlash(null), 1600);
    return () => clearTimeout(timer);
  }, [flash]);

  useEffect(() => {
    if (skipPulse.current) {
      skipPulse.current = false;
      return;
    }
    if (reduced) return;
    scale.value = withSequence(withTiming(1.05, { duration: 90 }), withTiming(1, { duration: 150 }));
  }, [reduced, scale, strokes]);

  const pulse = useAnimatedStyle(() => ({ transform: [{ scale: scale.value }] }));
  const stats = summarizeHoles(holes.map(holeScoreToInput));
  const relative = stats.relativeToPar == null ? null : formatRelative(stats.relativeToPar);
  const result = holeResult(strokes, hole.par);
  const numbers = holes.map((item) => item.holeNumber);
  const index = numbers.indexOf(hole.holeNumber);
  const previous = index > 0 ? numbers[index - 1] : null;
  const next = index < numbers.length - 1 ? numbers[index + 1] : null;
  const baseline = hole.strokes ?? hole.par;
  const dirty =
    strokes !== baseline ||
    putts !== hole.putts ||
    penalties !== hole.penalties ||
    fairway !== hole.fairwayHit;
  const unplayed = holes.filter((item) => !item.completed).length;

  function draft() {
    return {
      roundId,
      holeNumber: hole.holeNumber,
      strokes,
      putts,
      penalties,
      fairwayHit: hole.par === 3 ? null : fairway,
    };
  }

  async function persist() {
    await onSave(draft());
    const detail = tools.current;
    await saveHoleNote({
      roundId,
      holeNumber: hole.holeNumber,
      par: hole.par,
      strokes,
      sample,
      miss: detail.miss,
      gir: detail.gir,
      pin: detail.pin,
      club: detail.club,
      cardId: detail.cardId,
      shots: detail.shots,
    });
    hapticSuccess();
    setFlash(`Hole ${hole.holeNumber} saved`);
  }

  async function finishRound() {
    await onFinish();
    const played = [
      ...notes.filter((note) => note.roundId === roundId && note.holeNumber !== hole.holeNumber),
      {
        roundId,
        holeNumber: hole.holeNumber,
        par: hole.par,
        strokes,
        sample,
        miss: tools.current.miss,
        gir: tools.current.gir,
        pin: tools.current.pin,
        club: tools.current.club,
        cardId: tools.current.cardId,
        shots: tools.current.shots,
      },
    ];
    await requestRecap(userId, roundId, { strokes: stats.totalStrokes, relative: stats.relativeToPar }, played).catch(
      () => undefined,
    );
  }

  function goTo(holeNumber: number) {
    const untouched =
      !hole.completed && strokes === hole.par && putts == null && penalties == null && fairway == null;
    if (!dirty || untouched) {
      void onFocus(holeNumber);
      return;
    }
    Alert.alert('Save this hole?', 'The score changed and has not been saved.', [
      { text: 'Discard', style: 'destructive', onPress: () => void onFocus(holeNumber) },
      {
        text: 'Save',
        onPress: () => {
          void persist().then(() => onFocus(holeNumber));
        },
      },
    ]);
  }

  async function onPrimary() {
    const shouldSave = !hole.completed || dirty;
    if (shouldSave) await persist();
    if (next) {
      await onFocus(next);
      return;
    }
    if (status === 'active') {
      await finishRound();
      setFlash('Round saved');
    }
  }

  let primary = 'Save hole';
  if (hole.completed && dirty) primary = 'Update score';
  else if (hole.completed && next) primary = 'Next hole';
  else if (!hole.completed && !next) primary = 'Save and finish';
  else if (hole.completed && !next && status === 'active') primary = 'Finish round';
  else if (status === 'completed' && !dirty) primary = 'View scorecard';

  return (
    <Screen>
      <View className="mb-3 flex-row items-start justify-between">
        <View className="flex-1 pr-3">
          <AppText weight="semibold" className="text-2xl">
            Round
          </AppText>
          <AppText className="mt-1 text-sm text-slate">
            {courseName} · {teeName}
          </AppText>
        </View>
        <Pressable accessibilityRole="button" onPress={() => router.push('/scorecard')} className="min-h-11 justify-center">
          <AppText weight="medium" className="text-cyan">
            Scorecard
          </AppText>
        </Pressable>
      </View>

      {mapped ? null : (
        <View className="h-36 overflow-hidden rounded-3xl border border-white/10 bg-panel">
          <TopoMap seed={`${courseId}-${hole.holeNumber}`} animate sketch />
        </View>
      )}

      <View className="mt-4 flex-row items-center justify-between">
        <IconButton
          label="Previous hole"
          disabled={previous == null}
          onPress={() => previous != null && goTo(previous)}
        >
          <ChevronLeft color={colors.mist} size={22} />
        </IconButton>
        <View className="items-center">
          <AppText weight="semibold" className="text-xl">
            Hole {hole.holeNumber}
          </AppText>
          <AppText className="mt-1 text-sm text-slate">
            Par {hole.par} · {formatDistance(hole.yards, units)}
          </AppText>
        </View>
        <IconButton label="Next hole" disabled={next == null} onPress={() => next != null && goTo(next)}>
          <ChevronRight color={colors.mist} size={22} />
        </IconButton>
      </View>
      <HoleRail holes={holes} current={hole.holeNumber} onSelect={goTo} />

      <View className="mt-6 flex-row items-center justify-between">
        <IconButton
          label="Remove stroke"
          disabled={strokes <= 1}
          onPress={() => {
            hapticSelect();
            setStrokes((value) => Math.max(1, value - 1));
          }}
        >
          <Minus color={colors.mist} size={22} />
        </IconButton>
        <Animated.View style={pulse}>
          <View className="items-center">
            <AppText weight="semibold" className="text-[72px] leading-[76px]">
              {strokes}
            </AppText>
            <AppText className="text-sm text-slate">Strokes</AppText>
          </View>
        </Animated.View>
        <IconButton
          label="Add stroke"
          disabled={strokes >= 15}
          onPress={() => {
            hapticSelect();
            setStrokes((value) => Math.min(15, value + 1));
          }}
        >
          <Plus color={colors.mist} size={22} />
        </IconButton>
      </View>

      <View className="mt-4 items-center">
        <View className="rounded-full border border-white/10 px-4 py-2">
          <AppText weight="medium" style={{ color: resultTone(result.delta) }}>
            {result.label} · {result.plain}
          </AppText>
        </View>
        <AppText className="mt-3 text-center text-sm text-slate">
          {relative
            ? `${relative.symbol} · ${relative.words} through ${stats.completedHoles} saved ${
                stats.completedHoles === 1 ? 'hole' : 'holes'
              }`
            : 'No holes saved yet'}
        </AppText>
        {flash ? (
          <AppText className="mt-2 text-sm text-cyan">{flash}</AppText>
        ) : null}
      </View>

      <HoleTools
        userId={userId}
        roundId={roundId}
        courseId={courseId}
        courseName={courseName}
        teeName={teeName}
        holeNumber={hole.holeNumber}
        par={hole.par}
        yards={hole.yards}
        handicap={catalogHole?.handicap ?? 1}
        windOn={preferences.hud.showWind}
        bag={bag.clubs}
        saved={savedNote}
        onChange={onTools}
      />
      <View className="mt-4 rounded-3xl border border-white/10 bg-panel p-4">
        <Stepper label="Putts" value={putts} onChange={setPutts} max={strokes} />
      </View>
      <Pressable
        accessibilityRole="button"
        onPress={() => setAdvanced((open) => !open)}
        className="mt-4 min-h-11 justify-center"
      >
        <AppText weight="medium" className="text-sm text-slate">
          {advanced ? 'Hide details' : 'Penalties and fairway'}
        </AppText>
      </Pressable>
      {advanced ? (
        <View className="mt-2 rounded-3xl border border-white/10 bg-panel p-4">
          <View>
            <Stepper label="Penalty strokes" value={penalties} onChange={setPenalties} max={strokes} />
            <AppText className="mt-2 text-xs text-slate">
              Penalties are already part of the stroke count. They are not added again.
            </AppText>
          </View>
          {hole.par === 3 ? (
            <AppText className="mt-4 text-sm text-slate">Fairways are not tracked on par 3s.</AppText>
          ) : (
            <View className="mt-4">
              <AppText className="mb-2 text-sm text-slate">Fairway</AppText>
              <View className="flex-row gap-2">
                <Choice label="Hit" selected={fairway === true} onPress={() => setFairway(true)} />
                <Choice label="Missed" selected={fairway === false} onPress={() => setFairway(false)} />
                <Choice label="Skip" selected={fairway == null} onPress={() => setFairway(null)} />
              </View>
            </View>
          )}
        </View>
      ) : null}

      <View className="mt-6">
        <Button
          label={primary}
          onPress={() => {
            if (primary === 'View scorecard') {
              router.push('/scorecard');
              return;
            }
            void onPrimary();
          }}
        />
      </View>
      {status === 'active' && stats.completedHoles > 0 && unplayed > 0 ? (
        <Pressable
          accessibilityRole="button"
          className="mt-4 min-h-11 items-center justify-center"
          onPress={() => {
            Alert.alert(
              'End this round?',
              `${unplayed} ${unplayed === 1 ? 'hole is' : 'holes are'} still blank. Blank holes will not change your averages.`,
              [
                { text: 'Keep playing', style: 'cancel' },
                { text: 'End round', onPress: () => void finishRound() },
              ],
            );
          }}
        >
          <AppText className="text-sm text-slate">End round</AppText>
        </Pressable>
      ) : null}
    </Screen>
  );
}

function Stepper({
  label,
  value,
  onChange,
  max,
}: {
  label: string;
  value: number | null;
  onChange: (value: number | null) => void;
  max: number;
}) {
  return (
    <View className="flex-row items-center justify-between">
      <AppText>{label}</AppText>
      <View className="flex-row items-center gap-3">
        <SmallStep
          label={`Decrease ${label}`}
          disabled={value == null}
          onPress={() => {
            if (value == null) return;
            onChange(value <= 0 ? null : value - 1);
          }}
        >
          <Minus color={colors.mist} size={16} />
        </SmallStep>
        <AppText weight="semibold" className="w-8 text-center text-lg">
          {value == null ? '—' : String(value)}
        </AppText>
        <SmallStep
          label={`Increase ${label}`}
          disabled={value != null && value >= max}
          onPress={() => onChange(value == null ? 0 : Math.min(max, value + 1))}
        >
          <Plus color={colors.mist} size={16} />
        </SmallStep>
      </View>
    </View>
  );
}

function SmallStep({
  label,
  onPress,
  disabled,
  children,
}: {
  label: string;
  onPress: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={label}
      disabled={disabled}
      onPress={onPress}
      className="h-10 w-10 items-center justify-center rounded-full border border-white/10"
      style={{ opacity: disabled ? 0.35 : 1 }}
    >
      {children}
    </Pressable>
  );
}

function Choice({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      className={`min-h-10 flex-1 items-center justify-center rounded-full border ${
        selected ? 'border-cyan' : 'border-white/10'
      }`}
    >
      <AppText className={`text-sm ${selected ? 'text-cyan' : ''}`}>{label}</AppText>
    </Pressable>
  );
}
