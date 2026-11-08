import { useState } from 'react';
import { Text, View } from 'react-native';
import MapView, { Marker, Polyline } from 'react-native-maps';
import { holePoints, type HoleDrawing } from '../data/courseMaps';
import { regionFor, shotPath, yardsBetween, type MapPoint, type Shot } from '../domain/geo';
import type { MapLook } from '../domain/satelliteStyle';
import { colors } from '../theme/colors';
import { MapChrome } from './MapChrome';

export type { HoleDrawing };

function coordinate(point: MapPoint) {
  return { latitude: point.lat, longitude: point.lng };
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
  const marks = shots.filter((shot) => Number.isFinite(shot.lng) && Number.isFinite(shot.lat));
  const region = regionFor(holePoints(hole, marks));
  const path = shotPath(hole.tee, marks);
  const yards = Math.round(yardsBetween(marks.length ? marks[marks.length - 1] : hole.tee, hole.greenCenter));
  const holeKey = `${hole.number}:${hole.tee.lat.toFixed(5)}:${hole.tee.lng.toFixed(5)}`;

  return (
    <MapChrome label={`Hole ${hole.number} · ${yards} yd`} look={look} onLook={setLook}>
      <MapView
        key={holeKey}
        style={{ flex: 1 }}
        mapType={look === 'satellite' ? 'satellite' : 'terrain'}
        initialRegion={region}
        rotateEnabled
        pitchEnabled
        toolbarEnabled={false}
        showsUserLocation
        loadingBackgroundColor={colors.ink}
        loadingIndicatorColor={colors.cyan}
        onPress={(event) => {
          if (!onTap) return;
          const { latitude, longitude } = event.nativeEvent.coordinate;
          if (!Number.isFinite(latitude) || !Number.isFinite(longitude)) return;
          onTap({ lat: latitude, lng: longitude });
        }}
      >
        <Marker coordinate={coordinate(hole.tee)} anchor={{ x: 0.5, y: 0.5 }} tracksViewChanges={false} title="Tee">
          <View style={{ width: 14, height: 14, borderRadius: 7, backgroundColor: colors.cyan, borderWidth: 2, borderColor: '#fff' }} />
        </Marker>
        <Marker coordinate={coordinate(hole.greenCenter)} anchor={{ x: 0.2, y: 1 }} tracksViewChanges={false} title="Pin">
          <View style={{ alignItems: 'center' }}>
            <View style={{ width: 16, height: 10, backgroundColor: colors.magenta, marginLeft: 8 }} />
            <View style={{ width: 2, height: 18, backgroundColor: colors.mist }} />
          </View>
        </Marker>
        {path.length > 1 ? (
          <Polyline coordinates={path.map(coordinate)} strokeColor={colors.cyan} strokeWidth={3} />
        ) : null}
        {marks.map((shot) => {
          const filled = shot.source === 'tap';
          return (
            <Marker
              key={shot.n}
              coordinate={coordinate(shot)}
              anchor={{ x: 0.5, y: 0.5 }}
              tracksViewChanges={false}
              title={`Shot ${shot.n}`}
            >
              <View
                style={{
                  width: 22,
                  height: 22,
                  borderRadius: 11,
                  alignItems: 'center',
                  justifyContent: 'center',
                  backgroundColor: filled ? colors.cyan : 'rgba(8,12,18,0.78)',
                  borderWidth: 2,
                  borderColor: colors.cyan,
                }}
              >
                <Text style={{ color: filled ? colors.ink : colors.cyan, fontSize: 11, fontWeight: '700' }}>{shot.n}</Text>
              </View>
            </Marker>
          );
        })}
      </MapView>
    </MapChrome>
  );
}
