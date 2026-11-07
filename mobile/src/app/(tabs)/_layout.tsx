import { Tabs } from 'expo-router';
import { ChartColumn, Flag, House, PersonStanding } from 'lucide-react-native';
import { Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AppText } from '../../components/ui';
import { colors } from '../../theme/colors';

const ICONS = {
  index: House,
  round: Flag,
  stats: ChartColumn,
  swing: PersonStanding,
} as const;

const LABELS = {
  index: 'Home',
  round: 'Round',
  stats: 'Stats',
  swing: 'Swing',
} as const;

export default function TabLayout() {
  return (
    <Tabs
      tabBar={(props) => <GolfTabBar {...(props as unknown as GolfTabBarProps)} />}
      screenOptions={{
        headerShown: false,
        sceneStyle: { backgroundColor: colors.ink },
      }}
    >
      <Tabs.Screen name="index" options={{ title: 'Home' }} />
      <Tabs.Screen name="round" options={{ title: 'Round' }} />
      <Tabs.Screen name="stats" options={{ title: 'Stats' }} />
      <Tabs.Screen name="swing" options={{ title: 'Swing' }} />
    </Tabs>
  );
}

type GolfTabBarProps = {
  state: {
    index: number;
    routes: { key: string; name: string }[];
  };
  navigateToTab: (routeKey: string) => void;
};

function GolfTabBar({ state, navigateToTab }: GolfTabBarProps) {
  const insets = useSafeAreaInsets();
  return (
    <View
      style={{
        width: '100%',
        maxWidth: 430,
        alignSelf: 'center',
        paddingBottom: Math.max(insets.bottom, 8),
        backgroundColor: colors.ink,
        borderTopWidth: 1,
        borderTopColor: colors.line,
        flexDirection: 'row',
        paddingTop: 8,
      }}
    >
      {state.routes.map((route, index) => {
        const focused = state.index === index;
        const name = route.name as keyof typeof ICONS;
        const Icon = ICONS[name] ?? House;
        const color = focused ? colors.cyan : colors.slate;
        return (
          <Pressable
            key={route.key}
            accessibilityRole="button"
            accessibilityState={{ selected: focused }}
            accessibilityLabel={LABELS[name] ?? route.name}
            onPress={() => {
              if (!focused) navigateToTab(route.key);
            }}
            style={{ flex: 1, alignItems: 'center', minHeight: 48, justifyContent: 'center' }}
          >
            <Icon color={color} size={22} strokeWidth={focused ? 2.3 : 1.8} />
            <AppText weight="medium" className="mt-1 text-[11px]" style={{ color }}>
              {LABELS[name] ?? route.name}
            </AppText>
          </Pressable>
        );
      })}
    </View>
  );
}
