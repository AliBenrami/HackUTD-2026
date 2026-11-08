import { useState } from 'react';
import { Pressable, View } from 'react-native';
import type { CaddieCard as Card } from '../domain/caddie';
import { AppText } from './ui';

export function CaddieCardView({ card }: { card: Card }) {
  const [open, setOpen] = useState(false);
  return (
    <View className="mt-3">
      <View className="flex-row items-center justify-between">
        <View className="flex-1 pr-3">
          <AppText weight="semibold">{card.club}</AppText>
          <AppText className="text-sm text-slate">
            {card.carryYards} yd · playing {card.adjustedYards} · aim {card.aim}
          </AppText>
        </View>
        <Pressable accessibilityRole="button" onPress={() => setOpen((value) => !value)} className="min-h-11 justify-center">
          <AppText weight="medium" className="text-sm text-cyan">
            {open ? 'Hide' : 'Why'}
          </AppText>
        </Pressable>
      </View>
      {open ? (
        <View className="mt-2 gap-2">
          {card.windNote ? <AppText className="text-sm">{card.windNote}</AppText> : null}
          <AppText className="text-sm text-slate">Miss toward the {card.missTo}.</AppText>
          {card.reasons.map((reason) => (
            <AppText key={reason} className="text-sm">
              {reason}
            </AppText>
          ))}
          <AppText className="text-xs text-slate">
            A suggestion from your bag and saved holes. It is not a measurement of the shot.
            {card.source === 'fallback' ? ' The model was not used.' : ''}
          </AppText>
        </View>
      ) : null}
    </View>
  );
}
