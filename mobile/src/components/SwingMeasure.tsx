import { useVideoPlayer, VideoView } from 'expo-video';
import { useEffect, useRef, useState, type ReactNode } from 'react';
import { Pressable, ScrollView, StyleSheet, View, type ScrollViewInstance } from 'react-native';
import Svg, { Circle, Line, Rect } from 'react-native-svg';
import { SCORE_CUTOFF, type ReviewedSwing } from '../data/swingReview';
import { classifySwing, replayWindow, roleLabel, roleNote } from '../domain/swingSession';
import type { SwingMeasurement } from '../services/swing/measurement';
import { colors } from '../theme/colors';
import type { BallSample } from '../data/swingReview';
import { BallTrace } from './BallTrace';
import { AppText } from './ui';

const BONES: ReadonlyArray<readonly [number, number]> = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
];
const DOTS = [0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const AMBER = '#FFC850';
const CLUB_COLORS = { shaft: '#FFB214', clubHead: '#8CF569', hands: '#DE8AED' } as const;
const SHORT_LABEL: Record<string, string> = {
  Address: 'Address',
  'Toe-up': 'Toe-up',
  'Mid-backswing': 'Mid back',
  Top: 'Top',
  'Mid-downswing': 'Mid down',
  Impact: 'Impact',
  'Mid-follow-through': 'Follow',
  Finish: 'Finish',
};

function degrees(value: number | null) {
  return value == null ? 'Unavailable' : `${value.toFixed(1)}°`;
}

export function MeasuredSwingView({
  videoUri,
  measurement,
  footer,
  onAnalyze,
  focusIndex,
  autoPlayToken = 0,
  onAutoPlayDone,
  passedIds = [],
  videoId,
  onPass,
}: {
  videoUri: string;
  measurement: SwingMeasurement;
  footer: ReactNode;
  onAnalyze?: () => void;
  focusIndex?: number;
  autoPlayToken?: number;
  onAutoPlayDone?: () => void;
  passedIds?: string[];
  videoId?: string;
  onPass?: (id: string) => void;
}) {
  const [swingIndex, setSwingIndex] = useState(focusIndex ?? 0);
  const swing = measurement.swings[swingIndex] ?? measurement.swings[0];
  useEffect(() => {
    if (focusIndex == null) return;
    setSwingIndex(focusIndex);
  }, [focusIndex]);
  const swingId = videoId && swing ? `${videoId}:${swing.id}` : null;
  return (
    <View className="mt-4">
      {measurement.swings.length > 1 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.swingRow}>
          {measurement.swings.map((item, index) => {
            const selected = index === swingIndex;
            const role = classifySwing(item);
            return (
              <Pressable
                key={item.id}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => setSwingIndex(index)}
                style={[styles.chip, selected && styles.chipSelected]}
              >
                <AppText weight="semibold" className="text-sm" style={{ color: selected ? colors.ink : colors.mist }}>
                  {roleLabel(role)} {index + 1}
                </AppText>
              </Pressable>
            );
          })}
        </ScrollView>
      ) : null}
      {swing && swing.events.length > 0 ? (
        <MeasuredCueVideo
          key={swing.id}
          videoUri={videoUri}
          measurement={measurement}
          swing={swing}
          footer={footer}
          autoPlayToken={autoPlayToken}
          onAutoPlayDone={onAutoPlayDone}
          passed={swingId != null && passedIds.includes(swingId)}
          onPass={swingId && onPass ? () => onPass(swingId) : undefined}
        />
      ) : (
        <>
          <SkeletonVideo videoUri={videoUri} measurement={measurement} />
          {footer}
          <AppText className="mt-3 text-sm text-slate">The hands did not trace a full swing, so there are no phase cues.</AppText>
        </>
      )}
      <AppText className="mt-3 text-sm text-slate">{measurement.disclaimer}</AppText>
      {onAnalyze ? (
        <Pressable accessibilityRole="button" onPress={onAnalyze} className="mt-2 min-h-11 justify-center">
          <AppText weight="semibold" className="text-cyan">
            Analyze again
          </AppText>
        </Pressable>
      ) : null}
    </View>
  );
}

function MeasuredCueVideo({
  videoUri,
  measurement,
  swing,
  footer,
  autoPlayToken = 0,
  onAutoPlayDone,
  passed,
  onPass,
}: {
  videoUri: string;
  measurement: SwingMeasurement;
  swing: ReviewedSwing;
  footer: ReactNode;
  autoPlayToken?: number;
  onAutoPlayDone?: () => void;
  passed?: boolean;
  onPass?: () => void;
}) {
  const impact = Math.max(0, swing.events.findIndex((event) => event.name === 'Impact'));
  const [eventIndex, setEventIndex] = useState(impact);
  const [playing, setPlaying] = useState(false);
  const [parked, setParked] = useState(true);
  const [playFrame, setPlayFrame] = useState(swing.events[impact]?.frame ?? 0);
  const phases = useRef<ScrollViewInstance>(null);
  const parkedRef = useRef(true);
  const cueTimeRef = useRef(swing.events[impact]?.timeS ?? 0);
  const doneRef = useRef(onAutoPlayDone);
  doneRef.current = onAutoPlayDone;
  const replayEndRef = useRef<number | null>(null);
  const replayArmedRef = useRef(false);
  const replayTokenRef = useRef(0);
  const cue = swing.events[eventIndex] ?? swing.events[0];
  const role = classifySwing(swing);
  const swingEnd = swing.events[swing.events.length - 1].timeS + 0.8;
  const player = useVideoPlayer(videoUri, (instance) => {
    instance.timeUpdateEventInterval = 1 / measurement.fps;
    instance.pause();
  });

  useEffect(() => {
    let cancelled = false;
    const seek = () => {
      if (cancelled || !parkedRef.current) return;
      player.currentTime = cueTimeRef.current;
    };
    seek();
    const status = player.addListener('statusChange', ({ status }) => {
      if (status === 'readyToPlay') seek();
    });
    const timers = [50, 150, 400, 900].map((delay) => setTimeout(seek, delay));
    return () => {
      cancelled = true;
      status.remove();
      timers.forEach(clearTimeout);
    };
  }, [player]);

  useEffect(() => {
    const playingSub = player.addListener('playingChange', ({ isPlaying }) => setPlaying(isPlaying));
    const timeSub = player.addListener('timeUpdate', ({ currentTime }) => {
      const frame = Math.max(0, Math.min(measurement.frames.length - 1, Math.round(currentTime * measurement.fps)));
      setPlayFrame((current) => (current === frame ? current : frame));
      if (replayEndRef.current != null) {
        if (currentTime <= replayEndRef.current - 0.2) replayArmedRef.current = true;
        if (replayArmedRef.current && currentTime >= replayEndRef.current) {
          replayEndRef.current = null;
          replayArmedRef.current = false;
          player.pause();
          doneRef.current?.();
          return;
        }
      }
      if (!player.playing) return;
      if (currentTime >= swingEnd) {
        player.pause();
        return;
      }
      let index = 0;
      for (let cursor = 0; cursor < swing.events.length; cursor += 1) {
        if (swing.events[cursor].timeS <= currentTime + 0.04) index = cursor;
      }
      setEventIndex((current) => (current === index ? current : index));
    });
    return () => {
      playingSub.remove();
      timeSub.remove();
    };
  }, [measurement.fps, measurement.frames.length, player, swing.events, swingEnd]);

  useEffect(() => {
    phases.current?.scrollTo({ x: Math.max(0, eventIndex * 84 - 24), animated: true });
  }, [eventIndex]);

  useEffect(() => {
    if (!autoPlayToken || replayTokenRef.current === autoPlayToken) return;
    replayTokenRef.current = autoPlayToken;
    const window = replayWindow(swing.events);
    if (!window) {
      doneRef.current?.();
      return;
    }
    replayEndRef.current = window.end;
    replayArmedRef.current = false;
    parkedRef.current = false;
    setParked(false);
    cueTimeRef.current = window.start;
    const play = () => {
      player.currentTime = window.start;
      player.play();
    };
    play();
    const timers = [80, 240].map((delay) => setTimeout(play, delay));
    return () => timers.forEach(clearTimeout);
  }, [autoPlayToken, player, swing.events]);

  function selectPhase(index: number) {
    const time = swing.events[index].timeS;
    cueTimeRef.current = time;
    parkedRef.current = true;
    player.pause();
    player.currentTime = time;
    setPlayFrame(swing.events[index].frame);
    setEventIndex(index);
    setParked(true);
  }

  function togglePlay() {
    if (player.playing) {
      player.pause();
      return;
    }
    if (player.currentTime >= swingEnd - 0.08) {
      player.currentTime = swing.events[0].timeS;
      setEventIndex(0);
    }
    parkedRef.current = false;
    setParked(false);
    player.play();
  }

  return (
    <View>
      <Stage measurement={measurement} video={player} frameIndex={parked ? cue.frame : playFrame} playing={playing} onToggle={togglePlay} ball={swing.ball ?? []}>
        <ScrollView ref={phases} horizontal showsHorizontalScrollIndicator={false} style={styles.phases} contentContainerStyle={styles.phaseRow}>
          {swing.events.map((event, index) => {
            const selected = index === eventIndex;
            const low = event.score < SCORE_CUTOFF;
            return (
              <Pressable
                key={`${event.name}-${event.frame}`}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => selectPhase(index)}
                style={[
                  styles.phase,
                  { borderColor: low ? AMBER : 'rgba(243,246,250,0.28)' },
                  selected && { backgroundColor: low ? AMBER : colors.cyan, borderColor: low ? AMBER : colors.cyan },
                ]}
              >
                <AppText weight={selected ? 'semibold' : 'regular'} className="text-sm" style={{ color: selected ? colors.ink : low ? AMBER : colors.mist }}>
                  {SHORT_LABEL[event.name] ?? event.label}
                </AppText>
              </Pressable>
            );
          })}
        </ScrollView>
      </Stage>
      {footer}
      <AppText weight="semibold" className="mt-4 text-2xl">
        {cue.label}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">
        {cue.timeS.toFixed(2)} s{cue.tentative ? ' · Tentative' : ''}
        {cue.score < SCORE_CUTOFF ? ' · Low score' : ''}
      </AppText>
      {cue.name === 'Impact' && (swing.ball ?? []).length === 0 ? (
        <AppText className="mt-2 text-sm text-slate">The ball stays put, so there is no flight trace.</AppText>
      ) : null}
      {(swing.ball ?? []).length > 0 ? (
        <AppText className="mt-2 text-sm text-slate">Ball flight from the detector. It stops when the ball is lost.</AppText>
      ) : null}
      <AppText className="mt-2 text-sm" style={{ color: role === 'shot' ? colors.cyan : '#FFC850' }}>
        {roleLabel(role)}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">{roleNote(role)}</AppText>
      <View className="mt-5">
        <AngleRow label="" left="Left" right="Right" muted />
        <AngleRow label="Elbow" left={degrees(cue.angles.leftElbow)} right={degrees(cue.angles.rightElbow)} />
        <AngleRow label="Knee" left={degrees(cue.angles.leftKnee)} right={degrees(cue.angles.rightKnee)} />
        <AngleRow label="Torso" left={degrees(cue.angles.torsoTilt)} right="" />
      </View>
    </View>
  );
}

function SkeletonVideo({ videoUri, measurement }: { videoUri: string; measurement: SwingMeasurement }) {
  const [frame, setFrame] = useState(0);
  const [playing, setPlaying] = useState(false);
  const player = useVideoPlayer(videoUri, (instance) => {
    instance.timeUpdateEventInterval = 1 / measurement.fps;
    instance.pause();
  });
  useEffect(() => {
    const playingSub = player.addListener('playingChange', ({ isPlaying }) => setPlaying(isPlaying));
    const timeSub = player.addListener('timeUpdate', ({ currentTime }) => {
      const next = Math.max(0, Math.min(measurement.frames.length - 1, Math.round(currentTime * measurement.fps)));
      setFrame((current) => (current === next ? current : next));
    });
    return () => {
      playingSub.remove();
      timeSub.remove();
    };
  }, [measurement.fps, measurement.frames.length, player]);
  return (
    <Stage
      measurement={measurement}
      video={player}
      frameIndex={frame}
      playing={playing}
      onToggle={() => (player.playing ? player.pause() : player.play())}
    />
  );
}

function Stage({
  measurement,
  video,
  frameIndex,
  playing,
  onToggle,
  ball = [],
  children,
}: {
  measurement: SwingMeasurement;
  video: ReturnType<typeof useVideoPlayer>;
  frameIndex: number;
  playing: boolean;
  onToggle: () => void;
  ball?: readonly BallSample[];
  children?: ReactNode;
}) {
  return (
    <View style={[styles.stage, { aspectRatio: measurement.width / measurement.height }]}>
      <VideoView player={video} style={styles.video} contentFit="contain" nativeControls={false} playsInline />
      <PoseOverlay measurement={measurement} frameIndex={frameIndex} ball={ball} />
      {children}
      <Pressable accessibilityRole="button" accessibilityLabel={playing ? 'Pause' : 'Play'} onPress={onToggle} style={styles.play}>
        <AppText weight="semibold" className="text-sm">
          {playing ? 'Pause' : 'Play'}
        </AppText>
      </Pressable>
    </View>
  );
}

function AngleRow({ label, left, right, muted = false }: { label: string; left: string; right: string; muted?: boolean }) {
  const tone = muted ? 'text-slate' : '';
  const missing = (value: string) => (value === 'Unavailable' ? 'text-slate' : tone);
  return (
    <View className="min-h-9 flex-row items-center">
      <AppText className={`w-16 ${tone}`}>{label}</AppText>
      <AppText className={`flex-1 text-right ${missing(left)}`}>{left}</AppText>
      <AppText className={`flex-1 text-right ${missing(right)}`}>{right}</AppText>
    </View>
  );
}

function PoseOverlay({
  measurement,
  frameIndex,
  ball,
}: {
  measurement: SwingMeasurement;
  frameIndex: number;
  ball: readonly BallSample[];
}) {
  const frame = measurement.frames[frameIndex];
  if (!frame) return null;
  return (
    <View style={styles.overlay} pointerEvents="none">
      <Svg viewBox={`0 0 ${measurement.width} ${measurement.height}`} style={StyleSheet.absoluteFill}>
        {BONES.map(([start, end]) => {
          const a = frame.j[start];
          const b = frame.j[end];
          if (!a || !b) return null;
          return <Line key={`${start}-${end}`} x1={a[0]} y1={a[1]} x2={b[0]} y2={b[1]} stroke={colors.cyan} strokeWidth={8} strokeLinecap="round" />;
        })}
        {DOTS.map((index) => {
          const joint = frame.j[index];
          if (!joint) return null;
          return <Circle key={index} cx={joint[0]} cy={joint[1]} r={7} fill={colors.cyan} />;
        })}
        {([
          ['shaft', frame.s],
          ['clubHead', frame.c],
          ['hands', frame.h],
        ] as const).map(([key, box]) => {
          if (!box) return null;
          const [x1, y1, x2, y2] = box;
          return <Rect key={key} x={x1} y={y1} width={x2 - x1} height={y2 - y1} stroke={CLUB_COLORS[key]} strokeWidth={6} fill="transparent" />;
        })}
        <BallTrace samples={ball} frame={frameIndex} />
      </Svg>
    </View>
  );
}

const styles = StyleSheet.create({
  stage: {
    position: 'relative',
    width: '100%',
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#10140f',
  },
  video: { position: 'absolute', top: 0, left: 0, width: '100%', height: '100%' },
  overlay: { position: 'absolute', top: 0, right: 0, bottom: 0, left: 0 },
  play: {
    position: 'absolute',
    left: 12,
    bottom: 12,
    zIndex: 2,
    borderRadius: 999,
    backgroundColor: 'rgba(8,12,18,0.72)',
    paddingHorizontal: 16,
    paddingVertical: 8,
  },
  phases: { position: 'absolute', top: 10, left: 0, right: 0, zIndex: 2 },
  phaseRow: { gap: 8, paddingHorizontal: 10 },
  phase: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: 'rgba(8,12,18,0.55)',
  },
  swingRow: { gap: 8, paddingBottom: 12 },
  chip: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(243,246,250,0.16)',
    backgroundColor: colors.panel,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  chipSelected: { backgroundColor: colors.cyan, borderColor: colors.cyan },
});
