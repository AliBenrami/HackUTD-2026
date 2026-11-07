import { describe, expect, it } from 'vitest';
import { SCORE_CUTOFF, swingReview } from './swingReview';
import { swingTrack } from './swingTrack';

describe('recorded swing review', () => {
  it('places both impact cues on the stable frames', () => {
    const impacts = swingReview.map((swing) => swing.events.find((event) => event.name === 'Impact'));
    expect(impacts.map((event) => event?.frame)).toEqual([114, 429]);
    expect(impacts.map((event) => event?.timeS)).toEqual([3.8, 14.3]);
    expect(impacts.map((event) => event?.label)).toEqual(['Impact cue', 'Impact cue']);
  });

  it('keeps top and finish tentative and marks low scores', () => {
    for (const swing of swingReview) {
      for (const event of swing.events) {
        expect(event.tentative).toBe(event.name === 'Top' || event.name === 'Finish');
        expect(event.score < SCORE_CUTOFF).toBe(event.score < 0.6);
      }
    }
    expect(swingReview[0].events.find((event) => event.name === 'Address')?.score).toBeLessThan(SCORE_CUTOFF);
    expect(swingReview[0].events.find((event) => event.name === 'Top')?.score).toBeLessThan(SCORE_CUTOFF);
  });

  it('leaves dropped detections empty instead of zero', () => {
    const midBackswing = swingReview[0].events.find((event) => event.frame === 82);
    expect(midBackswing?.clubs.clubHead).toBeNull();
    expect(midBackswing?.clubs.hands).toBeNull();
    expect(midBackswing?.clubs.shaft).not.toBeNull();

    const finish = swingReview[1].events.find((event) => event.name === 'Finish');
    expect(finish?.angles.rightElbow).toBeNull();
    expect(finish?.clubs.clubHead).toBeNull();
    expect(finish?.angles.leftElbow).toBe(63.8);
  });

  it('keeps a pose for every frame of the clip', () => {
    expect(swingTrack).toHaveLength(639);
    expect(swingTrack[114].c).not.toBeNull();
    expect(swingTrack[82].c).toBeNull();
    expect(swingTrack[82].h).toBeNull();
    expect(swingTrack[82].s).not.toBeNull();
  });
});
