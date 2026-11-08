import type { MapPoint } from '../domain/geo';
import type { Course, TeeSet } from '../domain/types';
import raw from './courseMaps.json';

export type HoleDrawing = {
  number: number;
  tee: MapPoint;
  green: MapPoint[];
  greenCenter: MapPoint;
  fairway: MapPoint[] | null;
  bunkers: MapPoint[][];
  centerline: MapPoint[];
};

type StoredTee = { lng: number; lat: number; yards: number };

type StoredHole = {
  number: number;
  tees: Record<string, StoredTee>;
  green: MapPoint[];
  greenCenter: MapPoint;
  fairway: MapPoint[] | null;
  bunkers: MapPoint[][];
  centerline: MapPoint[];
};

type StoredCourse = {
  id: string;
  name: string;
  location: string;
  summary: string;
  center: MapPoint;
  teeSets: TeeSet[];
  holes: StoredHole[];
};

const stored = (raw.courses ?? []) as StoredCourse[];

export const mappedCourses: Course[] = stored.map((course) => ({
  id: course.id,
  name: course.name,
  location: course.location,
  summary: course.summary,
  teeSets: course.teeSets,
}));

export function courseCenter(courseId: string): MapPoint | null {
  return stored.find((course) => course.id === courseId)?.center ?? null;
}

export function holeDrawing(courseId: string, holeNumber: number, teeName: string): HoleDrawing | null {
  const course = stored.find((item) => item.id === courseId);
  const hole = course?.holes.find((item) => item.number === holeNumber);
  if (!hole) return null;
  const tee = hole.tees[teeName] ?? Object.values(hole.tees)[0];
  if (!tee) return null;
  return {
    number: hole.number,
    tee: { lng: tee.lng, lat: tee.lat },
    green: hole.green,
    greenCenter: hole.greenCenter,
    fairway: hole.fairway,
    bunkers: hole.bunkers,
    centerline: hole.centerline,
  };
}
