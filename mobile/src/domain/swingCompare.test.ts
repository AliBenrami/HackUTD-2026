import { describe, expect, it } from 'vitest';
import { proReference, proReferences } from '../data/proReferences';
import { SCORE_CUTOFF, swingReview } from '../data/swingReview';
import { LlmSwingNarrator, compareAndNarrate } from '../services/swing/narrator';
import {
  COMPARE_PHASES,
  PHASE_SCORE_CUTOFF,
  SWING_COMPARE_DISCLAIMER,
  buildLlmInsightRequest,
  compareSwing,
} from './swingCompare';

const tiger = proReference('tiger-woods');
const rory = proReference('rory-mcilroy');

describe('swing comparison', () => {
  it('uses the same phase-score bar as the swing screen', () => {
    expect(PHASE_SCORE_CUTOFF).toBe(SCORE_CUTOFF);
  });

  it('gives every reference the mapped phases', () => {
    for (const reference of proReferences) {
      expect(reference.kind).toBe('reference-model');
      expect(reference.phases.map((phase) => phase.name)).toEqual([...COMPARE_PHASES]);
    }
  });

  it('treats the left arm as the lead arm', () => {
    const impact = compareSwing(swingReview[0], tiger).phases.find((phase) => phase.phase === 'Impact');
    expect(impact?.metrics.find((metric) => metric.key === 'leadElbow')?.user).toBe(178.9);
    expect(impact?.metrics.find((metric) => metric.key === 'trailElbow')?.user).toBe(146.8);
  });

  it('drops a collapsed trail-arm reading', () => {
    const mid = compareSwing(swingReview[0], tiger).phases.find((phase) => phase.phase === 'Mid-backswing');
    expect(mid?.metrics.find((metric) => metric.key === 'trailElbow')?.status).toBe('unusable');
  });

  it('describes Tiger’s tucked trail arm when the reference is more bent', () => {
    const { insights } = compareAndNarrate(
      {
        id: 99,
        events: [
          {
            name: 'Mid-downswing',
            score: 0.9,
            tentative: false,
            angles: { leftElbow: 160, rightElbow: 155 },
          },
        ],
      },
      tiger,
    );
    const trail = insights.find((insight) => insight.metric === 'trailElbow');
    expect(trail?.observation).toContain('straighter');
    expect(trail?.observation).toContain('155.0');
    expect(trail?.why.toLowerCase()).toContain('tuck');
    expect(trail?.confidence).toBe('limited');
    expect(trail?.disclaimer).toBe(SWING_COMPARE_DISCLAIMER);
  });

  it('keeps the sample top-of-swing trail gap uncertain', () => {
    const { insights } = compareAndNarrate(swingReview[0], tiger);
    const trail = insights.find((insight) => insight.phase === 'Top' && insight.metric === 'trailElbow');
    expect(trail?.observation).toContain('58.8');
    expect(trail?.observation).toContain('more bent');
    expect(trail?.observation).toContain('pose estimate');
    expect(trail?.why.toLowerCase()).toContain('tuck');
    expect(trail?.confidence).toBe('low');
    expect(trail?.caveat).toBe('tentative');
  });

  it('ranks the emphasized arm first when both gaps are readable', () => {
    const swing = {
      id: 3,
      events: [
        {
          name: 'Top',
          score: 0.95,
          tentative: false,
          angles: { leftElbow: 120, rightElbow: 70 },
        },
      ],
    };
    expect(compareAndNarrate(swing, tiger).insights[0]?.metric).toBe('trailElbow');
    expect(compareAndNarrate(swing, rory).insights[0]?.metric).toBe('leadElbow');
    expect(compareAndNarrate(swingReview[0], rory).insights[0]?.observation).toContain('Rory');
  });

  it('builds an LLM request from the angles and leaves the video out', () => {
    const packet = compareSwing(swingReview[0], tiger);
    const request = buildLlmInsightRequest(packet, tiger);
    const encoded = JSON.stringify(request);
    expect(encoded).not.toContain('joints');
    expect(encoded).not.toContain('.mp4');
    expect(encoded).not.toContain('clubHead');
    expect(request.disclaimer).toBe(SWING_COMPARE_DISCLAIMER);
    expect(request.task).toContain('no guaranteed certainty');
    expect(request.rows.some((row) => row.phase === 'Top' && row.metric === 'trailElbow')).toBe(true);
    expect(request.rows.some((row) => row.phase === 'Mid-backswing' && row.metric === 'trailElbow')).toBe(false);
    expect(request.rows[0]?.whyHint.length).toBeGreaterThan(0);
  });

  it('does not call a model from the unconnected narrator', () => {
    const packet = compareSwing(swingReview[0], tiger);
    expect(() => new LlmSwingNarrator().narrate(packet, tiger)).toThrow(/not connected/);
  });
});
