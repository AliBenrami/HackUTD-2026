import { useState } from 'react';
import { Pressable, View } from 'react-native';
import type { CaddieCard as Card } from '../domain/caddie';
import { AppText } from './ui';

export function CaddieCardView({ card }: { card: Card }) {
  const [open, setOpen] = useState(false);
  return (
    <View className="mt-4 rounded-3xl border border-white/10 bg-panel p-4">
      <AppText className="text-sm text-slate">This hole</AppText>
      <AppText weight="semibold" className="mt-1 text-2xl">
        {card.club}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">
        {card.carryYards} yard carry · playing {card.adjustedYards} · aim {card.aim}
      </AppText>
      {card.windNote ? <AppText className="mt-2 text-sm">{card.windNote}</AppText> : null}
      <AppText className="mt-2 text-sm text-slate">Miss toward the {card.missTo}.</AppText>
      <Pressable accessibilityRole="button" onPress={() => setOpen((value) => !value)} className="mt-3 min-h-11 justify-center">
        <AppText weight="medium" className="text-sm text-cyan">
          {open ? 'Hide reasons' : 'Why this club'}
        </AppText>
      </Pressable>
      {open ? (
        <View className="gap-2">
          {card.reasons.map((reason) => (
            <AppText key={reason} className="text-sm">
              {reason}
            </AppText>
          ))}
        </View>
      ) : null}
      <AppText className="mt-3 text-xs text-slate">
        A suggestion from your bag and saved holes. It is not a measurement of the shot.
        {card.source === 'fallback' ? ' The model was not used.' : ''}
      </AppText>
    </View>
  );
}
