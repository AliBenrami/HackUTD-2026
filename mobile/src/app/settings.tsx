import { router } from 'expo-router';
import { useState } from 'react';
import { Switch, TextInput, View } from 'react-native';
import { AppText, BackHeader, Button, Screen } from '../components/ui';
import { formatClock, formatWhen } from '../domain/format';
import type { ARPreferences, HudPreferences, Units } from '../domain/types';
import { useGolf } from '../state/GolfContext';
import { colors, fonts } from '../theme/colors';

export default function SettingsScreen() {
  const { player, preferences, updatePlayerName, updatePreferences, setDeviceLinked, signOut } = useGolf();
  const [name, setName] = useState(player.name);

  function patch(next: ARPreferences) {
    void updatePreferences(next);
  }

  function toggleHud(key: keyof HudPreferences) {
    patch({ ...preferences, hud: { ...preferences.hud, [key]: !preferences.hud[key] } });
  }

  return (
    <Screen header={<BackHeader title="Settings" onBack={() => router.back()} />}>
      <AppText className="text-sm text-slate">
        The visor link is simulated. Arcade play stays in the separate AR experience. This app keeps real rounds and can hand a score snapshot across when a device is linked.
      </AppText>

      <AppText weight="semibold" className="mb-2 mt-6 text-lg">
        Player
      </AppText>
      <TextInput
        value={name}
        onChangeText={setName}
        onEndEditing={() => void updatePlayerName(name)}
        placeholder="Your name"
        placeholderTextColor={colors.slate}
        className="min-h-12 rounded-2xl border border-white/10 bg-panel px-4 text-base"
        style={{ fontFamily: fonts.regular, color: colors.mist }}
      />

      <AppText weight="semibold" className="mb-2 mt-6 text-lg">
        AR device
      </AppText>
      <View className="rounded-3xl border border-white/10 bg-panel p-4">
        <AppText weight="semibold">{preferences.device.name}</AppText>
        <AppText className="mt-1 text-sm text-slate">
          {preferences.device.connected
            ? `Simulated link · ${preferences.device.model}`
            : 'Not linked'}
        </AppText>
        {preferences.device.connected ? (
          <AppText className="mt-2 text-sm text-slate">
            Battery {preferences.device.battery}% · Firmware {preferences.device.firmware}
          </AppText>
        ) : null}
        <AppText className="mt-2 text-sm text-slate">
          {preferences.lastSyncAt
            ? `Last score sent ${formatWhen(preferences.lastSyncAt)} at ${formatClock(preferences.lastSyncAt)}`
            : 'No score has been sent yet.'}
        </AppText>
        <View className="mt-4">
          <Button
            label={preferences.device.connected ? 'Disconnect' : 'Simulate link'}
            variant={preferences.device.connected ? 'secondary' : 'primary'}
            onPress={() => void setDeviceLinked(!preferences.device.connected)}
          />
        </View>
      </View>

      <AppText weight="semibold" className="mb-2 mt-6 text-lg">
        Units
      </AppText>
      <View className="flex-row gap-2">
        <UnitChoice
          label="Yards"
          selected={preferences.units === 'yards'}
          onPress={() => patch({ ...preferences, units: 'yards' satisfies Units })}
        />
        <UnitChoice
          label="Meters"
          selected={preferences.units === 'meters'}
          onPress={() => patch({ ...preferences, units: 'meters' })}
        />
      </View>

      <AppText weight="semibold" className="mb-2 mt-6 text-lg">
        Visor readout
      </AppText>
      <Toggle
        label="Distance"
        value={preferences.hud.showDistance}
        onChange={() => toggleHud('showDistance')}
      />
      <Toggle
        label="Elevation"
        value={preferences.hud.showElevation}
        onChange={() => toggleHud('showElevation')}
      />
      <Toggle label="Score" value={preferences.hud.showScore} onChange={() => toggleHud('showScore')} />
      <Toggle label="Wind" value={preferences.hud.showWind} onChange={() => toggleHud('showWind')} />

      <View className="mt-2">
        <Toggle
          label="Send scores to the visor"
          value={preferences.syncScores}
          onChange={() => patch({ ...preferences, syncScores: !preferences.syncScores })}
        />
      </View>
      <AppText className="mt-2 text-xs text-slate">
        Rounds stay on your account. A linked visor only receives a score when sending is on.
      </AppText>
      <View className="mt-8">
        <Button label="Sign out" variant="secondary" onPress={() => void signOut()} />
      </View>
    </Screen>
  );
}

function UnitChoice({
  label,
  selected,
  onPress,
}: {
  label: string;
  selected: boolean;
  onPress: () => void;
}) {
  return (
    <View className="flex-1">
      <Button label={label} variant={selected ? 'primary' : 'secondary'} onPress={onPress} />
    </View>
  );
}

function Toggle({
  label,
  value,
  onChange,
}: {
  label: string;
  value: boolean;
  onChange: () => void;
}) {
  return (
    <View className="mb-3 min-h-14 flex-row items-center justify-between rounded-2xl border border-white/10 bg-panel px-4">
      <AppText>{label}</AppText>
      <Switch
        accessibilityLabel={label}
        value={value}
        onValueChange={onChange}
        trackColor={{ false: '#243041', true: colors.cyan }}
        thumbColor={colors.mist}
      />
    </View>
  );
}
