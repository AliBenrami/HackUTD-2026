import { router } from 'expo-router';
import { useVideoPlayer, VideoView } from 'expo-video';
import { useEffect, useRef, useState } from 'react';
import { Image, Pressable, ScrollView, StyleSheet, View, type ScrollViewInstance } from 'react-native';
import Svg, { Circle, Line, Rect } from 'react-native-svg';
import { swingClip, swingFrames } from '../data/swingFrames';
import { SCORE_CUTOFF, swingReview } from '../data/swingReview';
import { SWING_FPS, swingTrack } from '../data/swingTrack';
import { formatWhen } from '../domain/format';
import type { SwingSession } from '../domain/types';
import { useGolf } from '../state/GolfContext';
import { colors } from '../theme/colors';
import { AppText } from './ui';

const BONES: ReadonlyArray<readonly [number, number]> = [
  [5, 6], [5, 7], [7, 9], [6, 8], [8, 10],
  [5, 11], [6, 12], [11, 12],
  [11, 13], [13, 15], [12, 14], [14, 16],
];
const DOTS = [0, 5, 6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16];
const AMBER = '#FFC850';
const CLUB_COLORS = { shaft: '#FFB214', clubHead: '#8CF569', hands: '#DE8AED' } as const;
const CLUB_ROWS = [
  ['shaft', 'Shaft'],
  ['clubHead', 'Club head'],
  ['hands', 'Hands'],
] as const;
const FRAME_HEIGHT = 1920;
const CROP_Y = 520;
const CROP_HEIGHT = 1360;
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

type SwingChoice =
  | { key: string; kind: 'analyzed'; swingIndex: number; label: string; detail: string }
  | { key: string; kind: 'saved'; session: SwingSession; label: string; detail: string };

type VideoGroup = {
  id: string;
  title: string;
  detail: string;
  letter?: string;
  swings: SwingChoice[];
};

function impactIndex(swingIndex: number) {
  return swingReview[swingIndex].events.findIndex((event) => event.name === 'Impact');
}

function swingCount(count: number) {
  return count === 1 ? '1 swing' : `${count} swings`;
}

function buildVideos(saved: SwingSession[]): VideoGroup[] {
  const analyzed: VideoGroup = {
    id: 'range-clip',
    title: 'Range clip',
    detail: swingCount(swingReview.length),
    swings: swingReview.map((swing, index) => {
      const impact = swing.events[impactIndex(index)];
      return {
        key: `analyzed-${swing.id}`,
        kind: 'analyzed',
        swingIndex: index,
        label: `Swing ${swing.id}`,
        detail: `${impact.timeS.toFixed(2)} s`,
      };
    }),
  };

  const groups = new Map<string, SwingSession[]>();
  const order: string[] = [];
  for (const session of saved) {
    const videoId = session.videoId;
    const existing = groups.get(videoId);
    if (existing) existing.push(session);
    else {
      groups.set(videoId, [session]);
      order.push(videoId);
    }
  }

  const recorded = order.map((uri) => {
    const sessions = [...(groups.get(uri) ?? [])].sort((a, b) => a.createdAt.localeCompare(b.createdAt));
    const first = sessions[0];
    return {
      id: uri,
      title: first.club,
      detail: swingCount(sessions.length),
      letter: first.club.slice(0, 1),
      swings: sessions.map((session, index) => ({
        key: session.id,
        kind: 'saved' as const,
        session,
        label: `Swing ${index + 1}`,
        detail: formatWhen(session.createdAt),
      })),
    };
  });

  return [analyzed, ...recorded];
}

function degrees(value: number | null) {
  return value == null ? 'Unavailable' : `${value.toFixed(1)}°`;
}

export function SwingReview() {
  const { swings, removeSwing } = useGolf();
  const saved = swings.filter((swing) => swing.source !== 'demo');
  const savedIds = saved.map((swing) => swing.id).join('|');
  const videos = buildVideos(saved);
  const [videoId, setVideoId] = useState(videos[0].id);
  const [swingKey, setSwingKey] = useState(videos[0].swings[0].key);
  const known = useRef(new Set(saved.map((swing) => swing.id)));
  const savedRef = useRef(saved);
  savedRef.current = saved;

  useEffect(() => {
    const current = savedRef.current;
    const fresh = current.find((swing) => !known.current.has(swing.id));
    for (const swing of current) known.current.add(swing.id);
    if (fresh) {
      setVideoId(fresh.videoId);
      setSwingKey(fresh.id);
    }
  }, [savedIds]);

  const video = videos.find((item) => item.id === videoId) ?? videos[0];
  const swing = video.swings.find((item) => item.key === swingKey) ?? video.swings[0];

  return (
    <View>
      <View className="mb-3 flex-row items-center justify-between">
        <AppText weight="semibold" className="text-lg">
          Videos
        </AppText>
        <Pressable accessibilityRole="button" onPress={() => router.push('/record')} className="min-h-11 justify-center">
          <AppText weight="semibold" className="text-cyan">
            Record
          </AppText>
        </Pressable>
      </View>

      <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.library}>
        {videos.map((item) => {
          const selected = item.id === video.id;
          return (
            <Pressable
              key={item.id}
              accessibilityRole="button"
              accessibilityState={{ selected }}
              onPress={() => {
                setVideoId(item.id);
                setSwingKey(item.swings[0].key);
              }}
              style={[styles.card, selected && styles.cardSelected]}
            >
              {item.id === 'range-clip' ? (
                <View style={styles.thumb}>
                  <Image
                    source={swingFrames[swingReview[0].events[impactIndex(0)].frame]}
                    resizeMode="stretch"
                    style={{ width: '100%', height: `${(FRAME_HEIGHT / CROP_HEIGHT) * 100}%`, marginTop: `${(-CROP_Y / CROP_HEIGHT) * 100}%` }}
                  />
                </View>
              ) : (
                <View style={styles.thumbFallback}>
                  <AppText weight="semibold">{item.letter}</AppText>
                </View>
              )}
              <AppText weight="medium" className="mt-2 text-sm" numberOfLines={1}>
                {item.title}
              </AppText>
              <AppText className="text-xs text-slate">{item.detail}</AppText>
            </Pressable>
          );
        })}
      </ScrollView>

      {video.swings.length > 1 ? (
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={styles.swingRow}>
          {video.swings.map((item) => {
            const selected = item.key === swing.key;
            return (
              <Pressable
                key={item.key}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => setSwingKey(item.key)}
                style={[styles.swingChip, selected && styles.swingChipSelected]}
              >
                <AppText weight="semibold" className="text-sm" style={{ color: selected ? colors.ink : colors.mist }}>
                  {item.label}
                </AppText>
                <AppText className="text-xs" style={{ color: selected ? colors.ink : colors.slate }}>
                  {item.detail}
                </AppText>
              </Pressable>
            );
          })}
        </ScrollView>
      ) : null}

      {swing.kind === 'analyzed' ? (
        <AnalyzedSwing key={swing.swingIndex} swingIndex={swing.swingIndex} />
      ) : (
        <SavedSwing key={swing.session.id} swing={swing.session} onRemove={() => void removeSwing(swing.session.id)} />
      )}
    </View>
  );
}

function AnalyzedSwing({ swingIndex }: { swingIndex: number }) {
  const swing = swingReview[swingIndex];
  const [eventIndex, setEventIndex] = useState(() => impactIndex(swingIndex));
  const [playing, setPlaying] = useState(false);
  const [parked, setParked] = useState(true);
  const [playFrame, setPlayFrame] = useState(() => swing.events[impactIndex(swingIndex)].frame);
  const [stageWidth, setStageWidth] = useState(0);
  const phases = useRef<ScrollViewInstance>(null);
  const parkedRef = useRef(true);
  const cueTimeRef = useRef(swing.events[impactIndex(swingIndex)].timeS);
  const cue = swing.events[eventIndex];
  const swingEnd = swing.events[swing.events.length - 1].timeS + 0.8;
  const player = useVideoPlayer(swingClip, (instance) => {
    instance.timeUpdateEventInterval = 1 / SWING_FPS;
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
    const playingSub = player.addListener('playingChange', ({ isPlaying }) => {
      setPlaying(isPlaying);
    });
    const timeSub = player.addListener('timeUpdate', ({ currentTime }) => {
      const frame = Math.max(0, Math.min(swingTrack.length - 1, Math.round(currentTime * SWING_FPS)));
      setPlayFrame((current) => (current === frame ? current : frame));
      if (!player.playing) return;
      if (currentTime >= swingEnd) {
        player.pause();
        return;
      }
      let index = 0;
      for (let i = 0; i < swing.events.length; i += 1) {
        if (swing.events[i].timeS <= currentTime + 0.04) index = i;
      }
      setEventIndex((current) => (current === index ? current : index));
    });
    return () => {
      playingSub.remove();
      timeSub.remove();
    };
  }, [player, swing.events, swingEnd]);

  useEffect(() => {
    phases.current?.scrollTo({ x: Math.max(0, eventIndex * 84 - 24), animated: true });
  }, [eventIndex]);

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
    <View className="mt-4">
      <View
        style={styles.stage}
        onLayout={(event) => {
          const width = event.nativeEvent.layout.width;
          setStageWidth((current) => (Math.abs(current - width) < 0.5 ? current : width));
        }}
      >
        <VideoView
          player={player}
          contentFit="fill"
          nativeControls={false}
          playsInline
          style={{
            position: 'absolute',
            left: 0,
            top: -stageWidth * (CROP_Y / 1080),
            width: stageWidth,
            height: stageWidth * (FRAME_HEIGHT / 1080),
          }}
        />
        {parked ? (
          <Image
            source={swingFrames[cue.frame]}
            resizeMode="stretch"
            style={styles.still}
          />
        ) : null}
        <PoseOverlay frameIndex={parked ? cue.frame : playFrame} />
        <ScrollView
          ref={phases}
          horizontal
          showsHorizontalScrollIndicator={false}
          style={styles.phases}
          contentContainerStyle={styles.phaseRow}
        >
          {swing.events.map((event, index) => {
            const selected = index === eventIndex;
            const low = event.score < SCORE_CUTOFF;
            return (
              <Pressable
                key={event.frame}
                accessibilityRole="button"
                accessibilityState={{ selected }}
                onPress={() => selectPhase(index)}
                style={[
                  styles.phase,
                  { borderColor: low ? AMBER : 'rgba(243,246,250,0.28)' },
                  selected && { backgroundColor: low ? AMBER : colors.cyan, borderColor: low ? AMBER : colors.cyan },
                ]}
              >
                <AppText
                  weight={selected ? 'semibold' : 'regular'}
                  className="text-sm"
                  style={{ color: selected ? colors.ink : low ? AMBER : colors.mist }}
                >
                  {SHORT_LABEL[event.name] ?? event.label}
                </AppText>
              </Pressable>
            );
          })}
        </ScrollView>
        <Pressable accessibilityRole="button" accessibilityLabel={playing ? 'Pause' : 'Play'} onPress={togglePlay} style={styles.play}>
          <AppText weight="semibold" className="text-sm">
            {playing ? 'Pause' : 'Play'}
          </AppText>
        </Pressable>
      </View>

      <AppText weight="semibold" className="mt-4 text-2xl">
        {cue.label}
      </AppText>
      <AppText className="mt-1 text-sm text-slate">
        {cue.timeS.toFixed(2)} s
        {cue.tentative ? ' · Tentative' : ''}
        {cue.score < SCORE_CUTOFF ? ' · Low score' : ''}
      </AppText>
      {cue.name === 'Impact' && swing.id === 1 ? (
        <AppText className="mt-2 text-sm" style={{ color: AMBER }}>
          Ball still on the ground.
        </AppText>
      ) : null}

      <View className="mt-5">
        <Row label="" left="Left" right="Right" muted />
        <Row label="Elbow" left={degrees(cue.angles.leftElbow)} right={degrees(cue.angles.rightElbow)} />
        <Row label="Knee" left={degrees(cue.angles.leftKnee)} right={degrees(cue.angles.rightKnee)} />
        <Row label="Torso" left={degrees(cue.angles.torsoTilt)} right="" />
      </View>
      <View className="mt-3">
        {CLUB_ROWS.map(([key, label]) => {
          const detection = cue.clubs[key];
          return (
            <View key={key} className="flex-row items-center justify-between border-t border-white/10 py-2.5">
              <AppText>{label}</AppText>
              <AppText className={detection ? '' : 'text-slate'}>
                {detection ? detection.confidence.toFixed(3) : 'Unavailable'}
              </AppText>
            </View>
          );
        })}
      </View>
    </View>
  );
}

function SavedSwing({ swing, onRemove }: { swing: SwingSession; onRemove: () => void }) {
  const [playing, setPlaying] = useState(false);
  const player = useVideoPlayer(swing.videoUri, (instance) => {
    instance.pause();
  });

  useEffect(() => {
    const sub = player.addListener('playingChange', ({ isPlaying }) => {
      setPlaying(isPlaying);
    });
    const ended = player.addListener('playToEnd', () => {
      setPlaying(false);
    });
    return () => {
      sub.remove();
      ended.remove();
    };
  }, [player]);

  function togglePlay() {
    if (player.playing) {
      player.pause();
      return;
    }
    if (player.duration > 0 && player.currentTime >= player.duration - 0.1) {
      player.currentTime = 0;
    }
    player.play();
  }

  return (
    <View className="mt-4">
      <View style={styles.stage}>
        <VideoView player={player} style={styles.savedVideo} contentFit="contain" nativeControls={false} playsInline />
        <Pressable accessibilityRole="button" accessibilityLabel={playing ? 'Pause' : 'Play'} onPress={togglePlay} style={styles.play}>
          <AppText weight="semibold" className="text-sm">
            {playing ? 'Pause' : 'Play'}
          </AppText>
        </Pressable>
      </View>
      <View className="mt-4 flex-row items-center justify-between">
        <AppText weight="semibold" className="text-2xl">
          {swing.club}
        </AppText>
        <Pressable accessibilityRole="button" onPress={onRemove} className="min-h-11 justify-center">
          <AppText weight="semibold" className="text-sm" style={{ color: colors.magenta }}>
            Remove
          </AppText>
        </Pressable>
      </View>
      <AppText className="mt-1 text-sm text-slate">
        {swing.source === 'camera' ? 'Recorded' : 'Imported'} · {formatWhen(swing.createdAt)}
      </AppText>
      <AppText className="mt-3 text-sm text-slate">
        Pose and phase marks are on the range clip. This recording plays back as its own video.
      </AppText>
    </View>
  );
}

function PoseOverlay({ frameIndex }: { frameIndex: number }) {
  const frame = swingTrack[frameIndex];
  if (!frame) return null;
  const clubs = [
    ['shaft', frame.s],
    ['clubHead', frame.c],
    ['hands', frame.h],
  ] as const;
  return (
    <View style={styles.overlay} pointerEvents="none">
      <Svg viewBox={`0 ${CROP_Y} 1080 ${CROP_HEIGHT}`} style={StyleSheet.absoluteFill}>
        {BONES.map(([start, end]) => {
          const a = frame.j[start];
          const b = frame.j[end];
          if (!a || !b) return null;
          return (
            <Line
              key={`${start}-${end}`}
              x1={a[0]}
              y1={a[1]}
              x2={b[0]}
              y2={b[1]}
              stroke={colors.cyan}
              strokeWidth={8}
              strokeLinecap="round"
            />
          );
        })}
        {DOTS.map((index) => {
          const joint = frame.j[index];
          if (!joint) return null;
          return <Circle key={index} cx={joint[0]} cy={joint[1]} r={7} fill={colors.cyan} />;
        })}
        {clubs.map(([key, box]) => {
          if (!box) return null;
          const [x1, y1, x2, y2] = box;
          return (
            <Rect
              key={key}
              x={x1}
              y={y1}
              width={x2 - x1}
              height={y2 - y1}
              stroke={CLUB_COLORS[key]}
              strokeWidth={6}
              fill="transparent"
            />
          );
        })}
      </Svg>
    </View>
  );
}

function Row({
  label,
  left,
  right,
  muted = false,
}: {
  label: string;
  left: string;
  right: string;
  muted?: boolean;
}) {
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

const styles = StyleSheet.create({
  library: { gap: 10, paddingRight: 8 },
  card: {
    width: 116,
    borderRadius: 14,
    padding: 6,
    borderWidth: 1,
    borderColor: 'transparent',
  },
  swingRow: { gap: 8, paddingTop: 12 },
  swingChip: {
    borderRadius: 14,
    borderWidth: 1,
    borderColor: 'rgba(243,246,250,0.16)',
    backgroundColor: colors.panel,
    paddingHorizontal: 14,
    paddingVertical: 8,
  },
  swingChipSelected: {
    backgroundColor: colors.cyan,
    borderColor: colors.cyan,
  },
  cardSelected: { borderColor: colors.cyan, backgroundColor: colors.panel },
  thumb: { width: '100%', height: 112, borderRadius: 10, overflow: 'hidden' },
  thumbFallback: {
    width: '100%',
    height: 112,
    borderRadius: 10,
    backgroundColor: colors.panelRaised,
    alignItems: 'center',
    justifyContent: 'center',
  },
  stage: {
    position: 'relative',
    width: '100%',
    aspectRatio: 1080 / CROP_HEIGHT,
    borderRadius: 16,
    overflow: 'hidden',
    backgroundColor: '#10140f',
  },
  still: {
    position: 'absolute',
    left: 0,
    zIndex: 1,
    width: '100%',
    height: `${(FRAME_HEIGHT / CROP_HEIGHT) * 100}%`,
    top: `${(-CROP_Y / CROP_HEIGHT) * 100}%`,
  },
  overlay: {
    position: 'absolute',
    top: 0,
    right: 0,
    bottom: 0,
    left: 0,
    zIndex: 1,
  },
  savedVideo: {
    position: 'absolute',
    top: 0,
    left: 0,
    width: '100%',
    height: '100%',
  },
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
  phases: {
    position: 'absolute',
    top: 10,
    left: 0,
    right: 0,
    zIndex: 2,
  },
  phaseRow: { gap: 8, paddingHorizontal: 10 },
  phase: {
    borderWidth: 1,
    borderRadius: 999,
    paddingHorizontal: 12,
    paddingVertical: 7,
    backgroundColor: 'rgba(8,12,18,0.55)',
  },
});
