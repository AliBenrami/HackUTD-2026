import type { BallSample } from './swingReview';

// Detector trace for the range clip, keyed like swingReview.
// Swing 1 never leaves the tee, so it has no flight.
// Swing 2 runs from the 14.30 s impact cue and stops at 14.90 s, when the ball is lost.
export const ballTraces: readonly (readonly BallSample[])[] = [
  [],
  [
    { frame: 429, timeS: 14.3, x: 733.0, y: 1670.1, confidence: 0.867 },
    { frame: 430, timeS: 14.3333, x: 671.5, y: 1433.5, confidence: 0.807 },
    { frame: 431, timeS: 14.3667, x: 627.2, y: 1272.7, confidence: 0.828 },
    { frame: 432, timeS: 14.4, x: 601.2, y: 1173.3, confidence: 0.848 },
    { frame: 433, timeS: 14.4333, x: 583.3, y: 1106.6, confidence: 0.658 },
    { frame: 439, timeS: 14.6333, x: 539.2, y: 941.4, confidence: 0.224 },
    { frame: 440, timeS: 14.6667, x: 535.1, y: 929.7, confidence: 0.1 },
    { frame: 441, timeS: 14.7, x: 532.5, y: 918.7, confidence: 0.273 },
    { frame: 442, timeS: 14.7333, x: 529.9, y: 910.0, confidence: 0.081 },
    { frame: 443, timeS: 14.7667, x: 526.9, y: 902.8, confidence: 0.058 },
    { frame: 445, timeS: 14.8333, x: 524.5, y: 891.7, confidence: 0.17 },
    { frame: 447, timeS: 14.9, x: 521.7, y: 883.5, confidence: 0.123 },
  ],
];
