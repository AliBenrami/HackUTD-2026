export type Units = 'yards' | 'meters';

export type NineSelection = 'front' | 'back' | 'full';

export type RoundStatus = 'active' | 'completed';

export type Player = {
  id: string;
  name: string;
  createdAt: string;
};

export type HoleInfo = {
  number: number;
  par: 3 | 4 | 5;
  yards: number;
  handicap: number;
};

export type TeeSet = {
  id: string;
  name: string;
  marker: string;
  rating: number | null;
  slope: number | null;
  holes: HoleInfo[];
};

export type Course = {
  id: string;
  name: string;
  location: string;
  summary: string;
  teeSets: TeeSet[];
};

export type Round = {
  id: string;
  playerId: string;
  courseId: string;
  courseName: string;
  teeSetId: string;
  teeSetName: string;
  nine: NineSelection;
  startedAt: string;
  completedAt: string | null;
  status: RoundStatus;
  currentHole: number;
  sample: boolean;
};

/**
 * Penalty strokes are stored for display only.
 * They are already included in `strokes` and must not be added again.
 * `fairwayHit` is null when the player skipped it or the hole is a par 3.
 * `putts` is null when the player did not enter putts.
 */
export type HoleScore = {
  id: string;
  roundId: string;
  holeNumber: number;
  par: number;
  yards: number;
  strokes: number | null;
  putts: number | null;
  penalties: number | null;
  fairwayHit: boolean | null;
  completed: boolean;
};

export type SwingSource = 'camera' | 'import' | 'demo';

export type SwingPhaseName =
  | 'address'
  | 'takeaway'
  | 'top'
  | 'downswing'
  | 'impact'
  | 'followThrough';

export type PoseLandmark = {
  name: string;
  x: number;
  y: number;
};

export type SwingAnalysisResult = {
  mode: 'demonstration' | 'measured';
  disclaimer: string;
  phases: { name: SwingPhaseName; label: string; atMs: number }[];
  landmarks: PoseLandmark[];
  notes: string[];
};

export type SwingSession = {
  id: string;
  videoId: string;
  createdAt: string;
  source: SwingSource;
  videoUri: string | null;
  storagePath: string | null;
  club: string;
  status: 'ready' | 'demo';
  analysis: SwingAnalysisResult | null;
};

export type HudPreferences = {
  showDistance: boolean;
  showElevation: boolean;
  showScore: boolean;
  showWind: boolean;
};

export type ARDevice = {
  id: string;
  name: string;
  model: string;
  connected: boolean;
  battery: number | null;
  firmware: string | null;
};

export type ARPreferences = {
  units: Units;
  hud: HudPreferences;
  syncScores: boolean;
  device: ARDevice;
  lastSyncAt: string | null;
};

export type ScoreSyncPayload = {
  version: 1;
  roundId: string;
  courseId: string;
  holeNumber: number;
  strokes: number;
  par: number;
  relativeToPar: number;
  roundRelativeToPar: number | null;
  updatedAt: string;
};
