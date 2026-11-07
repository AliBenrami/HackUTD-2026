import type { Course, HoleInfo, TeeSet } from '../domain/types';

type Yardage = [number, number, number, number];

type HoleSpec = {
  number: number;
  par: 3 | 4 | 5;
  handicap: number;
  yards: Yardage;
};

const TEE_META = [
  { name: 'Black', marker: '#D7DEE8' },
  { name: 'Blue', marker: '#3B82F6' },
  { name: 'White', marker: '#F3F6FA' },
  { name: 'Red', marker: '#F07167' },
] as const;

function buildCourse(
  meta: { id: string; name: string; location: string; summary: string },
  ratings: Array<{ rating: number; slope: number }>,
  specs: HoleSpec[],
): Course {
  const teeSets: TeeSet[] = TEE_META.map((tee, index) => ({
    id: `${meta.id}-${tee.name.toLowerCase()}`,
    name: tee.name,
    marker: tee.marker,
    rating: ratings[index].rating,
    slope: ratings[index].slope,
    holes: specs.map(
      (spec): HoleInfo => ({
        number: spec.number,
        par: spec.par,
        handicap: spec.handicap,
        yards: spec.yards[index],
      }),
    ),
  }));

  return { ...meta, teeSets };
}

function holes(
  rows: Array<[number, 3 | 4 | 5, number, number, number, number, number]>,
): HoleSpec[] {
  return rows.map(([number, par, handicap, black, blue, white, red]) => ({
    number,
    par,
    handicap,
    yards: [black, blue, white, red],
  }));
}

export const courses: Course[] = [
  buildCourse(
    {
      id: 'cedar-ridge',
      name: 'Cedar Ridge',
      location: 'Dallas, Texas',
      summary: 'Parkland routing with a long par-5 eighth and a guarded back-nine green.',
    },
    [
      { rating: 74.2, slope: 141 },
      { rating: 72.1, slope: 136 },
      { rating: 69.8, slope: 128 },
      { rating: 67.2, slope: 118 },
    ],
    holes([
      [1, 4, 9, 418, 395, 368, 321],
      [2, 5, 3, 558, 531, 498, 452],
      [3, 3, 15, 198, 176, 154, 128],
      [4, 4, 5, 431, 408, 377, 334],
      [5, 4, 1, 455, 429, 396, 348],
      [6, 3, 17, 224, 201, 172, 141],
      [7, 4, 11, 412, 387, 356, 310],
      [8, 5, 7, 572, 544, 509, 461],
      [9, 4, 13, 404, 381, 352, 308],
      [10, 4, 8, 421, 397, 366, 324],
      [11, 4, 12, 388, 364, 339, 297],
      [12, 3, 16, 189, 168, 147, 119],
      [13, 5, 2, 561, 534, 501, 455],
      [14, 4, 4, 448, 422, 390, 342],
      [15, 4, 10, 406, 382, 354, 312],
      [16, 3, 18, 212, 186, 161, 132],
      [17, 5, 6, 549, 522, 488, 440],
      [18, 4, 14, 432, 405, 374, 329],
    ]),
  ),
  buildCourse(
    {
      id: 'neon-dunes',
      name: 'Neon Dunes',
      location: 'Scottsdale, Arizona',
      summary: 'Desert corridors, wide landing areas, and two short par 3s into the wind.',
    },
    [
      { rating: 73.4, slope: 138 },
      { rating: 71.2, slope: 132 },
      { rating: 68.6, slope: 124 },
      { rating: 66.1, slope: 116 },
    ],
    holes([
      [1, 4, 5, 402, 381, 354, 312],
      [2, 4, 11, 376, 352, 328, 290],
      [3, 5, 1, 548, 521, 486, 441],
      [4, 3, 17, 168, 151, 134, 112],
      [5, 4, 7, 421, 398, 367, 325],
      [6, 4, 13, 389, 366, 340, 301],
      [7, 3, 15, 205, 184, 159, 128],
      [8, 5, 3, 536, 509, 474, 428],
      [9, 4, 9, 414, 391, 362, 318],
      [10, 4, 8, 398, 374, 348, 306],
      [11, 3, 18, 156, 139, 122, 98],
      [12, 4, 6, 433, 408, 379, 334],
      [13, 5, 2, 559, 532, 497, 450],
      [14, 4, 4, 446, 419, 388, 341],
      [15, 4, 12, 371, 348, 322, 284],
      [16, 3, 16, 192, 171, 148, 121],
      [17, 5, 10, 512, 486, 452, 408],
      [18, 4, 14, 407, 383, 356, 314],
    ]),
  ),
  buildCourse(
    {
      id: 'harbor-lights',
      name: 'Harbor Lights',
      location: 'Galveston, Texas',
      summary: 'A shorter coastal course with firm fairways and small, exposed greens.',
    },
    [
      { rating: 72.6, slope: 134 },
      { rating: 70.4, slope: 128 },
      { rating: 68.1, slope: 121 },
      { rating: 65.4, slope: 114 },
    ],
    holes([
      [1, 4, 7, 388, 364, 338, 298],
      [2, 5, 3, 521, 494, 461, 418],
      [3, 3, 15, 174, 156, 138, 114],
      [4, 4, 1, 428, 402, 372, 328],
      [5, 4, 11, 366, 342, 318, 281],
      [6, 3, 17, 188, 167, 146, 118],
      [7, 4, 9, 395, 371, 344, 304],
      [8, 5, 5, 534, 507, 472, 426],
      [9, 4, 13, 381, 357, 331, 292],
      [10, 4, 8, 372, 349, 324, 286],
      [11, 4, 12, 358, 334, 309, 272],
      [12, 3, 18, 149, 132, 116, 96],
      [13, 5, 2, 546, 518, 483, 438],
      [14, 4, 4, 419, 394, 365, 322],
      [15, 4, 10, 384, 360, 334, 295],
      [16, 3, 16, 201, 179, 155, 126],
      [17, 5, 6, 528, 501, 466, 421],
      [18, 4, 14, 399, 375, 348, 307],
    ]),
  ),
];

export function getCourse(courseId: string): Course | undefined {
  return courses.find((course) => course.id === courseId);
}

export function getTee(course: Course, teeSetId: string): TeeSet | undefined {
  return course.teeSets.find((tee) => tee.id === teeSetId);
}

export function searchCourses(query: string): Course[] {
  const needle = query.trim().toLowerCase();
  if (!needle) return courses;
  return courses.filter((course) => {
    const haystack = `${course.name} ${course.location}`.toLowerCase();
    return haystack.includes(needle);
  });
}

export function defaultTee(course: Course): TeeSet {
  return course.teeSets.find((tee) => tee.name === 'Blue') ?? course.teeSets[0];
}
