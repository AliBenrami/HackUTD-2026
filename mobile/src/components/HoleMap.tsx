import { useEffect, useRef, useState } from 'react';
import { View } from 'react-native';
import type { GeoJSONSource, Map as MlMap, Marker as MlMarker, StyleSpecification } from 'maplibre-gl';
import { holePoints, type HoleDrawing } from '../data/courseMaps';
import { regionFor, shotPath, yardsBetween, type MapPoint, type Shot } from '../domain/geo';
import { mapStyle, type MapLook } from '../domain/satelliteStyle';
import { colors } from '../theme/colors';
import { AppText } from './ui';
import { MapChrome } from './MapChrome';

export type { HoleDrawing };

const MAP_CSS = `
.maplibregl-map { position: relative; overflow: hidden; width: 100%; height: 100%; }
.maplibregl-canvas-container { position: absolute; inset: 0; width: 100%; height: 100%; }
.maplibregl-canvas { position: absolute; left: 0; top: 0; }
.maplibregl-canvas-container.maplibregl-interactive { touch-action: none; }
.maplibregl-ctrl-bottom-right, .maplibregl-ctrl-bottom-left { position: absolute; bottom: 0; z-index: 2; margin: 0; }
.maplibregl-ctrl-bottom-right { right: 0; }
.maplibregl-ctrl-bottom-left { left: 0; }
.maplibregl-ctrl-attrib { background: rgba(8,12,18,0.72); color: #c5ced9; font-size: 10px; padding: 2px 6px; }
.maplibregl-ctrl-attrib a { color: #c5ced9; text-decoration: none; }
.maplibregl-marker { position: absolute; top: 0; left: 0; will-change: transform; }
`;

function ensureCss() {
  if (typeof document === 'undefined') return;
  const existing = document.getElementById('golfar-maplibre-css');
  if (existing) {
    existing.textContent = MAP_CSS;
    return;
  }
  const style = document.createElement('style');
  style.id = 'golfar-maplibre-css';
  style.textContent = MAP_CSS;
  document.head.appendChild(style);
}

function dot(label: string, color: string, filled: boolean) {
  const node = document.createElement('div');
  node.textContent = label;
  node.style.cssText = [
    'display:flex',
    'align-items:center',
    'justify-content:center',
    'border-radius:999px',
    'pointer-events:none',
    'font:700 11px Outfit, sans-serif',
    `width:${label ? 22 : 14}px`,
    `height:${label ? 22 : 14}px`,
    `background:${filled ? color : 'rgba(8,12,18,0.78)'}`,
    `color:${filled ? '#080C12' : color}`,
    `border:2px solid ${color}`,
    'box-shadow:0 1px 4px rgba(0,0,0,0.45)',
  ].join(';');
  return node;
}

function flag() {
  const node = document.createElement('div');
  node.style.cssText = 'width:18px;height:28px;pointer-events:none;';
  node.innerHTML =
    '<div style="position:absolute;left:8px;top:0;width:2px;height:28px;background:#F3F6FA"></div>' +
    '<div style="position:absolute;left:10px;top:0;width:14px;height:9px;background:#E879F9"></div>';
  return node;
}

export function HoleMap({
  hole,
  shots,
  onTap,
}: {
  hole: HoleDrawing;
  shots: Shot[];
  onTap?: (point: MapPoint) => void;
}) {
  const [look, setLook] = useState<MapLook>('satellite');
  const [failed, setFailed] = useState<string | null>(null);
  const host = useRef<HTMLElement | null>(null);
  const mapRef = useRef<MlMap | null>(null);
  const markers = useRef<MlMarker[]>([]);
  const markerCtor = useRef<typeof MlMarker | null>(null);
  const onTapRef = useRef(onTap);
  const dataRef = useRef({ hole, shots, look });
  const skipLook = useRef(true);
  onTapRef.current = onTap;
  dataRef.current = { hole, shots, look };

  const marks = shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
  const yards = Math.round(yardsBetween(marks.length ? marks[marks.length - 1] : hole.tee, hole.greenCenter));
  const holeKey = `${hole.number}:${hole.tee.lat.toFixed(5)}:${hole.tee.lng.toFixed(5)}`;

  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let dead = false;
    let map: MlMap | null = null;
    ensureCss();

    void (async () => {
      try {
        const ml = await import('maplibre-gl');
        if (dead || !host.current) return;
        ml.setWorkerUrl('https://unpkg.com/maplibre-gl@6.17.0/dist/maplibre-gl-worker.mjs');
        markerCtor.current = ml.Marker;
        const region = regionFor(holePoints(dataRef.current.hole, dataRef.current.shots));
        map = new ml.Map({
          container: host.current,
          style: mapStyle(dataRef.current.look) as StyleSpecification | string,
          center: [region.longitude, region.latitude],
          zoom: 16,
          attributionControl: { compact: false },
        });
        map.on('click', (event) => {
          onTapRef.current?.({ lng: event.lngLat.lng, lat: event.lngLat.lat });
        });
        map.on('load', () => {
          if (!map || dead) return;
          mapRef.current = map;
          draw(map);
          fit(map);
          map.resize();
        });
      } catch (error) {
        if (!dead) setFailed(error instanceof Error ? error.message : 'The satellite map did not start.');
      }
    })();

    return () => {
      dead = true;
      markers.current.forEach((marker) => marker.remove());
      markers.current = [];
      map?.remove();
      mapRef.current = null;
    };
  }, [holeKey]);

  useEffect(() => {
    if (skipLook.current) {
      skipLook.current = false;
      return;
    }
    const map = mapRef.current;
    if (!map) return;
    map.setStyle(mapStyle(look) as StyleSpecification | string);
    map.once('style.load', () => {
      if (mapRef.current !== map) return;
      draw(map);
    });
  }, [look]);

  useEffect(() => {
    const map = mapRef.current;
    if (!map) return;
    let frames = 0;
    let raf = 0;
    const paint = () => {
      if (mapRef.current !== map) return;
      if (!map.isStyleLoaded()) {
        if (frames < 30) {
          frames += 1;
          raf = requestAnimationFrame(paint);
        }
        return;
      }
      draw(map);
    };
    paint();
    return () => cancelAnimationFrame(raf);
  }, [shots, holeKey]);

  function draw(map: MlMap) {
    const Ctor = markerCtor.current;
    if (!Ctor) return;
    markers.current.forEach((marker) => marker.remove());
    markers.current = [];
    const current = dataRef.current;
    const placed = current.shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
    const path = shotPath(current.hole.tee, placed);
    const line = {
      type: 'Feature' as const,
      properties: {},
      geometry: { type: 'LineString' as const, coordinates: path.map((point) => [point.lng, point.lat]) },
    };
    const source = map.getSource('shot-path') as GeoJSONSource | undefined;
    if (path.length > 1) {
      if (source) source.setData(line);
      else {
        map.addSource('shot-path', { type: 'geojson', data: line });
        map.addLayer({
          id: 'shot-path',
          type: 'line',
          source: 'shot-path',
          layout: { 'line-cap': 'round', 'line-join': 'round' },
          paint: { 'line-color': colors.cyan, 'line-width': 4 },
        });
      }
    } else if (map.getLayer('shot-path')) {
      map.removeLayer('shot-path');
      map.removeSource('shot-path');
    }

    const add = (lng: number, lat: number, node: HTMLElement, anchor: 'center' | 'bottom' = 'center') => {
      const marker = new Ctor({ element: node, anchor }).setLngLat([lng, lat]).addTo(map);
      markers.current.push(marker);
    };
    add(current.hole.tee.lng, current.hole.tee.lat, dot('', colors.cyan, true));
    add(current.hole.greenCenter.lng, current.hole.greenCenter.lat, flag(), 'bottom');
    for (const shot of placed) {
      add(shot.lng, shot.lat, dot(String(shot.n), colors.cyan, shot.source === 'tap'));
    }
  }

  function fit(map: MlMap) {
    const current = dataRef.current;
    const region = regionFor(holePoints(current.hole, current.shots));
    map.fitBounds(
      [
        [region.longitude - region.longitudeDelta / 2, region.latitude - region.latitudeDelta / 2],
        [region.longitude + region.longitudeDelta / 2, region.latitude + region.latitudeDelta / 2],
      ],
      { padding: 28, duration: 0 },
    );
  }

  return (
    <MapChrome label={`Hole ${hole.number} · ${yards} yd`} look={look} onLook={setLook}>
      <View
        ref={(node) => {
          host.current = node instanceof HTMLElement ? node : null;
        }}
        style={{ flex: 1 }}
      />
      {failed ? (
        <View className="absolute inset-0 items-center justify-center px-6">
          <AppText className="text-center text-sm text-slate">{failed}</AppText>
        </View>
      ) : null}
    </MapChrome>
  );
}
