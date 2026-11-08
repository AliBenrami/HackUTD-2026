import type { ReactNode } from 'react';
import { Pressable, View } from 'react-native';
import type { MapLook } from '../domain/satelliteStyle';
import { AppText } from './ui';

export function MapChrome({
  label,
  look,
  onLook,
  children,
}: {
  label: string;
  look: MapLook;
  onLook: (look: MapLook) => void;
  children: ReactNode;
}) {
  return (
    <View className="h-96 overflow-hidden rounded-3xl border border-white/10 bg-ink">
      {children}
      <View
        pointerEvents="none"
        className="absolute left-3 top-3 z-10 rounded-full px-3 py-2"
        style={{ backgroundColor: 'rgba(8,12,18,0.78)' }}
      >
        <AppText className="text-xs">{label}</AppText>
      </View>
      <View
        className="absolute right-3 top-3 z-10 flex-row overflow-hidden rounded-full"
        style={{ backgroundColor: 'rgba(8,12,18,0.78)' }}
      >
        <LookChip label="Satellite" selected={look === 'satellite'} onPress={() => onLook('satellite')} />
        <LookChip label="Terrain" selected={look === 'terrain'} onPress={() => onLook('terrain')} />
      </View>
    </View>
  );
}

function LookChip({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" accessibilityState={{ selected }} onPress={onPress} className="min-h-9 justify-center px-3">
      <AppText className={`text-xs ${selected ? 'text-cyan' : 'text-mist'}`}>{label}</AppText>
    </Pressable>
  );
}
