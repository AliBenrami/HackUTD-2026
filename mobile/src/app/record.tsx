import { CameraView, useCameraPermissions, useMicrophonePermissions } from 'expo-camera';
import { router, useLocalSearchParams } from 'expo-router';
import { useEffect, useRef, useState } from 'react';
import { Alert, Linking, Pressable, View } from 'react-native';
import { useSafeAreaInsets } from 'react-native-safe-area-context';
import { AppText, Button } from '../components/ui';
import { useGolf } from '../state/GolfContext';
import { colors } from '../theme/colors';

const MAX_SECONDS = 12;

export default function RecordScreen() {
  const { club } = useLocalSearchParams<{ club?: string }>();
  return <Recorder clubName={club || 'Driver'} />;
}

function Recorder({ clubName }: { clubName: string }) {
  const insets = useSafeAreaInsets();
  const cameraRef = useRef<CameraView>(null);
  const recording = useRef(false);
  const asked = useRef(false);
  const [ready, setReady] = useState(false);
  const [isRecording, setIsRecording] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [facing, setFacing] = useState<'back' | 'front'>('back');
  const [mountError, setMountError] = useState<string | null>(null);
  const [cameraPermission, requestCamera] = useCameraPermissions();
  const [micPermission, requestMic] = useMicrophonePermissions();
  const { recordSwing } = useGolf();

  const cameraGranted = Boolean(cameraPermission?.granted);
  const micGranted = Boolean(micPermission?.granted);
  const canAskAgain = Boolean(
    (cameraPermission && !cameraPermission.granted && cameraPermission.canAskAgain) ||
      (micPermission && !micPermission.granted && micPermission.canAskAgain)
  );

  useEffect(() => {
    if (asked.current || !cameraPermission || !micPermission) return;
    if (cameraGranted && micGranted) return;
    if (!cameraPermission.canAskAgain && !micPermission.canAskAgain) return;
    asked.current = true;
    void (async () => {
      if (!cameraPermission.granted && cameraPermission.canAskAgain) await requestCamera();
      if (!micPermission.granted && micPermission.canAskAgain) await requestMic();
    })();
  }, [cameraGranted, cameraPermission, micGranted, micPermission, requestCamera, requestMic]);

  useEffect(() => {
    if (!isRecording) return;
    const started = Date.now();
    const timer = setInterval(() => setElapsed(Math.floor((Date.now() - started) / 1000)), 200);
    return () => clearInterval(timer);
  }, [isRecording]);

  async function allowAccess() {
    const camera =
      cameraPermission && !cameraPermission.granted && cameraPermission.canAskAgain
        ? await requestCamera()
        : cameraPermission;
    const mic =
      micPermission && !micPermission.granted && micPermission.canAskAgain ? await requestMic() : micPermission;
    const blocked =
      (camera && !camera.granted && !camera.canAskAgain) || (mic && !mic.granted && !mic.canAskAgain);
    if (blocked) await Linking.openSettings();
  }

  async function toggleRecording() {
    const camera = cameraRef.current;
    if (!camera || !ready) return;
    if (recording.current) {
      camera.stopRecording();
      return;
    }
    if (!cameraGranted || !micGranted) {
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

  if (!cameraPermission || !micPermission) {
    return (
      <View className="flex-1 items-center justify-center bg-ink">
        <AppText className="text-slate">Opening the camera…</AppText>
      </View>
    );
  }

  if (!cameraGranted || !micGranted || mountError) {
    return (
      <View className="flex-1 bg-ink px-5" style={{ paddingTop: insets.top + 16 }}>
        <AppText weight="semibold" className="text-2xl">
          Record a swing
        </AppText>
        <AppText className="mt-3 text-base text-slate">
          {mountError ?? 'Allow the camera and microphone so a swing can be recorded.'}
        </AppText>
        <View className="mt-6">
          <Button label={canAskAgain ? 'Allow camera' : 'Open Settings'} onPress={() => void allowAccess()} />
        </View>
        <Pressable accessibilityRole="button" onPress={() => router.back()} className="mt-4 min-h-11 justify-center">
          <AppText weight="semibold" className="text-cyan">
            Back
          </AppText>
        </Pressable>
      </View>
    );
  }

  return (
    <View className="flex-1 bg-ink">
      <CameraView
        ref={cameraRef}
        style={{ flex: 1 }}
        mode="video"
        facing={facing}
        onCameraReady={() => setReady(true)}
        onMountError={({ message }) => setMountError(message)}
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
