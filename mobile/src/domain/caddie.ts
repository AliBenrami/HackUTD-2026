import { COMPARE_PHASES } from './swingCompare';

export type PinPosition = 'front' | 'middle' | 'back';
export type MissSide = 'left' | 'right' | 'short' | 'long';
export type Aim = 'center' | 'left' | 'right';

export type ClubCarry = { name: string; carry: number };

export type CaddieCard = {
  club: string;
  carryYards: number;
  adjustedYards: number;
  aim: Aim;
  missTo: MissSide;
  windNote: string;
  reasons: string[];
  assumptions: string[];
  confidence: 'limited' | 'fair';
  source: 'gemini' | 'fallback';
  id?: string;
};

export const PIN_SHIFT: Record<PinPosition, number> = { front: -8, middle: 0, back: 8 };

export const STARTER_BAG: ClubCarry[] = [
  { name: 'Driver', carry: 230 },
  { name: '3-wood', carry: 215 },
  { name: '5-iron', carry: 175 },
  { name: '7-iron', carry: 155 },
  { name: '9-iron', carry: 135 },
  { name: 'Pitching wedge', carry: 120 },
  { name: 'Sand wedge', carry: 90 },
];

export function targetYards(holeYards: number, pin: PinPosition): number {
  return Math.max(1, holeYards + PIN_SHIFT[pin]);
}

export function courseHandicap(index: number, slope: number, rating: number, par: number): number | null {
  if (!Number.isFinite(index) || index < 0 || index > 54) return null;
  if (!Number.isFinite(slope) || slope < 55 || slope > 155) return null;
  if (!Number.isFinite(rating) || !Number.isFinite(par)) return null;
  return Math.round(index * (slope / 113) + (rating - par));
}

export function pickClub(bag: ClubCarry[], yards: number): ClubCarry {
  const clubs = bag.length > 0 ? bag : STARTER_BAG;
  return clubs.reduce((best, club) =>
    Math.abs(club.carry - yards) < Math.abs(best.carry - yards) ? club : best,
  );
}

export type WindReading = {
  speedMph: number;
  gustMph: number | null;
  fromDeg: number;
};

export function windPhrase(wind: WindReading, holeBearingDeg: number | null): { phrase: string; yardAdjust: number } {
  const speed = Math.max(0, Math.round(wind.speedMph));
  if (holeBearingDeg == null) {
    return { phrase: `${speed} mph from the ${compass(wind.fromDeg)}`, yardAdjust: 0 };
  }
  const delta = angleBetween(wind.fromDeg, holeBearingDeg);
  if (delta < 50) return { phrase: `${speed} mph into you`, yardAdjust: speed };
  if (delta > 130) return { phrase: `${speed} mph downwind`, yardAdjust: -speed };
  const side = Math.sin(((wind.fromDeg - holeBearingDeg) * Math.PI) / 180) > 0 ? 'right' : 'left';
  return { phrase: `${speed} mph from the ${side}`, yardAdjust: 0 };
}

function angleBetween(a: number, b: number): number {
  const delta = Math.abs(a - b) % 360;
  return delta > 180 ? 360 - delta : delta;
}

function compass(degrees: number): string {
  const names = ['north', 'northeast', 'east', 'southeast', 'south', 'southwest', 'west', 'northwest'];
  return names[Math.round(((degrees % 360) + 360) % 360 / 45) % 8];
}

export function fallbackCard(input: {
  bag: ClubCarry[];
  holeYards: number;
  pin: PinPosition;
  wind: WindReading | null;
  windOn: boolean;
  holeBearingDeg: number | null;
  commonMiss: MissSide | null;
}): CaddieCard {
  const wind = input.windOn && input.wind ? windPhrase(input.wind, input.holeBearingDeg) : null;
  const playing = targetYards(input.holeYards, input.pin) + (wind?.yardAdjust ?? 0);
  const club = pickClub(input.bag, playing);
  const reasons = [`${club.name} is the closest club in your bag to ${Math.round(playing)} yards.`];
  if (input.pin !== 'middle') {
    reasons.push(input.pin === 'front' ? 'The pin is up, so the target is 8 yards shorter.' : 'The pin is back, so the target is 8 yards longer.');
  }
  return {
    club: club.name,
    carryYards: club.carry,
    adjustedYards: club.carry + (wind?.yardAdjust ?? 0),
    aim: 'center',
    missTo: input.commonMiss ?? 'left',
    windNote: wind ? `${wind.phrase}.` : '',
    reasons: reasons.slice(0, 3),
    assumptions: ['Carries are the bag you entered.', 'The model was not used.'],
    confidence: 'limited',
    source: 'fallback',
  };
}

export function validateCard(value: unknown, bag: ClubCarry[]): CaddieCard | null {
  if (!value || typeof value !== 'object') return null;
  const card = value as Record<string, unknown>;
  const club = bag.find((item) => item.name === card.club);
  if (!club || card.carryYards !== club.carry) return null;
  if (typeof card.adjustedYards !== 'number' || Math.abs(card.adjustedYards - club.carry) > 40) return null;
  if (card.aim !== 'center' && card.aim !== 'left' && card.aim !== 'right') return null;
  if (card.missTo !== 'left' && card.missTo !== 'right' && card.missTo !== 'short' && card.missTo !== 'long') return null;
  if (typeof card.windNote !== 'string' || card.windNote.length > 180) return null;
  if (!Array.isArray(card.reasons) || card.reasons.length === 0 || card.reasons.length > 3) return null;
  if (!card.reasons.every((reason) => typeof reason === 'string' && reason.length > 0 && reason.length <= 180)) return null;
  if (!Array.isArray(card.assumptions) || card.assumptions.length > 4) return null;
  if (!card.assumptions.every((item) => typeof item === 'string' && item.length <= 180)) return null;
  if (card.confidence !== 'limited' && card.confidence !== 'fair') return null;
  return {
    club: club.name,
    carryYards: club.carry,
    adjustedYards: Math.round(card.adjustedYards),
    aim: card.aim,
    missTo: card.missTo,
    windNote: card.windNote,
    reasons: card.reasons,
    assumptions: card.assumptions,
    confidence: card.confidence,
    source: 'gemini',
  };
}

export function angleVector(
  events: Array<{ name: string; angles: { leftElbow: number | null; rightElbow: number | null } }>,
): Array<number | null> {
  const byName = new Map(events.map((event) => [event.name, event]));
  const vector: Array<number | null> = [];
  for (const phase of COMPARE_PHASES) {
    const event = byName.get(phase);
    vector.push(usableElbow(event?.angles.leftElbow ?? null), usableElbow(event?.angles.rightElbow ?? null));
  }
  return vector;
}

function usableElbow(value: number | null): number | null {
  if (value == null || !Number.isFinite(value) || value < 55 || value > 180) return null;
  return value;
}

export function commonMiss(counts: Partial<Record<MissSide, number>>): MissSide | null {
  const entries = (Object.entries(counts) as Array<[MissSide, number | undefined]>).filter(
    (entry): entry is [MissSide, number] => (entry[1] ?? 0) > 0,
  );
  if (entries.length === 0) return null;
  entries.sort((a, b) => b[1] - a[1]);
  return entries[0][0];
}
