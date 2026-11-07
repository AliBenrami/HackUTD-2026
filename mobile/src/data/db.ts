import type { SQLiteDatabase } from 'expo-sqlite';
import { seedDatabase } from './repository';

const DATABASE_VERSION = 1;

export async function migrate(db: SQLiteDatabase): Promise<void> {
  const version = await db.getFirstAsync<{ user_version: number }>('PRAGMA user_version');
  if ((version?.user_version ?? 0) >= DATABASE_VERSION) return;

  try {
    await db.execAsync('PRAGMA journal_mode = WAL;');
  } catch {
    // Some web builds keep the default journal. The tables still persist.
  }

  await db.execAsync(`
    CREATE TABLE IF NOT EXISTS player (
      id TEXT PRIMARY KEY NOT NULL,
      name TEXT NOT NULL,
      created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS rounds (
      id TEXT PRIMARY KEY NOT NULL,
      player_id TEXT NOT NULL,
      course_id TEXT NOT NULL,
      course_name TEXT NOT NULL,
      tee_set_id TEXT NOT NULL,
      tee_set_name TEXT NOT NULL,
      nine TEXT NOT NULL,
      started_at TEXT NOT NULL,
      completed_at TEXT,
      status TEXT NOT NULL,
      current_hole INTEGER NOT NULL,
      sample INTEGER NOT NULL DEFAULT 0
    );

    CREATE TABLE IF NOT EXISTS hole_scores (
      id TEXT PRIMARY KEY NOT NULL,
      round_id TEXT NOT NULL,
      hole_number INTEGER NOT NULL,
      par INTEGER NOT NULL,
      yards INTEGER NOT NULL,
      strokes INTEGER,
      putts INTEGER,
      penalties INTEGER,
      fairway_hit INTEGER,
      completed INTEGER NOT NULL DEFAULT 0,
      UNIQUE(round_id, hole_number)
    );

    CREATE TABLE IF NOT EXISTS swing_sessions (
      id TEXT PRIMARY KEY NOT NULL,
      created_at TEXT NOT NULL,
      source TEXT NOT NULL,
      video_uri TEXT,
      club TEXT NOT NULL,
      status TEXT NOT NULL,
      analysis_json TEXT
    );

    CREATE TABLE IF NOT EXISTS preferences (
      id INTEGER PRIMARY KEY NOT NULL,
      units TEXT NOT NULL,
      hud_json TEXT NOT NULL,
      sync_scores INTEGER NOT NULL,
      device_json TEXT NOT NULL,
      last_sync_at TEXT
    );

    CREATE TABLE IF NOT EXISTS recent_courses (
      course_id TEXT PRIMARY KEY NOT NULL,
      selected_at TEXT NOT NULL
    );
  `);

  await seedDatabase(db);
  await db.execAsync(`PRAGMA user_version = ${DATABASE_VERSION}`);
}
