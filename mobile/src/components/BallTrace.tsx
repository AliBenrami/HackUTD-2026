import { Circle, Polyline } from 'react-native-svg';
import type { BallSample } from '../data/swingReview';

const INK = '#F4F7FB';
const SHADE = '#081018';

export function BallTrace({ samples, frame }: { samples: readonly BallSample[]; frame: number }) {
  const visible = samples.filter((sample) => sample.frame <= frame);
  if (visible.length === 0) return null;
  const points = visible.map((sample) => `${sample.x},${sample.y}`).join(' ');
  const last = visible[visible.length - 1];
  return (
    <>
      {visible.length > 1 ? (
        <>
          <Polyline points={points} stroke={SHADE} strokeWidth={12} fill="none" strokeLinecap="round" strokeLinejoin="round" />
          <Polyline points={points} stroke={INK} strokeWidth={6} fill="none" strokeLinecap="round" strokeLinejoin="round" />
        </>
      ) : null}
      {visible.map((sample) => (
        <Circle key={sample.frame} cx={sample.x} cy={sample.y} r={sample.frame === last.frame ? 8 : 4} fill={INK} />
      ))}
    </>
  );
}
