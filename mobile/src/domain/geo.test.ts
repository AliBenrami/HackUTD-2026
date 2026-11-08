import { describe, expect, it } from 'vitest';
import { frameHole, fromPlane, guessLanding, placeShot, toPlane, yardsBetween } from './geo';

const tee = { lng: -96.75, lat: 32.99 };
const green = { lng: -96.75, lat: 32.9936 };

describe('hole geometry', () => {
  it('measures a northbound hole in yards', () => {
    expect(yardsBetween(tee, green)).toBeGreaterThan(400);
    expect(yardsBetween(tee, green)).toBeLessThan(460);
  });

  it('puts the green straight ahead and a point to the right on the positive side', () => {
    const ahead = toPlane(tee, green, green);
    expect(ahead.y).toBeGreaterThan(400);
    expect(Math.abs(ahead.x)).toBeLessThan(1);
    const right = toPlane(tee, green, { lng: -96.7485, lat: 32.9918 });
    expect(right.x).toBeGreaterThan(50);
  });

  it('gives a wide frame more room across the hole', () => {
    const side = { lng: -96.7492, lat: 32.9918 };
    const narrow = frameHole(tee, green, [tee, green, side], 2 / 3);
    const wide = frameHole(tee, green, [tee, green, side], 1.4);
    const gap = (frame: ReturnType<typeof frameHole>) =>
      Math.abs(frame.toView(side).x - frame.toView(tee).x) / frame.width;
    expect(gap(wide)).toBeGreaterThan(gap(narrow));
  });

  it('round-trips a point through the map frame', () => {
    const frame = frameHole(tee, green, [tee, green, { lng: -96.749, lat: 32.992 }]);
    const view = frame.toView(green);
    const back = frame.fromView(view.x, view.y);
    expect(yardsBetween(back, green)).toBeLessThan(1);
    expect(yardsBetween(fromPlane(tee, green, toPlane(tee, green, green)), green)).toBeLessThan(1);
  });

  it('uses the phone when it is on the hole and a centerline guess when it is not', () => {
    const path = [tee, green];
    const phone = guessLanding({
      path,
      green,
      shots: [],
      phone: { lng: -96.75, lat: 32.991 },
      carryYards: 230,
    });
    expect(phone.source).toBe('phone');
    expect(phone.point.lat).toBeCloseTo(32.991);

    const generic = guessLanding({
      path,
      green,
      shots: [],
      phone: { lng: -97.2, lat: 32.5 },
      carryYards: 200,
    });
    expect(generic.source).toBe('generic');
    expect(yardsBetween(tee, generic.point)).toBeGreaterThan(150);
    expect(yardsBetween(tee, generic.point)).toBeLessThan(230);
  });

  it('replaces a guess when the player taps the map', () => {
    const shots = placeShot([], { lng: -96.75, lat: 32.991 }, 'generic');
    const tapped = placeShot(shots, { lng: -96.751, lat: 32.992 }, 'tap');
    expect(tapped).toHaveLength(1);
    expect(tapped[0].source).toBe('tap');
    expect(tapped[0].n).toBe(1);
  });
});
