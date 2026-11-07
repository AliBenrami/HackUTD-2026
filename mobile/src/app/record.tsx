import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AppText } from '../components/ui';
import { useGolf } from '../state/GolfContext';
import { colors } from '../theme/colors';

const MAX_SECONDS = 12;

export default function RecordScreen() {
  const { club } = useLocalSearchParams<{ club?: string }>();
  const clubName = club || 'Driver';
  const [available, setAvailable] = useState<boolean | null>(null);

  useEffect(() => {
    CameraView.isAvailableAsync()
      .then(setAvailable)
      .catch(() => setAvailable(false));
  }, []);

  if (available === null) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <AppText className="text-slate">Opening the camera…</AppText>
      </View>
    );
  }

  if (!available) {
    return <CameraMissing />;
  }

  return <Recorder clubName={clubName} />;
}

function CameraMissing() {
  const insets = useSafeAreaInsets();
  return (
    <View className="flex-1 bg-ink px-5" style={{ paddingTop: insets.top + 16 }}>
      <AppText weight="semibold" className="text-2xl">
        Record a swing
      </AppText>
      <AppText className="mt-3 text-base text-slate">This phone has no camera, so a swing can’t be recorded here.</AppText>
      <Pressable accessibilityRole="button" onPress={() => router.back()} className="mt-6 min-h-11 justify-center">
        <AppText weight="semibold" className="text-cyan">
          Back
        </AppText>
      </Pressable>
    </View>
  );
}

function Recorder({ clubName }: { clubName: string }) {
  const insets = useSafeAreaInsets();
  const cameraRef = useRef<CameraView>(null);
  const recording = useRef(false);
  const [ready, setReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [facing, setFacing] = useState<'back' | 'front'>('back');
  const [cameraPermission, requestCamera] = useCameraPermissions();
  const [micPermission, requestMic] = useMicrophonePermissions();
  const { recordSwing } = useGolf();

  useEffect(() => {
    if (!isRecording) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 200);
    return () => clearInterval(timer);
  }, [isRecording]);

  async function ensurePermissions(): Promise<boolean> {
    const camera = cameraPermission?.granted ? cameraPermission : await requestCamera();
    const mic = micPermission?.granted ? micPermission : await requestMic();
    return Boolean(camera?.granted && mic?.granted);
  }

  async function toggleRecording() {
    const camera = cameraRef.current;
    if (!camera || !ready) return;
    if (recording.current) {
      camera.stopRecording();
      return;
    }
    const allowed = await ensurePermissions();
    if (!allowed) {
      Alert.alert('Camera access is off', 'Allow the camera and microphone to record a swing.');
      return;
    }
    recording.current = true;
    setElapsed(0);
    setIsRecording(true);
    try {
      const video = await camera.recordAsync({ maxDuration: MAX_SECONDS });
      if (video?.uri) {
        await recordSwing({ source: 'camera', videoUri: video.uri, club: clubName });
        router.back();
      }
    } catch (error) {
      Alert.alert('Could not save the recording', error instanceof Error ? error.message : 'Try again.');
    } finally {
      recording.current = false;
      setIsRecording(false);
    }
  }

  return (
    <View className="flex-1 bg-ink">
      <CameraView
        ref={cameraRef}
        style={{ flex: 1 }}
        mode="video"
        facing={facing}
        onCameraReady={() => setReady(true)}
      />
      <View
        style={{ position: 'absolute', top: insets.top + 12, left: 20, right: 20 }}
        className="flex-row items-center justify-between"
      >
        <Pressable accessibilityRole="button" onPress={() => router.back()} className="min-h-11 justify-center">
          <AppText weight="medium">Close</AppText>
        </Pressable>
        <AppText className="text-sm">{isRecording ? formatElapsed(elapsed) : `${clubName} · ${MAX_SECONDS}s`}</AppText>
      </View>
      <View style={{ position: 'absolute', bottom: insets.bottom + 24, left: 0, right: 0 }} className="items-center">
        <Pressable
          accessibilityRole="button"
          accessibilityLabel={isRecording ? 'Stop recording' : 'Start recording'}
          onPress={() => void toggleRecording()}
          className="h-20 w-20 items-center justify-center rounded-full border-2 border-white"
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
          disabled={isRecording}
          onPress={() => setFacing((side) => (side === 'back' ? 'front' : 'back'))}
          className="mt-4 min-h-11 justify-center"
        >
          <AppText className="text-sm">{isRecording ? 'Recording' : 'Flip camera'}</AppText>
        </Pressable>
      </View>
    </View>
  );
}

function formatElapsed(seconds: number) {
  return `0:${String(Math.min(seconds, MAX_SECONDS)).padStart(2, '0')}`;
}
