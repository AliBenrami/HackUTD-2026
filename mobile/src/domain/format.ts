import type { Units } from './types';

const YARDS_TO_METERS = 0.9144;

export function formatRelative(value: number): { symbol: string; words: string } {
  if (value === 0) return { symbol: 'E', words: 'Even par' };
  if (value > 0) return { symbol: `+${value}`, words: `${value} over par` };
  return { symbol: `${value}`, words: `${Math.abs(value)} under par` };
}

export function formatAverageRelative(value: number): { symbol: string; words: string } {
  const rounded = Math.round(value * 10) / 10;
  if (Object.is(rounded, -0) || rounded === 0) {
    return { symbol: 'E', words: 'Even par per hole' };
  }
  const abs = Math.abs(rounded);
  const text = Number.isInteger(abs) ? String(abs) : abs.toFixed(1);
  if (rounded > 0) return { symbol: `+${text}`, words: `${text} over par per hole` };
  return { symbol: `-${text}`, words: `${text} under par per hole` };
}

export function formatDecimal(value: number | null, digits = 1): string {
  if (value == null || Number.isNaN(value)) return '—';
  const factor = 10 ** digits;
  const rounded = Math.round(value * factor) / factor;
  if (Number.isInteger(rounded)) return String(rounded);
  return rounded.toFixed(digits);
}

export function formatPercent(value: number | null): string {
  if (value == null || Number.isNaN(value)) return '—';
  return `${Math.round(value)}%`;
}

export function formatCount(value: number | null): string {
  if (value == null) return '—';
  return String(value);
}

export function convertDistance(yards: number, units: Units): number {
  if (units === 'meters') return Math.round(yards * YARDS_TO_METERS);
  return yards;
}

export function formatDistance(yards: number, units: Units): string {
  const value = convertDistance(yards, units);
  return units === 'meters' ? `${value} m` : `${value} yd`;
}

export function formatWhen(iso: string): string {
  return new Date(iso).toLocaleDateString(undefined, { month: 'short', day: 'numeric' });
}

export function formatClock(iso: string): string {
  return new Date(iso).toLocaleTimeString(undefined, { hour: 'numeric', minute: '2-digit' });
}
