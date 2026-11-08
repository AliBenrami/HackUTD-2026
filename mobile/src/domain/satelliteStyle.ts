export type MapLook = 'satellite' | 'terrain';

const ESRI = {
  satellite: {
    tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, Maxar, Earthstar Geographics',
  },
  terrain: {
    tiles: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Topo_Map/MapServer/tile/{z}/{y}/{x}',
    attribution: 'Esri, HERE, Garmin, USGS',
  },
} as const;

export function mapStyle(look: MapLook, key = process.env.EXPO_PUBLIC_MAPTILER_KEY?.trim() ?? '') {
  if (key) {
    const name = look === 'satellite' ? 'satellite' : 'outdoor';
    return `https://api.maptiler.com/maps/${name}/style.json?key=${key}`;
  }
  const source = ESRI[look];
  return {
    version: 8 as const,
    sources: {
      imagery: {
        type: 'raster' as const,
        tiles: [source.tiles],
        tileSize: 256,
        maxzoom: 19,
        attribution: source.attribution,
      },
    },
    layers: [{ id: 'imagery', type: 'raster' as const, source: 'imagery' }],
  };
}
