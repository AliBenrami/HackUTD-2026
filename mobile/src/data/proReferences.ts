import type { ProPhase, ProReference } from '../domain/swingCompare';

/**
 * Included elbow angles, matching the pose review: 180° is straight.
 * Bands sit inside published tour ranges. Lead elbow is about 145° at the top
 * and about 161° at impact. Trail-elbow flexion is about 55–85° at the top
 * (included angle about 95–125°) and about 15–25° at impact (included angle
 * about 155–165°). Each player shifts the typical value inside those ranges.
 * These are reference models, not motion capture of a named swing.
 */

export const REFERENCE_SOURCE_NOTE =
  'Reference model built from published tour ranges for elbow bend, shifted slightly for how this swing is commonly described. It is not a motion capture of this player.';

function phase(name: string, lead: [number, number, number], trail: [number, number, number]): ProPhase {
  return {
    name,
    angles: {
      leadElbow: { typical: lead[0], low: lead[1], high: lead[2] },
      trailElbow: { typical: trail[0], low: trail[1], high: trail[2] },
    },
  };
}

const tigerPhases: ProPhase[] = [
  phase('Address', [168, 160, 176], [170, 160, 178]),
  phase('Toe-up', [165, 155, 175], [142, 125, 155]),
  phase('Mid-backswing', [155, 145, 165], [112, 95, 130]),
  phase('Top', [144, 135, 155], [108, 95, 125]),
  phase('Mid-downswing', [160, 150, 172], [120, 105, 140]),
  phase('Impact', [161, 152, 172], [158, 150, 170]),
  phase('Mid-follow-through', [159, 148, 172], [145, 125, 165]),
  phase('Finish', [100, 55, 140], [120, 90, 155]),
];

const roryPhases: ProPhase[] = [
  phase('Address', [170, 162, 178], [168, 158, 178]),
  phase('Toe-up', [166, 156, 176], [136, 120, 152]),
  phase('Mid-backswing', [158, 148, 168], [104, 90, 125]),
  phase('Top', [150, 140, 160], [100, 90, 120]),
  phase('Mid-downswing', [163, 152, 174], [114, 100, 135]),
  phase('Impact', [164, 154, 174], [164, 154, 174]),
  phase('Mid-follow-through', [160, 148, 172], [140, 120, 160]),
  phase('Finish', [96, 55, 140], [118, 90, 155]),
];

const nellyPhases: ProPhase[] = [
  phase('Address', [169, 160, 178], [170, 160, 178]),
  phase('Toe-up', [166, 156, 176], [148, 130, 162]),
  phase('Mid-backswing', [160, 150, 170], [118, 100, 135]),
  phase('Top', [152, 142, 162], [114, 100, 128]),
  phase('Mid-downswing', [164, 154, 174], [128, 112, 145]),
  phase('Impact', [166, 156, 176], [162, 152, 172]),
  phase('Mid-follow-through', [162, 150, 174], [150, 130, 168]),
  phase('Finish', [98, 55, 140], [122, 90, 155]),
];

export const proReferences: ProReference[] = [
  {
    id: 'tiger-woods',
    name: 'Tiger Woods',
    kind: 'reference-model',
    summary: 'Trail arm stays connected on the way down.',
    sourceNote: REFERENCE_SOURCE_NOTE,
    emphasis: ['trailElbow'],
    phases: tigerPhases,
    explanations: {
      trailElbow: {
        userMoreBent:
          'This reference keeps a moderate bend so the elbow stays tucked toward the ribs, which can help the club shallow on the way down. The angle is elbow bend, a stand-in for how close the arm sits to the body.',
        userStraighter:
          'This reference bends the trail elbow more so the elbow stays tucked closer to the ribcage. That tuck can help the club stay shallow, and the angle only stands in for the gap to the body.',
      },
    },
  },
  {
    id: 'rory-mcilroy',
    name: 'Rory McIlroy',
    kind: 'reference-model',
    summary: 'Lead arm holds a wide arc.',
    sourceNote: REFERENCE_SOURCE_NOTE,
    emphasis: ['leadElbow'],
    phases: roryPhases,
    explanations: {
      leadElbow: {
        userMoreBent:
          'This reference keeps the lead arm extended enough to hold a wide arc. Extra bend shortens that arc and can drop the hands.',
        userStraighter:
          'This reference leaves a little bend in the lead arm so the arc stays wide without locking the elbow. A side camera can make the arm look straighter than it is.',
      },
    },
  },
  {
    id: 'nelly-korda',
    name: 'Nelly Korda',
    kind: 'reference-model',
    summary: 'Lead arm stays long. She plays left-handed, so lead is compared with lead.',
    sourceNote: REFERENCE_SOURCE_NOTE,
    emphasis: ['leadElbow'],
    phases: nellyPhases,
    explanations: {
      leadElbow: {
        userMoreBent:
          'This reference keeps the lead arm long, which is the wide arc in this model. Extra bend shortens that arc.',
        userStraighter:
          'This reference leaves a little bend in the lead arm rather than locking it straight. The arm stays long either way.',
      },
    },
  },
];

export function proReference(id: string) {
  return proReferences.find((reference) => reference.id === id) ?? proReferences[0];
}
