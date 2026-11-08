import { router } from 'expo-router';
import { useState } from 'react';
import { TextInput, View } from 'react-native';
import { AppText, BackHeader, Button, Screen } from '../components/ui';
import type { ClubCarry } from '../domain/caddie';
import { useGolf } from '../state/GolfContext';
import { colors, fonts } from '../theme/colors';

export default function BagScreen() {
  const { bag, updateBag } = useGolf();
  const [clubs, setClubs] = useState<ClubCarry[]>(bag.clubs);
  const [name, setName] = useState('');
  const [carry, setCarry] = useState('');

  function editCarry(index: number, value: string) {
    const next = Number(value);
    setClubs((current) => current.map((club, clubIndex) => (clubIndex === index ? { ...club, carry: Number.isFinite(next) ? next : club.carry } : club)));
  }

  return (
    <Screen header={<BackHeader title="Bag" onBack={() => router.back()} />}>
      <AppText className="text-sm text-slate">
        {bag.starter
          ? 'These are starter carries. Change them to the distances you actually hit.'
          : 'The hole card uses these carries.'}
      </AppText>
      {clubs.map((club, index) => (
        <View key={`${club.name}-${index}`} className="mt-3 flex-row items-center gap-3">
          <AppText className="flex-1">{club.name}</AppText>
          <TextInput
            value={String(club.carry)}
            onChangeText={(value) => editCarry(index, value)}
            keyboardType="number-pad"
            className="h-11 w-20 rounded-2xl border border-white/10 bg-panel text-center"
            style={{ fontFamily: fonts.regular, color: colors.mist }}
          />
          <AppText className="text-sm text-slate">yds</AppText>
        </View>
      ))}
      <View className="mt-6 flex-row gap-2">
        <TextInput
          value={name}
          onChangeText={setName}
          placeholder="Club"
          placeholderTextColor={colors.slate}
          className="h-12 flex-1 rounded-2xl border border-white/10 bg-panel px-3"
          style={{ fontFamily: fonts.regular, color: colors.mist }}
        />
        <TextInput
          value={carry}
          onChangeText={setCarry}
          placeholder="Yards"
          placeholderTextColor={colors.slate}
          keyboardType="number-pad"
          className="h-12 w-24 rounded-2xl border border-white/10 bg-panel px-3"
          style={{ fontFamily: fonts.regular, color: colors.mist }}
        />
      </View>
      <View className="mt-3">
        <Button
          label="Add club"
          variant="secondary"
          onPress={() => {
            const yards = Number(carry);
            if (!name.trim() || !Number.isFinite(yards) || yards <= 0) return;
            setClubs((current) => [...current, { name: name.trim(), carry: yards }]);
            setName('');
            setCarry('');
          }}
        />
      </View>
      <View className="mt-6">
        <Button label="Save bag" onPress={() => void updateBag(clubs, bag.handicapIndex)} />
      </View>
    </Screen>
  );
}
