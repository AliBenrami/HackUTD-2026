import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';
import { TopoMap } from '../../components/TopoMap';
import { AppText, BackHeader, Button, Screen, Segmented } from '../../components/ui';
import { formatDistance } from '../../domain/format';
import { holesForNine, sumPar, sumYards } from '../../domain/scoring';
import type { NineSelection } from '../../domain/types';
import { getCourse } from '../../data/courses';
import { useGolf } from '../../state/GolfContext';

const NINES: { value: NineSelection; label: string }[] = [
  { value: 'front', label: 'Front 9' },
  { value: 'back', label: 'Back 9' },
  { value: 'full', label: '18 holes' },
];

export default function CourseDetailScreen() {
  const { id } = useLocalSearchParams<{ id: string }>();
  const course = getCourse(String(id));
  const { activeRound, startRound, preferences, noteCourse } = useGolf();
  const [teeId, setTeeId] = useState(course?.teeSets[1]?.id ?? course?.teeSets[0]?.id ?? '');
  const [nine, setNine] = useState<NineSelection>('full');
  const noted = useRef(false);

  useEffect(() => {
    if (!course || noted.current) return;
    noted.current = true;
    void noteCourse(course.id);
  }, [course, noteCourse]);

  if (!course) {
    return (
      <Screen header={<BackHeader title="Course" onBack={() => router.back()} />}>
        <AppText>That course is not in the local catalog.</AppText>
      </Screen>
    );
  }

  const tee = course.teeSets.find((item) => item.id === teeId) ?? course.teeSets[0];
  const holes = holesForNine(tee, nine);

  async function onStart() {
    if (!course) return;
    if (activeRound) {
      Alert.alert(
        'Round already in progress',
        `${activeRound.courseName} is still open. Continue that round, or end it before starting another.`,
        [
          { text: 'Continue', onPress: () => router.navigate('/round') },
          { text: 'Not now', style: 'cancel' },
        ],
      );
      return;
    }
    await startRound(course, tee, nine);
    router.navigate('/round');
  }

  return (
    <Screen header={<BackHeader title="Course" onBack={() => router.back()} />}>
      <View className="mb-4 h-52 overflow-hidden rounded-3xl border border-white/10 bg-panel">
        <TopoMap seed={`${course.id}-${nine}`} animate />
      </View>
      <AppText weight="semibold" className="text-2xl">
        {course.name}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">{course.location}</AppText>
      <AppText className="mt-3 text-base text-slate">{course.summary}</AppText>

      <View className="mt-5 flex-row gap-3">
        <Stat label="Par" value={String(sumPar(holes))} />
        <Stat label="Distance" value={formatDistance(sumYards(holes), preferences.units)} />
        <Stat label="Slope" value={String(tee.slope)} />
      </View>

      <AppText weight="medium" className="mb-2 mt-6 text-sm text-slate">
        Tees
      </AppText>
      <View className="flex-row flex-wrap gap-2">
        {course.teeSets.map((option) => {
          const selected = option.id === tee.id;
          return (
            <Pressable
              key={option.id}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => setTeeId(option.id)}
              className={`min-h-11 flex-row items-center rounded-full border px-3 ${
                selected ? 'border-cyan bg-panel' : 'border-white/10 bg-panel'
              }`}
            >
              <View
                style={{ width: 10, height: 10, borderRadius: 5, backgroundColor: option.marker }}
              />
              <AppText className={`ml-2 text-sm ${selected ? 'text-cyan' : ''}`}>{option.name}</AppText>
            </Pressable>
          );
        })}
      </View>
      <AppText className="mt-2 text-xs text-slate">
        Rating {tee.rating.toFixed(1)} · {tee.name} tees
      </AppText>

      <AppText weight="medium" className="mb-2 mt-6 text-sm text-slate">
        Round length
      </AppText>
      <Segmented options={NINES} value={nine} onChange={setNine} />

      <View className="mt-6">
        <Button label="Start round" onPress={() => void onStart()} />
      </View>
    </Screen>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <View className="flex-1 rounded-2xl border border-white/10 bg-panel px-3 py-3">
      <AppText className="text-xs text-slate">{label}</AppText>
      <AppText weight="semibold" className="mt-1 text-base">
        {value}
      </AppText>
    </View>
  );
}
