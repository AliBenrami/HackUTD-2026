import { View } from 'react-native';
import Svg, { Circle, Line } from 'react-native-svg';
import type { PoseLandmark } from '../domain/types';
import { DEMO_BONES } from '../services/swing/analyzer';
import { colors } from '../theme/colors';
import { AppText } from './ui';

export function PoseFigure({ landmarks }: { landmarks: PoseLandmark[] }) {
  const byName = new Map(landmarks.map((landmark) => [landmark.name, landmark]));

  return (
    <View className="overflow-hidden rounded-3xl border border-white/10 bg-panel">
      <View style={{ height: 280 }}>
        <Svg viewBox="0 0 100 100" width="100%" height="100%">
          {DEMO_BONES.map(([from, to]) => {
            const start = byName.get(from);
            const end = byName.get(to);
            if (!start || !end) return null;
            const club = to === 'club';
            return (
              <Line
                key={`${from}-${to}`}
                x1={start.x}
                y1={start.y}
                x2={end.x}
                y2={end.y}
                stroke={club ? colors.magenta : colors.cyan}
                strokeWidth={club ? 1.1 : 1.4}
                strokeLinecap="round"
              />
            );
          })}
          {landmarks
            .filter((landmark) => landmark.name !== 'club')
            .map((landmark) => (
              <Circle
                key={landmark.name}
                cx={landmark.x}
                cy={landmark.y}
                r={landmark.name === 'head' ? 3.1 : 1.7}
                fill={colors.mist}
              />
            ))}
        </Svg>
      </View>
      <AppText className="px-4 pb-4 text-xs text-slate">Sample pose · not detected from video</AppText>
    </View>
  );
}
