import * as Location from 'expo-location';
import { useEffect, useState } from 'react';
import { Platform, Pressable, View } from 'react-native';
import { courseCenter, holeDrawing } from '../data/courseMaps';
import { pickClub, windPhrase, type CaddieCard, type ClubCarry, type MissSide, type PinPosition } from '../domain/caddie';
import { guessLanding, holeBearing, placeShot, yardsBetween, type Shot } from '../domain/geo';
import type { HoleNote } from '../services/golf/client';
import { loadWeather, requestCard } from '../services/golf/client';
import { AppText } from './ui';
import { CaddieCardView } from './CaddieCard';
import { HoleMap } from './HoleMap';

export type HoleDraft = {
  miss: MissSide | null;
  gir: boolean | null;
  pin: PinPosition;
  shots: Shot[];
  club: string | null;
  cardId: string | null;
};

async function locatePhone(): Promise<{ lng: number; lat: number } | null> {
  const read = (async () => {
    const permission = await Location.requestForegroundPermissionsAsync();
    if (!permission.granted) return null;
    const position = await Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced });
    return { lng: position.coords.longitude, lat: position.coords.latitude };
  })();
  try {
    if (Platform.OS !== 'web') return await read;
    return await Promise.race([
      read,
      new Promise<null>((resolve) => setTimeout(() => resolve(null), 1500)),
    ]);
  } catch {
    return null;
  }
}

const PINS: PinPosition[] = ['front', 'middle', 'back'];
const MISSES: Array<MissSide | null> = ['left', 'right', 'short', 'long', null];

export function HoleTools({
  userId,
  roundId,
  courseId,
  courseName,
  teeName,
  holeNumber,
  par,
  yards,
  handicap,
  windOn,
  bag,
  saved,
  onChange,
}: {
  userId: string;
  roundId: string;
  courseId: string;
  courseName: string;
  teeName: string;
  holeNumber: number;
  par: number;
  yards: number;
  handicap: number;
  windOn: boolean;
  bag: ClubCarry[];
  saved: HoleNote | null;
  onChange: (draft: HoleDraft) => void;
}) {
  const drawing = holeDrawing(courseId, holeNumber, teeName);
  const [pin, setPin] = useState<PinPosition>(saved?.pin ?? 'middle');
  const [miss, setMiss] = useState<MissSide | null>(saved?.miss ?? null);
  const [gir, setGir] = useState<boolean | null>(saved?.gir ?? null);
  const [shots, setShots] = useState<Shot[]>(saved?.shots ?? []);
  const [card, setCard] = useState<CaddieCard | null>(null);
  const [guessNote, setGuessNote] = useState<string | null>(null);
  const [windLine, setWindLine] = useState<string | null>(null);

  useEffect(() => {
    setPin(saved?.pin ?? 'middle');
    setMiss(saved?.miss ?? null);
    setGir(saved?.gir ?? null);
    setShots(saved?.shots ?? []);
    setCard(null);
    setGuessNote(null);
  }, [saved, holeNumber, roundId]);

  useEffect(() => {
    onChange({ miss, gir, pin, shots, club: card?.club ?? null, cardId: card?.id ?? null });
  }, [card, gir, miss, onChange, pin, shots]);

  useEffect(() => {
    let alive = true;
    const center = courseCenter(courseId);
    const bearing = drawing ? holeBearing(drawing.tee, drawing.greenCenter) : null;
    if (windOn) {
      void loadWeather(courseId, center).then((wind) => {
        if (alive && wind) setWindLine(windPhrase(wind, bearing).phrase);
      });
    } else {
      setWindLine(null);
    }
    void requestCard(
      {
        userId,
        roundId,
        courseId,
        courseName,
        holeNumber,
        par,
        yards,
        handicap,
        pin,
        windOn,
        holeBearing: bearing,
        center,
      },
      bag,
    ).then((next) => {
      if (alive) setCard(next);
    });
    return () => {
      alive = false;
    };
  }, [bag, courseId, courseName, handicap, holeNumber, par, pin, roundId, teeName, userId, windOn, yards]);

  async function guess() {
    if (!drawing) return;
    const phone = await locatePhone();
    const origin = shots.length ? shots[shots.length - 1] : drawing.tee;
    const remaining = yardsBetween(origin, drawing.greenCenter);
    const carry = pickClub(bag, remaining).carry;
    const landing = guessLanding({
      path: drawing.centerline.length > 1 ? drawing.centerline : [drawing.tee, drawing.greenCenter],
      green: drawing.greenCenter,
      shots,
      phone,
      carryYards: carry,
    });
    setShots((current) => placeShot(current, landing.point, landing.source));
    setGuessNote(landing.note);
  }

  return (
    <View className="mt-4">
      {drawing ? (
        <>
          <HoleMap
            hole={drawing}
            shots={shots}
            onTap={(point) => {
              setShots((current) => placeShot(current, point, 'tap'));
              setGuessNote(null);
            }}
          />
          <View className="mt-3 flex-row gap-2">
            <Mini label="Guess landing" onPress={() => void guess()} />
            <Mini
              label="Undo stroke"
              onPress={() => setShots((current) => current.slice(0, -1).map((shot, index) => ({ ...shot, n: index + 1 })))}
            />
          </View>
          {guessNote ? <AppText className="mt-2 text-sm text-slate">{guessNote}</AppText> : null}
          <AppText className="mt-2 text-sm text-slate">
            {shots.length === 0
              ? `${yards} yards from the tee to the green.`
              : `${Math.round(yardsBetween(shots[shots.length - 1], drawing.greenCenter))} yards from the last mark to the green.`}
          </AppText>
        </>
      ) : null}
      {windOn && windLine && !card?.windNote ? <AppText className="mt-3 text-sm">{windLine}</AppText> : null}
      <View className="mt-4 flex-row gap-2">
        {PINS.map((value) => (
          <Choice key={value} label={value === 'middle' ? 'Middle' : value === 'front' ? 'Front pin' : 'Back pin'} selected={pin === value} onPress={() => setPin(value)} />
        ))}
      </View>
      <AppText className="mt-2 text-xs text-slate">Front shortens the target 8 yards. Back adds 8. That is a convention, not a laser.</AppText>
      {card ? <CaddieCardView card={card} /> : null}
      <AppText className="mb-2 mt-4 text-sm text-slate">Where the tee shot missed</AppText>
      <View className="flex-row flex-wrap gap-2">
        {MISSES.map((value) => (
          <Choice key={value ?? 'skip'} label={value ?? 'Skip'} selected={miss === value} onPress={() => setMiss(value)} />
        ))}
      </View>
      <AppText className="mb-2 mt-4 text-sm text-slate">Green in regulation</AppText>
      <View className="flex-row gap-2">
        <Choice label="Yes" selected={gir === true} onPress={() => setGir(true)} />
        <Choice label="No" selected={gir === false} onPress={() => setGir(false)} />
        <Choice label="Skip" selected={gir == null} onPress={() => setGir(null)} />
      </View>
    </View>
  );
}

function Choice({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      className={`min-h-10 flex-1 items-center justify-center rounded-full border px-3 ${selected ? 'border-cyan' : 'border-white/10'}`}
    >
      <AppText className={`text-sm capitalize ${selected ? 'text-cyan' : ''}`}>{label}</AppText>
    </Pressable>
  );
}

function Mini({ label, onPress }: { label: string; onPress: () => void }) {
  return (
    <Pressable accessibilityRole="button" onPress={onPress} className="min-h-11 flex-1 items-center justify-center rounded-full border border-white/10">
      <AppText className="text-sm">{label}</AppText>
    </Pressable>
  );
}
