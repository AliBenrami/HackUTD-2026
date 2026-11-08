import { router } from 'expo-router';
import { ChevronRight, Search } from 'lucide-react-native';
import { useMemo, useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { TopoMap } from '../../components/TopoMap';
import { AppText, BackHeader, Screen } from '../../components/ui';
import { formatDistance } from '../../domain/format';
import { holesForNine, sumPar, sumYards } from '../../domain/scoring';
import { defaultTee, getCourse, searchCourses } from '../../data/courses';
import { useGolf } from '../../state/GolfContext';
import { colors, fonts } from '../../theme/colors';

export default function CourseListScreen() {
  const { recentCourseIds, preferences } = useGolf();
  const [query, setQuery] = useState('');
  const results = useMemo(() => searchCourses(query), [query]);
  const recent = recentCourseIds
    .map((id) => getCourse(id))
    .filter((course) => course != null);

  return (
    <Screen header={<BackHeader title="Courses" onBack={() => router.back()} />}>
      <View className="mb-4 min-h-12 flex-row items-center rounded-2xl border border-white/10 bg-panel px-3">
        <Search color={colors.slate} size={18} />
        <TextInput
          value={query}
          onChangeText={setQuery}
          placeholder="Search courses"
          placeholderTextColor={colors.slate}
          autoCapitalize="none"
          autoCorrect={false}
          className="ml-2 flex-1 py-3 text-base text-mist"
          style={{ fontFamily: fonts.regular, color: colors.mist }}
        />
      </View>

      {query.trim().length === 0 && recent.length > 0 ? (
        <View className="mb-5">
          <AppText weight="medium" className="mb-2 text-sm text-slate">
            Recent
          </AppText>
          <View className="flex-row flex-wrap gap-2">
            {recent.map((course) => (
              <Pressable
                key={course.id}
                accessibilityRole="button"
                onPress={() => router.push(`/course/${course.id}`)}
                className="min-h-10 justify-center rounded-full border border-white/10 bg-panel px-4"
              >
                <AppText className="text-sm">{course.name}</AppText>
              </Pressable>
            ))}
          </View>
        </View>
      ) : null}

      {results.length === 0 ? (
        <AppText className="text-sm text-slate">No courses match that search.</AppText>
      ) : (
        results.map((course) => {
          const tee = defaultTee(course);
          const holes = holesForNine(tee, 'full');
          return (
            <Pressable
              key={course.id}
              accessibilityRole="button"
              onPress={() => router.push(`/course/${course.id}`)}
              className="mb-3 flex-row overflow-hidden rounded-3xl border border-white/10 bg-panel"
              style={({ pressed }) => ({ opacity: pressed ? 0.86 : 1 })}
            >
              <View className="h-24 w-28">
                <TopoMap seed={course.id} />
              </View>
              <View className="flex-1 justify-center pr-3">
                <AppText weight="semibold">{course.name}</AppText>
                <AppText className="mt-1 text-sm text-slate">{course.location}</AppText>
                <AppText className="mt-1 text-sm text-slate">
                  Par {sumPar(holes)} · {formatDistance(sumYards(holes), preferences.units)}
                </AppText>
              </View>
              <View className="justify-center pr-4">
                <ChevronRight color={colors.slate} size={18} />
              </View>
            </Pressable>
          );
        })
      )}
    </Screen>
  );
}
