import { Pressable, View } from 'react-native';
import { holeResult } from '../domain/scoring';
import type { HoleScore } from '../domain/types';
import { colors, resultTone } from '../theme/colors';

export function HoleRail({
  holes,
  current,
  onSelect,
}: {
  holes: HoleScore[];
  current: number;
  onSelect: (holeNumber: number) => void;
}) {
  return (
    <View className="mt-3 flex-row flex-wrap justify-center gap-1.5">
      {holes.map((hole) => {
        const played = hole.completed && hole.strokes != null;
        const tone = played && hole.strokes != null ? resultTone(holeResult(hole.strokes, hole.par).delta) : colors.line;
        const selected = hole.holeNumber === current;
        return (
          <Pressable
            key={hole.holeNumber}
            accessibilityRole="button"
            accessibilityLabel={`Hole ${hole.holeNumber}`}
            onPress={() => onSelect(hole.holeNumber)}
            style={{
              width: 22,
              height: 22,
              borderRadius: 11,
              alignItems: 'center',
              justifyContent: 'center',
              borderWidth: selected ? 2 : 1,
              borderColor: selected ? colors.cyan : 'rgba(243,246,250,0.16)',
              backgroundColor: played ? tone : 'transparent',
            }}
          />
        );
      })}
    </View>
  );
}
