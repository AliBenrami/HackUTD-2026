import { useState } from 'react';
import { View } from 'react-native';
import { BarChart } from 'react-native-gifted-charts';
import type { HoleStat } from '../domain/scoring';
import { useReducedMotion } from '../hooks/useReducedMotion';
import { colors } from '../theme/colors';
import { AppText } from './ui';

function barColor(relative: number): string {
  if (relative < 0) return colors.cyan;
  if (relative > 0) return colors.magenta;
  return colors.slate;
}

export function ScoreChart({ holes }: { holes: HoleStat[] }) {
  const reduced = useReducedMotion();
  const [width, setWidth] = useState(0);
  if (holes.length === 0) {
    return (
      <AppText className="text-sm text-slate">Score a hole to see it on the chart.</AppText>
    );
  }

  const values = holes.map((hole) => hole.relative);
  const maxValue = Math.max(1, ...values);
  const mostNegativeValue = Math.min(-1, ...values);

  return (
    <View onLayout={(event) => setWidth(event.nativeEvent.layout.width)}>
      {width > 0 ? (
        <BarChart
          width={Math.max(220, width - 8)}
          height={150}
          data={holes.map((hole) => ({
            value: hole.relative,
            label: String(hole.holeNumber),
            frontColor: barColor(hole.relative),
          }))}
          maxValue={maxValue}
          mostNegativeValue={mostNegativeValue}
          stepValue={1}
          barWidth={holes.length > 12 ? 10 : 16}
          spacing={holes.length > 12 ? 12 : 18}
          initialSpacing={10}
          barBorderRadius={4}
          disableScroll={holes.length <= 9}
          isAnimated={!reduced}
          animationDuration={450}
          hideRules={false}
          rulesColor={colors.line}
          rulesType="solid"
          yAxisThickness={0}
          xAxisThickness={1}
          xAxisColor={colors.line}
          yAxisTextStyle={{ color: colors.slate, fontSize: 11 }}
          xAxisLabelTextStyle={{ color: colors.slate, fontSize: 10 }}
          yAxisLabelWidth={28}
          noOfSections={maxValue}
          labelsExtraHeight={6}
        />
      ) : (
        <View style={{ height: 170 }} />
      )}
      <View className="mt-2 flex-row gap-x-4">
        <Legend color={colors.cyan} label="Under par" />
        <Legend color={colors.magenta} label="Over par" />
      </View>
      <AppText className="mt-1 text-xs text-slate">Even par sits on the line.</AppText>
    </View>
  );
}

function Legend({ color, label }: { color: string; label: string }) {
  return (
    <View className="flex-row items-center gap-2">
      <View style={{ width: 8, height: 8, borderRadius: 2, backgroundColor: color }} />
      <AppText className="text-xs text-slate">{label}</AppText>
    </View>
  );
}
