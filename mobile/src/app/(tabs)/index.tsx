import { router } from 'expo-router';
import { ChartColumn, ChevronRight, Flag, PersonStanding, Settings } from 'lucide-react-native';
import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';
import { TopoMap } from '../../components/TopoMap';
import { AppText, PressableCard, Screen, Wordmark } from '../../components/ui';
import { formatRelative } from '../../domain/format';
import { holeScoreToInput, summarizeHoles } from '../../domain/scoring';
import { useGolf } from '../../state/GolfContext';
import { colors } from '../../theme/colors';

export default function HomeScreen() {
  const { activeRound, scores, preferences } = useGolf();
  const holes = activeRound ? (scores[activeRound.id] ?? []) : [];
  const stats = summarizeHoles(holes.map(holeScoreToInput));
  const relative = stats.relativeToPar == null ? null : formatRelative(stats.relativeToPar);
  const seed = activeRound
    ? `${activeRound.courseId}-${activeRound.currentHole}`
    : 'cedar-ridge-overview';

  return (
    <Screen>
      <View className="mb-5 flex-row items-center justify-between">
        <Wordmark />
        <Pressable
          accessibilityRole="button"
          accessibilityLabel="Settings"
          onPress={() => router.push('/settings')}
          className="h-11 w-11 items-center justify-center rounded-full bg-panel"
        >
          <Settings color={colors.mist} size={20} />
        </Pressable>
      </View>

      <View className="h-56 overflow-hidden rounded-3xl border border-white/10 bg-panel">
        <TopoMap seed={seed} animate />
      </View>
      <AppText className="mb-6 mt-3 text-sm text-slate">
        {activeRound
          ? `${activeRound.courseName} · hole ${activeRound.currentHole}`
          : 'Courses drawn as holographic contour maps'}
      </AppText>

      <ActionRow
        icon={<Flag color={colors.ink} size={20} />}
        iconClass="bg-cyan"
        title={activeRound ? 'Continue round' : 'Start a round'}
        subtitle={
          activeRound
            ? `${activeRound.courseName} · Hole ${activeRound.currentHole}${
                relative ? ` · ${relative.symbol}` : ''
              }`
            : 'Choose a course and keep score'
        }
        onPress={() => (activeRound ? router.navigate('/round') : router.push('/course'))}
      />
      <ActionRow
        icon={<ChartColumn color={colors.cyan} size={20} />}
        title="Statistics"
        subtitle="Scores, averages, and past rounds"
        onPress={() => router.navigate('/stats')}
      />
      <ActionRow
        icon={<PersonStanding color={colors.cyan} size={20} />}
        title="Swing analysis"
        subtitle="Pose and club at each cue"
        onPress={() => router.navigate('/swing')}
      />

      <Pressable
        accessibilityRole="button"
        onPress={() => router.push('/settings')}
        className="mt-4 min-h-12 flex-row items-center justify-between"
      >
        <AppText className="text-sm">AR visor</AppText>
        <AppText className="text-sm text-slate">
          {preferences.device.connected ? 'Simulated link' : 'Not linked'}
        </AppText>
      </Pressable>
    </Screen>
  );
}

function ActionRow({
  icon,
  iconClass = 'bg-raised',
  title,
  subtitle,
  onPress,
}: {
  icon: ReactNode;
  iconClass?: string;
  title: string;
  subtitle: string;
  onPress: () => void;
}) {
  return (
    <PressableCard onPress={onPress} className="mb-3 px-4 py-4">
      <View className="flex-row items-center">
        <View className={`mr-3 h-12 w-12 items-center justify-center rounded-2xl ${iconClass}`}>
          {icon}
        </View>
        <View className="flex-1">
          <AppText weight="semibold" className="text-base">
            {title}
          </AppText>
          <AppText className="mt-1 text-sm text-slate">{subtitle}</AppText>
        </View>
        <ChevronRight color={colors.slate} size={18} />
      </View>
    </PressableCard>
  );
}
