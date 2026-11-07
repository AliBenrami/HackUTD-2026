import type { PoseLandmark, SwingAnalysisResult, SwingSource } from '../../domain/types';

export type SwingInput = {
  videoUri: string | null;
  source: SwingSource;
};

/**
 * The scorekeeping app talks to swing analysis only through this interface.
 * A future MediaPipe Pose Landmarker and phase classifier can replace the demo.
 */
export interface SwingAnalyzer {
  readonly id: string;
  readonly label: string;
  analyze(input: SwingInput): Promise<SwingAnalysisResult>;
}

export const DEMO_LANDMARKS: PoseLandmark[] = [
  { name: 'head', x: 48, y: 16 },
  { name: 'neck', x: 46, y: 24 },
  { name: 'shoulder', x: 43, y: 32 },
  { name: 'hip', x: 40, y: 52 },
  { name: 'knee', x: 45, y: 70 },
  { name: 'ankle', x: 43, y: 88 },
  { name: 'trailAnkle', x: 30, y: 88 },
  { name: 'leadElbow', x: 56, y: 22 },
  { name: 'leadWrist', x: 66, y: 14 },
  { name: 'trailElbow', x: 34, y: 38 },
  { name: 'trailWrist', x: 58, y: 18 },
  { name: 'club', x: 78, y: 8 },
];

export const DEMO_BONES: ReadonlyArray<readonly [string, string]> = [
  ['head', 'neck'],
  ['neck', 'shoulder'],
  ['shoulder', 'hip'],
  ['hip', 'knee'],
  ['knee', 'ankle'],
  ['hip', 'trailAnkle'],
  ['shoulder', 'leadElbow'],
  ['leadElbow', 'leadWrist'],
  ['shoulder', 'trailElbow'],
  ['trailElbow', 'trailWrist'],
  ['leadWrist', 'club'],
];

export const DEMO_ANALYSIS: SwingAnalysisResult = {
  mode: 'demonstration',
  disclaimer:
    'Demonstration preview. These phases and the pose are sample layout data, not a measurement of a swing.',
  phases: [
    { name: 'address', label: 'Address', atMs: 0 },
    { name: 'takeaway', label: 'Takeaway', atMs: 280 },
    { name: 'top', label: 'Top', atMs: 760 },
    { name: 'downswing', label: 'Downswing', atMs: 980 },
    { name: 'impact', label: 'Impact', atMs: 1140 },
    { name: 'followThrough', label: 'Follow-through', atMs: 1460 },
  ],
  landmarks: DEMO_LANDMARKS,
  notes: [
    'Body landmarks will be detected from video in a later model.',
    'Scorekeeping does not depend on this screen.',
  ],
};

export class DemoSwingAnalyzer implements SwingAnalyzer {
  readonly id = 'demo';
  readonly label = 'Demonstration analyzer';

  async analyze(input: SwingInput): Promise<SwingAnalysisResult> {
    const attached = input.videoUri
      ? 'Your video is saved on this phone. The pose below was not detected from that clip.'
      : 'No video is attached. This entry only shows the analysis layout.';
    return {
      ...DEMO_ANALYSIS,
      landmarks: DEMO_ANALYSIS.landmarks.map((landmark) => ({ ...landmark })),
      phases: DEMO_ANALYSIS.phases.map((phase) => ({ ...phase })),
      notes: [attached, ...DEMO_ANALYSIS.notes],
      disclaimer:
        'Demonstration preview. GolfAR is not scoring this swing. A pose model can be connected here later.',
    };
  }
}

/**
 * Reserved for MediaPipe Pose Landmarker plus a temporal phase classifier.
 * This build does not ship model weights or run inference.
 * Measured poses should use the phase names and elbow angles in
 * src/domain/swingCompare.ts so pro comparison can run on the same shape.
 */
export class MediaPipeSwingAnalyzer implements SwingAnalyzer {
  readonly id = 'mediapipe-pose';
  readonly label = 'MediaPipe Pose Landmarker';

  async analyze(): Promise<SwingAnalysisResult> {
    throw new Error('MediaPipe inference is not bundled in this build.');
  }
}

export const swingAnalyzer: SwingAnalyzer = new DemoSwingAnalyzer();
