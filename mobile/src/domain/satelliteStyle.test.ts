import { describe, expect, it } from 'vitest';
import { mapStyle } from './satelliteStyle';

describe('satellite style', () => {
  it('asks Esri for tiles in the row then column order they publish', () => {
    const style = mapStyle('satellite', '');
    expect(typeof style).not.toBe('string');
    if (typeof style === 'string') return;
    expect(style.sources.imagery.tiles[0]).toContain('/tile/{z}/{y}/{x}');
    expect(style.sources.imagery.maxzoom).toBe(19);
  });

  it('uses a MapTiler style when a key is set', () => {
    expect(mapStyle('satellite', 'abc')).toBe('https://api.maptiler.com/maps/satellite/style.json?key=abc');
    expect(mapStyle('terrain', 'abc')).toBe('https://api.maptiler.com/maps/outdoor/style.json?key=abc');
  });
});
