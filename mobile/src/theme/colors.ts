export const colors = {
  ink: '#080C12',
  panel: '#111923',
  panelRaised: '#172232',
  line: 'rgba(243,246,250,0.08)',
  cyan: '#00D9E8',
  violet: '#8B5CF6',
  magenta: '#E879F9',
  mist: '#F3F6FA',
  slate: '#8B97A8',
  bogey: '#C4B5FD',
} as const;

export const fonts = {
  regular: 'Outfit_400Regular',
  medium: 'Outfit_500Medium',
  semibold: 'Outfit_600SemiBold',
  bold: 'Outfit_700Bold',
} as const;

export type FontWeight = keyof typeof fonts;

export function resultTone(delta: number): string {
  if (delta < 0) return colors.cyan;
  if (delta === 0) return colors.mist;
  if (delta === 1) return colors.bogey;
  return colors.magenta;
}
