import type { ARDevice, ARPreferences, ScoreSyncPayload } from '../../domain/types';

export type ScoreSyncResult = {
  accepted: boolean;
  syncedAt: string | null;
};

/**
 * Hardware link for the separate AR experience.
 * The mobile app never runs the arcade game. It only prepares score snapshots.
 */
export interface ARDeviceBridge {
  pushScore(payload: ScoreSyncPayload, preferences: ARPreferences): Promise<ScoreSyncResult>;
}

export class MockARDeviceBridge implements ARDeviceBridge {
  async pushScore(payload: ScoreSyncPayload, preferences: ARPreferences): Promise<ScoreSyncResult> {
    if (!preferences.syncScores || !preferences.device.connected) {
      return { accepted: false, syncedAt: null };
    }
    return { accepted: true, syncedAt: payload.updatedAt };
  }
}

export const arBridge: ARDeviceBridge = new MockARDeviceBridge();

export function simulatedDevice(connected: boolean): ARDevice {
  if (!connected) {
    return {
      id: 'visor-horizon',
      name: 'Horizon Visor',
      model: 'GA-1',
      connected: false,
      battery: null,
      firmware: null,
    };
  }
  return {
    id: 'visor-horizon',
    name: 'Horizon Visor',
    model: 'GA-1',
    connected: true,
    battery: 86,
    firmware: '0.9.4-sim',
  };
}

export const defaultPreferences: ARPreferences = {
  units: 'yards',
  hud: {
    showDistance: true,
    showElevation: true,
    showScore: true,
    showWind: false,
  },
  syncScores: false,
  device: simulatedDevice(false),
  lastSyncAt: null,
};
