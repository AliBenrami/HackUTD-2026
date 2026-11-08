import { describe, expect, it } from 'vitest';
import { courseHandicap, fallbackCard, STARTER_BAG, targetYards, validateCard, windPhrase } from './caddie';

describe('caddie card', () => {
  it('moves the target eight yards for a front or back pin', () => {
    expect(targetYards(160, 'front')).toBe(152);
    expect(targetYards(160, 'back')).toBe(168);
  });

  it('picks the nearest club and says the model was not used', () => {
    const card = fallbackCard({
      bag: STARTER_BAG,
      holeYards: 160,
      pin: 'middle',
      wind: { speedMph: 8, gustMph: 12, fromDeg: 0 },
      windOn: true,
      holeBearingDeg: 0,
      commonMiss: 'right',
    });
    expect(card.source).toBe('fallback');
    expect(card.club).toBe('5-iron');
    expect(card.adjustedYards).toBe(183);
    expect(card.windNote).toContain('into you');
    expect(card.missTo).toBe('right');
    expect(card.confidence).toBe('limited');
  });

  it('accepts a card whose carry matches the bag and rejects a club that is not in it', () => {
    const accepted = validateCard(
      {
        club: '7-iron',
        carryYards: 155,
        adjustedYards: 160,
        aim: 'center',
        missTo: 'left',
        windNote: 'Light air.',
        reasons: ['The 7-iron matches the yardage.'],
        assumptions: ['Carries are the bag you entered.'],
        confidence: 'limited',
      },
      STARTER_BAG,
    );
    expect(accepted?.source).toBe('gemini');
    expect(validateCard({ ...accepted, club: '2-iron', carryYards: 155 }, STARTER_BAG)).toBeNull();
  });

  it('describes a crosswind from the right when playing north in an east wind', () => {
    expect(windPhrase({ speedMph: 8.2, gustMph: null, fromDeg: 90 }, 0).phrase).toBe('8 mph from the right');
    expect(windPhrase({ speedMph: 8, gustMph: null, fromDeg: 180 }, 0).yardAdjust).toBe(-8);
  });

  it('rounds a course handicap from the tee rating already on the course', () => {
    expect(courseHandicap(10, 130, 71.2, 72)).toBe(11);
    expect(courseHandicap(-1, 130, 71, 72)).toBeNull();
  });
});