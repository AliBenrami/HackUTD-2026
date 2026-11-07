import { describe, expect, it } from 'vitest';
import { buildTopo } from './topo';

describe('buildTopo', () => {
  it('builds stable contour paths for a course seed', () => {
    const first = buildTopo('cedar-ridge-7');
    const second = buildTopo('cedar-ridge-7');
    expect(first.viewBox).toBe('0 0 100 66');
    expect(first.contours.length).toBeGreaterThan(4);
    expect(first.contours.every((contour) => contour.d.startsWith('M'))).toBe(true);
    expect(first.fairway.startsWith('M')).toBe(true);
    expect(first.green.cx).toBeGreaterThan(first.tee.cx);
    expect(first.contours.map((contour) => contour.d)).toEqual(second.contours.map((contour) => contour.d));
    expect(buildTopo('neon-dunes-3').fairway).not.toBe(first.fairway);
  });
});
