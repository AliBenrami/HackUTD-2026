import { router, useLocalSearchParams } from 'expo-router';
import { useCallback, useEffect, useRef, useState } from 'react';
import { Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AppText } from '../components/ui';
import { useGolf } from '../state/GolfContext';
import { colors } from '../theme/colors';

const MAX_SECONDS = 12;

export default function RecordScreen() {
  const { club } = useLocalSearchParams<{ club?: string }>();
  return <WebRecorder clubName={club || 'Driver'} />;
}

function WebRecorder({ clubName }: { clubName: string }) {
  const insets = useSafeAreaInsets();
  const { recordSwing } = useGolf();
  const host = useRef<HTMLElement | null>(null);
  const streamRef = useRef<MediaStream | null>(null);
  const recorderRef = useRef<MediaRecorder | null>(null);
  const chunks = useRef<Blob[]>([]);
  const discard = useRef(false);
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [facing, setFacing] = useState<'user' | 'environment'>('environment');
  const [attempt, setAttempt] = useState(0);
  const [ready, setReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [error, setError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);

  const setHost = useCallback((node: unknown) => {
    host.current = node instanceof HTMLElement ? node : null;
  }, []);

  useEffect(() => {
    let cancelled = false;
    discard.current = false;
    setReady(false);
    setError(null);

    async function open() {
      if (!navigator.mediaDevices?.getUserMedia) {
        setError('This browser can’t open the camera.');
        return;
      }
      const video = { facingMode: { ideal: facing } };
      let next: MediaStream;
      try {
        next = await navigator.mediaDevices.getUserMedia({ video, audio: true });
      } catch {
        try {
          next = await navigator.mediaDevices.getUserMedia({ video, audio: false });
        } catch (cause) {
          if (!cancelled) setError(cameraMessage(cause));
          return;
        }
      }
      if (cancelled) {
        stopStream(next);
        return;
      }
      streamRef.current = next;
      setStream(next);
      setReady(true);
    }

    void open();
    return () => {
      cancelled = true;
      discard.current = true;
      if (recorderRef.current?.state === 'recording') recorderRef.current.stop();
      stopStream(streamRef.current);
      streamRef.current = null;
    };
  }, [facing, attempt]);

  useEffect(() => {
    const parent = host.current;
    if (!parent || !stream) return;
    const video = document.createElement('video');
    video.autoplay = true;
    video.muted = true;
    video.playsInline = true;
    video.style.width = '100%';
    video.style.height = '100%';
    video.style.objectFit = 'cover';
    video.style.transform = facing === 'user' ? 'scaleX(-1)' : 'none';
    video.srcObject = stream;
    parent.replaceChildren(video);
    void video.play().catch(() => undefined);
    return () => {
      video.pause();
      video.srcObject = null;
      video.remove();
    };
  }, [stream, facing]);

  useEffect(() => {
    if (!isRecording) return;
    const started = Date.now();
    const timer = setInterval(() => {
      const seconds = Math.floor((Date.now() - started) / 1000);
      setElapsed(seconds);
      if (seconds >= MAX_SECONDS && recorderRef.current?.state === 'recording') {
        recorderRef.current.stop();
      }
    }, 200);
    return () => clearInterval(timer);
  }, [isRecording]);

  async function save(blob: Blob) {
    setSaving(true);
    try {
      const uri = URL.createObjectURL(blob);
      await recordSwing({ source: 'camera', videoUri: uri, club: clubName });
      router.back();
    } catch (cause) {
      setSaving(false);
      setError(cause instanceof Error ? cause.message : 'The recording could not be saved.');
    }
  }

  function toggleRecording() {
    if (saving) return;
    const active = recorderRef.current;
    if (active && active.state === 'recording') {
      active.stop();
      return;
    }
    const live = streamRef.current;
    if (!live || !ready) return;
    const mimeType = ['video/webm;codecs=vp8,opus', 'video/webm;codecs=vp8', 'video/webm', 'video/mp4'].find((type) =>
      MediaRecorder.isTypeSupported(type),
    );
    const recorder = new MediaRecorder(live, mimeType ? { mimeType } : undefined);
    chunks.current = [];
    recorder.ondataavailable = (event) => {
      if (event.data.size > 0) chunks.current.push(event.data);
    };
    recorder.onstop = () => {
      setIsRecording(false);
      if (discard.current) return;
      const blob = new Blob(chunks.current, { type: recorder.mimeType || mimeType || 'video/webm' });
      if (blob.size > 0) void save(blob);
    };
    recorderRef.current = recorder;
    recorder.start();
    setElapsed(0);
    setIsRecording(true);
  }

  return (
    <View className="flex-1 bg-ink">
      <View ref={setHost} style={{ flex: 1, overflow: 'hidden', backgroundColor: colors.ink }} />
      {error ? (
        <View className="absolute inset-0 items-center justify-center px-8">
          <AppText weight="semibold" className="text-center text-xl">
            Record a swing
          </AppText>
          <AppText className="mt-3 text-center text-base text-slate">{error}</AppText>
          <Pressable accessibilityRole="button" onPress={() => setAttempt((value) => value + 1)} className="mt-6 min-h-11 justify-center">
            <AppText weight="semibold" className="text-cyan">
              Try again
            </AppText>
          </Pressable>
        </View>
      ) : null}
      <View
        pointerEvents="box-none"
        style={{ position: 'absolute', top: insets.top + 12, left: 20, right: 20 }}
        className="flex-row items-center justify-between"
      >
        <Pressable accessibilityRole="button" onPress={() => router.back()} className="min-h-11 justify-center">
          <AppText weight="medium">Close</AppText>
        </Pressable>
        <AppText className="text-sm">
          {isRecording ? formatElapsed(elapsed) : saving ? 'Saving…' : ready ? `${clubName} · ${MAX_SECONDS}s` : 'Opening the camera…'}
        </AppText>
      </View>
      <View
        pointerEvents="box-none"
        style={{ position: 'absolute', bottom: insets.bottom + 24, left: 0, right: 0 }}
        className="items-center"
      >
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={isRecording ? 'Stop recording' : 'Start recording'}
          disabled={!ready || saving}
          onPress={toggleRecording}
          className="h-20 w-20 items-center justify-center rounded-full border-2 border-white"
          style={{ opacity: ready && !saving ? 1 : 0.4 }}
        >
          <View
            style={{
              width: isRecording ? 28 : 58,
              height: isRecording ? 28 : 58,
              borderRadius: isRecording ? 6 : 29,
              backgroundColor: colors.magenta,
            }}
          />
        </Pressable>
        <Pressable
          accessibilityRole="button"
          disabled={isRecording || saving}
          onPress={() => setFacing((side) => (side === 'user' ? 'environment' : 'user'))}
          className="mt-4 min-h-11 justify-center"
        >
          <AppText className="text-sm">{isRecording ? 'Recording' : 'Flip camera'}</AppText>
        </Pressable>
      </View>
    </View>
  );
}

function stopStream(stream: MediaStream | null) {
  stream?.getTracks().forEach((track) => track.stop());
}

function cameraMessage(cause: unknown) {
  const name = cause instanceof DOMException ? cause.name : '';
  if (name === 'NotAllowedError' || name === 'PermissionDeniedError') {
    return 'Allow the camera to record a swing in the app.';
  }
  if (name === 'NotFoundError' || name === 'DevicesNotFoundError') {
    return 'No camera was found on this device.';
  }
  return 'The camera could not start. Try again.';
}

function formatElapsed(seconds: number) {
  return `0:${String(Math.min(seconds, MAX_SECONDS)).padStart(2, '0')}`;
}
