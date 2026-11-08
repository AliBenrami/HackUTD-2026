import { fallbackCard, type CaddieCard, type ClubCarry, type PinPosition, type WindReading } from '../../domain/caddie';
import type { Shot } from '../../domain/geo';
import type { SwingInsight } from '../../domain/swingCompare';

export type HoleNote = {
  roundId: string;
  holeNumber: number;
  par: number;
  strokes: number | null;
  sample: boolean;
  miss: 'left' | 'right' | 'short' | 'long' | null;
  gir: boolean | null;
  pin: PinPosition;
  club: string | null;
  cardId: string | null;
  shots: Shot[];
};

export type Bag = {
  clubs: ClubCarry[];
  handicapIndex: number | null;
  starter: boolean;
  tendencies: {
    holes: number;
    misses: Partial<Record<'left' | 'right' | 'short' | 'long', number>>;
  };
};

export type CardRequest = {
  userId: string;
  roundId: string;
  courseId: string;
  courseName: string;
  holeNumber: number;
  par: number;
  yards: number;
  handicap: number;
  pin: PinPosition;
  windOn: boolean;
  holeBearing: number | null;
  center: { lat: number; lng: number } | null;
};

function baseUrl() {
  return process.env.EXPO_PUBLIC_SWING_API_URL?.replace(/\/$/, '') ?? '';
}

async function request(path: string, init?: RequestInit): Promise<Response> {
  const base = baseUrl();
  if (!base) throw new Error('Set EXPO_PUBLIC_SWING_API_URL to the golf server.');
  return fetch(`${base}${path}`, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
  });
}

export async function loadBag(userId: string): Promise<Bag> {
  const response = await request(`/bag?user_id=${encodeURIComponent(userId)}`);
  if (!response.ok) throw new Error(await response.text());
  const body = (await response.json()) as Bag;
  return {
    clubs: body.clubs,
    handicapIndex: body.handicapIndex ?? null,
    starter: Boolean(body.starter),
    tendencies: body.tendencies ?? { holes: 0, misses: {} },
  };
}

export async function saveBag(userId: string, clubs: ClubCarry[], handicapIndex: number | null): Promise<Bag> {
  const response = await request('/bag', {
    method: 'PUT',
    body: JSON.stringify({ userId, clubs, handicapIndex }),
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

export async function loadNotes(userId: string, roundId?: string): Promise<HoleNote[]> {
  const query = new URLSearchParams({ user_id: userId });
  if (roundId) query.set('round_id', roundId);
  const response = await request(`/notes?${query.toString()}`);
  if (!response.ok) throw new Error(await response.text());
  const body = (await response.json()) as { notes: HoleNote[] };
  return body.notes ?? [];
}

export async function saveNote(userId: string, note: HoleNote): Promise<void> {
  const response = await request('/notes', { method: 'PUT', body: JSON.stringify({ userId, ...note }) });
  if (!response.ok) throw new Error(await response.text());
}

export async function requestCard(input: CardRequest, bag: ClubCarry[]): Promise<CaddieCard> {
  try {
    const response = await request('/caddie/card', { method: 'POST', body: JSON.stringify(input) });
    if (!response.ok) throw new Error(await response.text());
    return response.json();
  } catch {
    return fallbackCard({
      bag,
      holeYards: input.yards,
      pin: input.pin,
      wind: null,
      windOn: false,
      holeBearingDeg: input.holeBearing,
      commonMiss: null,
    });
  }
}

export async function loadWeather(courseId: string, center: { lat: number; lng: number } | null): Promise<WindReading | null> {
  try {
    const query = new URLSearchParams({ course_id: courseId });
    if (center) {
      query.set('lat', String(center.lat));
      query.set('lng', String(center.lng));
    }
    const response = await request(`/weather?${query.toString()}`);
    if (!response.ok) return null;
    const body = (await response.json()) as { wind: WindReading | null };
    return body.wind;
  } catch {
    return null;
  }
}

export async function requestRecap(userId: string, roundId: string, summary: unknown, notes: HoleNote[]): Promise<string[] | null> {
  const response = await request('/caddie/recap', {
    method: 'POST',
    body: JSON.stringify({ userId, roundId, summary, notes }),
  });
  if (!response.ok) return null;
  const body = (await response.json()) as { lines: string[] | null };
  return body.lines && body.lines.length === 4 ? body.lines : null;
}

export async function loadRecap(userId: string, roundId: string): Promise<string[] | null> {
  const query = new URLSearchParams({ user_id: userId, round_id: roundId });
  const response = await request(`/caddie/recap?${query.toString()}`);
  if (!response.ok) return null;
  const body = (await response.json()) as { lines: string[] | null };
  return body.lines && body.lines.length === 4 ? body.lines : null;
}

export async function requestNarration(packet: unknown): Promise<Array<{ id: string; observation: string; why: string }> | null> {
  const response = await request('/caddie/narrate', { method: 'POST', body: JSON.stringify(packet) });
  if (!response.ok) return null;
  const body = (await response.json()) as { insights?: Array<{ id: string; observation: string; why: string }> | null };
  return body.insights ?? null;
}

export function applyNarration(insights: SwingInsight[], lines: Array<{ id: string; observation: string; why: string }> | null): SwingInsight[] {
  if (!lines) return insights;
  return insights.map((insight) => {
    const line = lines.find((item) => item.id === insight.id);
    if (!line) return insight;
    const degrees = insight.observation.match(/\d+(\.\d+)?°/);
    if (!degrees || !line.observation.includes(degrees[0])) return insight;
    return { ...insight, observation: line.observation, why: line.why };
  });
}

export async function saveSwingDocument(input: {
  userId: string;
  videoId: string;
  club: string;
  angleVector: Array<number | null>;
  measured: unknown;
}): Promise<void> {
  await request('/swings', { method: 'POST', body: JSON.stringify(input) });
}

export async function similarSwing(userId: string, videoId: string, angleVector: Array<number | null>): Promise<{
  close: boolean;
  club?: string;
  createdAt?: string;
  rms?: number;
  reason?: string;
} | null> {
  const response = await request('/swings/similar', {
    method: 'POST',
    body: JSON.stringify({ userId, videoId, angleVector }),
  });
  if (!response.ok) return null;
  return response.json();
}
