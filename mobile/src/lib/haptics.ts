import * as Haptics from 'expo-haptics';
import { Platform } from 'react-native';

export function hapticSelect(): void {
  if (Platform.OS === 'web') return;
  void Haptics.selectionAsync();
}

export function hapticSuccess(): void {
  if (Platform.OS === 'web') return;
  void Haptics.notificationAsync(Haptics.NotificationFeedbackType.Success);
}
