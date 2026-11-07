import { useEffect, useMemo } from 'react';
import { StyleSheet, View, type StyleProp, type ViewStyle } from 'react-native';
import Animated, { Easing, useAnimatedProps, useSharedValue, withDelay, withTiming } from 'react-native-reanimated';
import Svg, { Circle, Path } from 'react-native-svg';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { colors } from '../theme/colors';
import { buildTopo } from './topo';

const AnimatedPath = Animated.createAnimatedComponent(Path);

function ContourPath({
  d,
  color,
  width,
  delay,
  animate,
}: {
  d: string;
  color: string;
  width: number;
  delay: number;
  animate: boolean;
}) {
  const offset = useSharedValue(animate ? 1 : 0);

  useEffect(() => {
    if (!animate) {
      offset.value = 0;
      return;
    }
    offset.value = 1;
    offset.value = withDelay(
      delay,
      withTiming(0, { duration: 900, easing: Easing.out(Easing.cubic) }),
    );
  }, [animate, d, delay, offset]);

  const animatedProps = useAnimatedProps(() => ({
    strokeDashoffset: offset.value * 1400,
  }));

  return (
    <AnimatedPath
      d={d}
      stroke={color}
      strokeWidth={width}
      fill="none"
      strokeLinecap="round"
      strokeLinejoin="round"
      strokeDasharray="1400"
      animatedProps={animatedProps}
    />
  );
}

export function TopoMap({
  seed,
  animate = false,
  style,
}: {
  seed: string;
  animate?: boolean;
  style?: StyleProp<ViewStyle>;
}) {
  const model = useMemo(() => buildTopo(seed), [seed]);
  const reduced = useReducedMotion();
  const play = animate && !reduced;

  return (
    <View style={[styles.fill, style]}>
      <Svg viewBox={model.viewBox} width="100%" height="100%">
        <Path
          d={model.fairway}
          stroke="rgba(0,217,232,0.16)"
          strokeWidth={8}
          fill="none"
          strokeLinecap="round"
        />
        <Circle
          cx={model.bunker.cx}
          cy={model.bunker.cy}
          r={2.1}
          fill="rgba(232,121,249,0.28)"
        />
        <Circle
          cx={model.green.cx}
          cy={model.green.cy}
          r={3.4}
          fill="rgba(0,217,232,0.16)"
          stroke="rgba(139,92,246,0.9)"
          strokeWidth={0.45}
        />
        {model.contours.map((contour, index) => (
          <ContourPath
            key={`${contour.d}-${index}`}
            d={contour.d}
            color={contour.color}
            width={contour.width}
            delay={Math.min(index, 22) * 28}
            animate={play}
          />
        ))}
        <Path
          d={`M ${model.green.cx} ${model.green.cy} L ${model.green.cx} ${model.green.cy - 7}`}
          stroke={colors.mist}
          strokeWidth={0.4}
        />
        <Path
          d={`M ${model.green.cx} ${model.green.cy - 7} L ${model.green.cx + 3.4} ${model.green.cy - 5.4} L ${model.green.cx} ${model.green.cy - 3.8}`}
          fill={colors.magenta}
        />
        <Circle cx={model.tee.cx} cy={model.tee.cy} r={0.8} fill={colors.cyan} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  fill: { flex: 1 },
});
