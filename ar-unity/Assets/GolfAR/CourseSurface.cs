using UnityEngine;

namespace GolfAR
{
    // The route corridor and warped height field follow the Python terrain.
    // Cache segment lengths so terrain sampling does no per-vertex allocation.
    public sealed class CourseSurface
    {
        private readonly CourseLayout layout;
        private readonly Vector2[] points;
        private readonly Vector2[] segments;
        private readonly float[] lengths, walked, invSquare;
        private readonly float ridgeCos, ridgeSin, ridgeOffset;
        private readonly Vector2 mesa;
        private readonly bool levelTee;
        public float Length { get; }

        public CourseSurface(CourseLayout layout, bool levelTee = false)
        {
            this.layout = layout;
            this.levelTee = levelTee;
            points = System.Array.ConvertAll(layout.route, CourseLayout.Ground);
            segments = new Vector2[points.Length - 1];
            lengths = new float[segments.Length];
            walked = new float[segments.Length];
            invSquare = new float[segments.Length];
            float length = 0;
            for (int i = 0; i < segments.Length; i++)
            {
                segments[i] = points[i + 1] - points[i];
                lengths[i] = segments[i].magnitude;
                invSquare[i] = 1f / Mathf.Max(1e-12f, segments[i].sqrMagnitude);
                walked[i] = length;
                length += lengths[i];
            }
            Length = length;
            float angle = (Hash(layout.seed + 733, 3, 9) + 1) * Mathf.PI;
            ridgeCos = Mathf.Cos(angle);
            ridgeSin = Mathf.Sin(angle);
            ridgeOffset = Hash(layout.seed + 811, 7, 2) * .24f;
            int corner = (int)(Hash(layout.seed + 907, 1, 4) * 4) & 3;
            mesa = new Vector2(corner is 0 or 3 ? .18f : .82f, corner is 0 or 1 ? .18f : .82f);
        }

        public (float Distance, float Progress, Vector2 Point) Project(Vector2 point)
        {
            float minSquare = float.PositiveInfinity;
            float progress = 0;
            Vector2 nearest = points[0];
            for (int i = 0; i < segments.Length; i++)
            {
                float t = Mathf.Clamp01(Vector2.Dot(point - points[i], segments[i]) * invSquare[i]);
                Vector2 projected = points[i] + segments[i] * t;
                float square = (point - projected).sqrMagnitude;
                if (square >= minSquare)
                    continue;
                minSquare = square;
                nearest = projected;
                progress = (walked[i] + t * lengths[i]) / Mathf.Max(Length, 1e-9f);
            }
            return (Mathf.Sqrt(minSquare), progress, nearest);
        }

        public static float DistanceToSegment(Vector2 point, Vector2 a, Vector2 b)
        {
            Vector2 segment = b - a;
            float t = Mathf.Clamp01(Vector2.Dot(point - a, segment) / Mathf.Max(1e-12f, segment.sqrMagnitude));
            return Vector2.Distance(point, a + segment * t);
        }

        public float Width(float progress)
        {
            float landing = 1 - Smooth(.025f, .095f, Mathf.Min(progress, 1 - progress));
            return layout.fairway_width_m * (1 + .16f * landing);
        }

        public float Height(Vector2 point)
        {
            var projection = Project(point);
            return Height(point, projection.Distance, projection.Progress);
        }

        internal Vector3 PlaceFeature(float[] position)
        {
            var point = CourseLayout.Ground(position);
            var projection = Project(point);
            float original = OriginalHeight(point, projection.Distance, projection.Progress);
            var placed = CourseLayout.WorldAxes(position);
            placed.y += TeeAdjustment(original, projection.Distance, projection.Progress);
            return placed;
        }

        public Vector3 Normal(Vector2 point, float step)
        {
            float dx = (Height(point + Vector2.right * step) - Height(point - Vector2.right * step)) / (2 * step);
            float dz = (Height(point + Vector2.up * step) - Height(point - Vector2.up * step)) / (2 * step);
            return new Vector3(-dx, 1, -dz).normalized;
        }

        public float Height(Vector2 point, float distance, float progress)
        {
            float height = OriginalHeight(point, distance, progress);
            return height + TeeAdjustment(height, distance, progress);
        }

        private float TeeAdjustment(float height, float distance, float progress)
        {
            if (!levelTee || progress >= .36f)
                return 0;
            float width = Width(progress);
            float blend = (1 - Smooth(.18f, .36f, progress)) *
                (1 - Smooth(width * .60f, width * .92f, distance));
            return (layout.terrain.base_height_m - height) * blend;
        }

        private float OriginalHeight(Vector2 point, float distance, float progress)
        {
            var terrain = layout.terrain;
            float width = Width(progress);
            float wave = Mathf.Sin(Mathf.PI * progress);
            float routeHeight = terrain.base_height_m + terrain.route_height_m * wave * wave;
            float blend = Smooth(width * .32f, width * .62f, distance);
            float endpoint = Mathf.Min(Vector2.Distance(point, points[0]), Vector2.Distance(point, points[^1]));
            if (endpoint < width * .42f)
            {
                blend *= Smooth(0, width * .42f, endpoint);
                routeHeight = terrain.base_height_m;
            }
            float outside = terrain.base_height_m + terrain.height_amplitude_m *
                Field(point.x / terrain.width_m + .5f, point.y / terrain.length_m + .5f);
            return Mathf.Lerp(routeHeight, outside, blend);
        }

        private float Field(float x, float y)
        {
            int seed = layout.seed;
            float qx = x + Noise(seed + 401, x * 1.35f + .7f, y * 1.35f - .4f) * .16f;
            float qy = y + Noise(seed + 509, x * 1.35f - 1.1f, y * 1.35f + .8f) * .16f;
            float macro = .64f * Noise(seed, qx * 1.15f, qy * 1.15f) +
                .25f * Noise(seed + 97, qx * 2.3f, qy * 2.3f) +
                .11f * Noise(seed + 194, qx * 4.6f, qy * 4.6f);
            float across = ((x - .5f) * ridgeCos + (y - .5f) * ridgeSin - ridgeOffset) / .075f;
            float along = (-(x - .5f) * ridgeSin + (y - .5f) * ridgeCos) / .44f;
            float ridge = Mathf.Exp(-across * across - along * along * along * along);
            float field = .70f * macro + .30f * ridge;
            float shelf = 1 - Smooth(-.008f, .035f, Mathf.Max(Mathf.Abs(x - mesa.x) - .18f, Mathf.Abs(y - mesa.y) - .14f));
            float basin = 1 - Smooth(-.008f, .040f,
                Mathf.Max(Mathf.Abs(x - (1 - mesa.x)) - .18f, Mathf.Abs(y - (1 - mesa.y)) - .13f));
            field = field * (1 - shelf * .88f) + shelf * .94f;
            return field * (1 - basin * .60f) + basin * .04f;
        }

        internal static float Noise(int seed, float x, float y)
        {
            int ix = Mathf.FloorToInt(x);
            int iy = Mathf.FloorToInt(y);
            float sx = Smooth(0, 1, x - ix);
            float sy = Smooth(0, 1, y - iy);
            return Mathf.Lerp(Mathf.Lerp(Hash(seed, ix, iy), Hash(seed, ix + 1, iy), sx),
                Mathf.Lerp(Hash(seed, ix, iy + 1), Hash(seed, ix + 1, iy + 1), sx), sy);
        }

        private static float Hash(int seed, int x, int y)
        {
            unchecked
            {
                uint n = (uint)(x * 374761393 + y * 668265263 + seed * 1442695041);
                n = (n ^ (n >> 13)) * 1274126177u;
                return ((n ^ (n >> 16)) & 0xffff) / 32767.5f - 1;
            }
        }

        private static float Smooth(float a, float b, float value)
        {
            float t = Mathf.Clamp01((value - a) / (b - a));
            return t * t * (3 - 2 * t);
        }
    }
}
