import { useMemo, useState } from 'react';
import { Pressable, View, type GestureResponderEvent } from 'react-native';
import Svg, { Circle, Path, Polygon, Polyline, Text as SvgText } from 'react-native-svg';
import type { HoleDrawing } from '../data/courseMaps';
import { frameHole, type MapPoint, type Shot } from '../domain/geo';
import { colors } from '../theme/colors';
import { AppText } from './ui';

export type { HoleDrawing };

function localPoint(event: GestureResponderEvent): { x: number; y: number } | null {
  const native = event.nativeEvent as GestureResponderEvent['nativeEvent'] & {
    offsetX?: number;
    offsetY?: number;
    clientX?: number;
    clientY?: number;
  };
  if (Number.isFinite(native.locationX) && Number.isFinite(native.locationY)) {
    return { x: native.locationX, y: native.locationY };
  }
  if (Number.isFinite(native.offsetX) && Number.isFinite(native.offsetY)) {
    return { x: native.offsetX as number, y: native.offsetY as number };
  }
  const node = event.currentTarget as { getBoundingClientRect?: () => { left: number; top: number } } | null;
  if (node?.getBoundingClientRect && Number.isFinite(native.clientX) && Number.isFinite(native.clientY)) {
    const rect = node.getBoundingClientRect();
    return { x: (native.clientX as number) - rect.left, y: (native.clientY as number) - rect.top };
  }
  return null;
}

function points(ring: MapPoint[], project: (point: MapPoint) => { x: number; y: number }) {
  return ring.map((point) => {
    const placed = project(point);
    return `${placed.x.toFixed(2)},${placed.y.toFixed(2)}`;
  }).join(' ');
}

export function HoleMap({
  hole,
  shots,
  onTap,
}: {
  hole: HoleDrawing;
  shots: Shot[];
  onTap?: (point: MapPoint) => void;
}) {
  const [size, setSize] = useState({ width: 0, height: 0 });
  const marks = shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
  const frame = useMemo(() => {
    const placed = shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
    const cloud = [
      hole.tee,
      hole.greenCenter,
      ...hole.green,
      ...(hole.fairway ?? []),
      ...hole.bunkers.flat(),
      ...hole.centerline,
      ...placed,
    ];
    const aspect = size.width > 0 && size.height > 0 ? size.width / size.height : 4 / 3;
    return frameHole(hole.tee, hole.greenCenter, cloud, aspect);
  }, [hole, shots, size.height, size.width]);

  return (
    <View
      className="h-72 overflow-hidden rounded-3xl border border-white/10 bg-panel"
      onLayout={(event) => setSize({ width: event.nativeEvent.layout.width, height: event.nativeEvent.layout.height })}
    >
      <Pressable
        accessibilityRole="button"
        accessibilityLabel="Place the ball on the hole"
        disabled={!onTap}
        onPress={(event) => {
          if (!onTap || size.width === 0 || size.height === 0) return;
          const local = localPoint(event);
          if (!local) return;
          const x = (local.x / size.width) * frame.width;
          const y = (local.y / size.height) * frame.height;
          if (!Number.isFinite(x) || !Number.isFinite(y)) return;
          onTap(frame.fromView(x, y));
        }}
        style={{ flex: 1 }}
      >
        <Svg viewBox={frame.viewBox} width="100%" height="100%" preserveAspectRatio="xMidYMid meet">
          {hole.fairway && hole.fairway.length > 2 ? (
            <Polygon points={points(hole.fairway, frame.toView)} fill="rgba(0,217,232,0.10)" stroke="rgba(0,217,232,0.45)" strokeWidth={0.6} />
          ) : null}
          {hole.bunkers.map((bunker, index) => (
            <Polygon key={index} points={points(bunker, frame.toView)} fill="rgba(232,121,249,0.28)" />
          ))}
          <Polyline
            points={points(hole.centerline.length > 1 ? hole.centerline : [hole.tee, hole.greenCenter], frame.toView)}
            fill="none"
            stroke="rgba(243,246,250,0.25)"
            strokeWidth={0.5}
            strokeDasharray="1.5 1.2"
          />
          <Polygon points={points(hole.green, frame.toView)} fill="rgba(0,217,232,0.18)" stroke={colors.violet} strokeWidth={0.5} />
          {(() => {
            const tee = frame.toView(hole.tee);
            const green = frame.toView(hole.greenCenter);
            return (
              <>
                <Circle cx={tee.x} cy={tee.y} r={2.2} fill={colors.cyan} />
                <Path d={`M ${green.x} ${green.y} L ${green.x} ${green.y - 9}`} stroke={colors.mist} strokeWidth={0.7} />
                <Path d={`M ${green.x} ${green.y - 9} L ${green.x + 4.5} ${green.y - 6.8} L ${green.x} ${green.y - 4.6}`} fill={colors.magenta} />
              </>
            );
          })()}
          {marks.length > 1 ? (
            <Polyline points={points(marks, frame.toView)} fill="none" stroke={colors.mist} strokeWidth={0.45} />
          ) : null}
          {marks.map((shot) => {
            const placed = frame.toView(shot);
            const guessed = shot.source !== 'tap';
            return (
              <Circle
                key={shot.n}
                cx={placed.x}
                cy={placed.y}
                r={2.1}
                fill={guessed ? 'transparent' : colors.mist}
                stroke={colors.mist}
                strokeWidth={0.45}
              />
            );
          })}
          {marks.map((shot) => {
            const placed = frame.toView(shot);
            return (
              <SvgText key={`n-${shot.n}`} x={placed.x + 2.4} y={placed.y - 1.6} fill={colors.mist} fontSize={3.2}>
                {shot.n}
              </SvgText>
            );
          })}
        </Svg>
      </Pressable>
      <View className="absolute bottom-2 left-3">
        <AppText className="text-[10px] text-slate">© OpenStreetMap</AppText>
      </View>
    </View>
  );
}
