import 'react-native-gesture-handler';
import '../../global.css';
import { colorScheme } from 'nativewind';

colorScheme.set('dark');

import { Outfit_400Regular, Outfit_500Medium, Outfit_600SemiBold, Outfit_700Bold, useFonts } from '@expo-google-fonts/outfit';
import { Stack } from 'expo-router';
import * as SplashScreen from 'expo-splash-screen';
import { StatusBar } from 'expo-status-bar';
import { Component, useEffect, type ReactNode } from 'react';
import { View } from 'react-native';
import { AppText } from '../components/ui';
import { GolfProvider } from '../state/GolfContext';
import { colors } from '../theme/colors';

SplashScreen.preventAutoHideAsync().catch(() => undefined);

export default function RootLayout() {
  const [fontsLoaded, fontError] = useFonts({
    Outfit_400Regular,
    Outfit_500Medium,
    Outfit_600SemiBold,
    Outfit_700Bold,
  });

  useEffect(() => {
    if (fontsLoaded || fontError) {
      SplashScreen.hideAsync().catch(() => undefined);
    }
  }, [fontsLoaded, fontError]);

  if (!fontsLoaded && !fontError) return null;

  return (
    <View className="flex-1 items-center bg-ink">
      <StatusBar style="light" />
      <View className="w-full max-w-[430px] flex-1">
      <DBErrorBoundary>
        <GolfProvider>
          <Stack
            screenOptions={{
              headerShown: false,
              contentStyle: { backgroundColor: colors.ink },
              animation: 'slide_from_right',
            }}
          >
            <Stack.Screen name="(tabs)" />
            <Stack.Screen name="course/index" />
            <Stack.Screen name="course/[id]" />
            <Stack.Screen name="scorecard" />
            <Stack.Screen name="settings" />
            <Stack.Screen name="record" options={{ animation: 'slide_from_bottom' }} />
          </Stack>
        </GolfProvider>
      </DBErrorBoundary>
      </View>
    </View>
  );
}

class DBErrorBoundary extends Component<{ children: ReactNode }, { message: string | null }> {
  state = { message: null as string | null };

  static getDerivedStateFromError(error: Error) {
    return { message: error.message };
  }

  render() {
    if (this.state.message) {
      return (
        <View className="flex-1 items-center justify-center bg-ink px-8">
          <AppText weight="semibold" className="text-xl">
            GolfAR could not open your account.
          </AppText>
          <AppText className="mt-3 text-center text-sm text-slate">{this.state.message}</AppText>
        </View>
      );
    }
    return this.props.children;
  }
}
