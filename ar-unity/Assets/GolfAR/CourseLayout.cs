using System;
using System.Collections.Generic;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace GolfAR
{
    // The v5 file format keeps Panda's XY ground plane and Z-up positions.
    // Only the renderer converts them to Unity's XZ ground plane.
    public sealed class CourseLayout
    {
        public const float DefaultScale = .25f;
        public const float DefaultBall = .022f;
        public const float Safety = .003f;
        public const int FixedSeed = 4242;
        public const int ReferenceGrid = 97;
        public static readonly Vector2 Table = new(.60f, .40f);

        public string scene = "cyber-golf";
        public int version = 5;
        public int seed;
        public string difficulty;
        public string archetype;
        public float course_scale;
        public float[] table_m;
        public double margin_m = .03;
        public int? decoration_count;
        public float ball_diameter_m;
        public HeightField terrain;
        public float fairway_width_m;
        public float[][] route;
        public float[][] direct_route;
        public float[][] reference_route;
        public float[][] preferred_route;
        public float[] start;
        public float[] hole;
        public List<Feature> obstacles = new();
        public List<Feature> hazards = new();
        public List<Feature> decor = new();
        public Feature[] objects;
        public object[] surfaces = Array.Empty<object>();
        public int segments;
        public int turns;
        public bool fallback;
        public object generation_attempts;
        public object validation;

        public sealed class HeightField
        {
            public float width_m, length_m, base_height_m, height_amplitude_m, route_height_m;
            public int grid_size;
        }

        public sealed class Feature
        {
            public string kind, asset;
            public float[] position, rotation;
            public float footprint_m, radius_m;
            public object[] target;
        }

        private readonly struct Preset
        {
            public readonly int Turns, Blocks, Pools;
            public readonly double Bend, Width, Hills, Rise;
            public readonly float Slope;
            public readonly string FirstStyle, SecondStyle;

            public Preset(int turns, int blocks, int pools, double bend, double width,
                double hills, double rise, float slope, string firstStyle, string secondStyle)
            {
                Turns = turns; Blocks = blocks; Pools = pools;
                Bend = bend; Width = width; Hills = hills; Rise = rise; Slope = slope;
                FirstStyle = firstStyle; SecondStyle = secondStyle;
            }
        }

        private static Preset Settings(string difficulty) => difficulty switch
        {
            "easy" => new(2, 0, 1, .035, .120, .022, .006, .60f, "neon-straight", "gentle-arc"),
            "medium" => new(3, 2, 2, .075, .090, .040, .014, .85f, "s-curve", "raised-district"),
            "hard" => new(4, 4, 3, .105, .065, .055, .025, 1.15f, "plasma-gauntlet", "ridge-run"),
            _ => throw new ArgumentException("Choose easy, medium or hard.")
        };

        public static readonly string[] CityAssets =
        {
            "cyber_tower_block", "cyber_noodle_shop", "cyber_vending_kiosk", "cyber_holo_billboard",
            "cyber_server_rack", "cyber_arcade_cabinet", "cyber_power_generator",
            "cyber_neon_sign_vertical", "cyber_delivery_drone", "cyber_hover_car"
        };

        public static CourseLayout Generate(int seed, string difficulty, double scale, double ball, int grid,
            IReadOnlyList<Bounds> reserved, double margin = .03, int decorationCount = 4)
        {
            var mode = Settings(difficulty);
            double width = Math.Min(.60 * .90, .60 - 2 * margin);
            double length = Math.Min(.40 * .85, .40 - 2 * margin);
            if (!(scale >= .10 && scale <= 1 && ball >= .020 - 1e-8 && ball <= .043 + 1e-8) ||
                grid is < 17 or > 129 || grid % 2 == 0 ||
                !(margin >= 0 && width > .20 && length > .12) || decorationCount is < 0 or > 120)
                throw new ArgumentException("Invalid course generation settings.");
            var random = new PythonCourseRandom(seed);
            var layout = new CourseLayout
            {
                seed = seed, difficulty = difficulty, turns = mode.Turns, course_scale = (float)scale,
                table_m = new[] { Table.x, Table.y }, ball_diameter_m = (float)ball,
                margin_m = margin, decoration_count = decorationCount,
                fairway_width_m = (float)(mode.Width / scale),
                terrain = new HeightField
                {
                    width_m = (float)(width / scale), length_m = (float)(length / scale),
                    base_height_m = (float)(.010 / scale), height_amplitude_m = (float)(mode.Hills / scale),
                    route_height_m = (float)(mode.Rise / scale), grid_size = grid
                }
            };

            // Draw both endpoints before the bends, and round in design metres before scaling.
            double start = random.Range(-length * .18, length * .18);
            double end = random.Range(-length * .18, length * .18);
            var points = new List<(double X, double Z)>();
            for (int i = 0; i < mode.Turns + 2; i++)
            {
                double x = -width * .38 + width * .76 * ((double)i / (mode.Turns + 1));
                double z = i == 0 ? start : i == mode.Turns + 1 ? end :
                    (i % 2 == 0 ? 1 : -1) * random.Range(mode.Bend * .45, mode.Bend) + random.Range(-.012, .012);
                points.Add((x, Math.Clamp(z, -length * .36, length * .36)));
            }
            for (int pass = 0; pass < 3; pass++)
            {
                var smooth = new List<(double X, double Z)> { points[0] };
                for (int i = 1; i < points.Count; i++)
                {
                    var a = points[i - 1];
                    var b = points[i];
                    smooth.Add((a.X * .75 + b.X * .25, a.Z * .75 + b.Z * .25));
                    smooth.Add((a.X * .25 + b.X * .75, a.Z * .25 + b.Z * .75));
                }
                smooth.Add(points[^1]);
                points = smooth;
            }
            var designRoute = points.Select(p => (X: Math.Round(p.X, 6), Z: Math.Round(p.Z, 6))).ToArray();
            var localRoute = designRoute.Select(p => (X: Math.Round(p.X / scale, 6), Z: Math.Round(p.Z / scale, 6))).ToArray();
            layout.route = localRoute.Select(p => new[] { (float)p.X, (float)p.Z }).ToArray();
            layout.start = layout.route[0];
            layout.hole = layout.route[^1];
            layout.segments = designRoute.Length - 1;
            layout.direct_route = new[] { layout.start, layout.hole };
            layout.reference_route = layout.direct_route;
            layout.preferred_route = layout.route;
            var surface = new CourseSurface(layout);

            bool Reserved(double x, double z, double radius)
            {
                foreach (Bounds bounds in reserved)
                    if (Math.Abs(bounds.center.x - x) < bounds.extents.x + radius &&
                        Math.Abs(bounds.center.z - z) < bounds.extents.z + radius)
                        return true;
                return false;
            }
            float Height(double x, double z) => surface.Height(new Vector2((float)x, (float)z));

            var tee = designRoute[0];
            double dx = designRoute[^1].X - tee.X;
            double dz = designRoute[^1].Z - tee.Z;
            double directLength = Math.Sqrt(dx * dx + dz * dz);
            double diameter = difficulty == "medium" ? .036 : .042;
            double expanded = diameter / 2 + ball / 2 + .003;
            double offset = expanded * (difficulty == "medium" ? .82 : .35);
            var placed = new List<(double X, double Z)>();
            for (int i = 0; i < mode.Blocks; i++)
            {
                (double Clearance, double X, double Z) best = default;
                for (int step = 0; step < 9; step++)
                {
                    double fraction = .18 + step * .08;
                    for (int side = -1; side <= 1; side += 2)
                    {
                        double x = tee.X + dx * fraction - dz / directLength * offset * side;
                        double z = tee.Z + dz * fraction + dx / directLength * offset * side;
                        double distance = Nearest(localRoute, x / scale, z / scale).Distance * scale;
                        if (distance < expanded + .002 ||
                            placed.Any(p => Distance(p.X - x, p.Z - z) < diameter * .82))
                            continue;
                        var candidate = (distance, x, z);
                        if (candidate.CompareTo(best) > 0)
                            best = candidate;
                    }
                }
                if (best.Clearance == 0)
                    break;
                if (Reserved(best.X, best.Z, diameter / 2))
                    continue;

                double localX = best.X / scale;
                double localZ = best.Z / scale;
                double roundX = Math.Round(localX, 6);
                double roundZ = Math.Round(localZ, 6);
                placed.Add((roundX * scale, roundZ * scale));
                layout.obstacles.Add(new Feature
                {
                    kind = i % 2 == 0 ? "crystal" : "barrier",
                    position = new[] { (float)roundX, (float)roundZ, (float)Math.Round(Height(localX, localZ), 6) },
                    footprint_m = (float)(diameter / scale), target = new object[] { "xy", diameter / scale }
                });
            }

            for (int i = 0; i < mode.Pools; i++)
            {
                var point = designRoute[(int)Math.Round((i + 1.0) / (mode.Pools + 1) * (designRoute.Length - 1))];
                double radius = random.Range(.030, .045);
                double shift = (mode.Width * .62 + radius * (difficulty == "hard" ? .65 : 1.05)) *
                    (((i + seed) & 1) == 0 ? 1 : -1);
                double edge = length / 2 - radius;
                double sideEdge = width / 2 - radius;
                double x = Math.Clamp(point.X, -sideEdge, sideEdge);
                double z = Math.Clamp(point.Z + shift, -edge, edge);
                if (Reserved(x, z, radius))
                    z = Math.Clamp(point.Z - shift, -edge, edge);
                if (!Reserved(x, z, radius))
                    layout.hazards.Add(new Feature
                    {
                        kind = "plasma", position = new[] { (float)(x / scale), (float)(z / scale),
                            (float)(Height(x / scale, z / scale) + .002 / scale) },
                        radius_m = (float)(radius / scale), footprint_m = (float)(2 * radius / scale)
                    });
            }

            for (int i = 0; i < decorationCount; i++)
            {
                for (int attempt = 0; attempt < 40; attempt++)
                {
                    double x = random.Range(-width * .44, width * .44);
                    double z = random.Range(-length * .42, length * .42);
                    var nearest = Nearest(localRoute, x / scale, z / scale);
                    double size = random.Range(.018, .034);
                    if (nearest.Distance * scale < mode.Width * .85 + size / 2 || Reserved(x, z, size / 2))
                        continue;
                    double yaw = Math.Round(Math.Atan2(nearest.X - x / scale, nearest.Z - z / scale) * (180 / Math.PI) / 15) * 15;
                    layout.decor.Add(new Feature
                    {
                        asset = CityAssets[random.Index(CityAssets.Length)],
                        position = new[] { (float)(x / scale), (float)(z / scale), Height(x / scale, z / scale) },
                        rotation = new[] { (float)yaw, 0f, 0f }, target = new object[] { "max", size },
                        footprint_m = (float)(size / scale)
                    });
                    break;
                }
            }
            layout.archetype = random.Index(2) == 0 ? mode.FirstStyle : mode.SecondStyle;
            layout.generation_attempts = new Dictionary<string, int> { ["route"] = 1, ["terrain"] = 1 };
            layout.Validate();
            return layout;
        }

        // Keep double precision for placement decisions at equal clearances. The
        // renderer uses the cached float projection in CourseSurface.
        private static (double Distance, double X, double Z) Nearest((double X, double Z)[] route, double x, double z)
        {
            (double Distance, double X, double Z) nearest = (double.PositiveInfinity, 0, 0);
            for (int i = 1; i < route.Length; i++)
            {
                var a = route[i - 1];
                double dx = route[i].X - a.X;
                double dz = route[i].Z - a.Z;
                double t = Math.Clamp(((x - a.X) * dx + (z - a.Z) * dz) / Math.Max(1e-12, dx * dx + dz * dz), 0, 1);
                double px = a.X + dx * t;
                double pz = a.Z + dz * t;
                double distance = Distance(x - px, z - pz);
                if (distance < nearest.Distance)
                    nearest = (distance, px, pz);
            }
            return nearest;
        }

        private static double Distance(double dx, double dz) => Math.Sqrt(dx * dx + dz * dz);

        public void Validate()
        {
            var mode = Settings(difficulty);
            if (scene != "cyber-golf" || version != 5 || !Between(course_scale, .1f, 1f) ||
                !Between(ball_diameter_m, .020f, .043f) || !Between(fairway_width_m, .01f, 2f) ||
                table_m == null || table_m.Length != 2 || !Between(table_m[0], Table.x - .0001f, Table.x + .0001f) ||
                !Between(table_m[1], Table.y - .0001f, Table.y + .0001f) ||
                terrain == null || !Between(terrain.width_m * course_scale, .20f, Table.x + .0001f) ||
                !Between(terrain.length_m * course_scale, .12f, Table.y + .0001f) ||
                !Between(terrain.base_height_m, 0, 1) || !Between(terrain.height_amplitude_m, 0, 1) ||
                !Between(terrain.route_height_m, 0, 1) || terrain.grid_size is < 17 or > 129 ||
                terrain.grid_size % 2 == 0 || route == null || route.Length is < 8 or > 256 ||
                route.Any(point => point == null || point.Length != 2 || !Inside(Ground(point), 0)) ||
                !route[0].SequenceEqual(start ?? Array.Empty<float>()) ||
                !route[^1].SequenceEqual(hole ?? Array.Empty<float>()))
                throw new ArgumentException("Invalid v5 layout or incompatible tabletop dimensions.");
            float radius = ball_diameter_m / 2;
            if (fairway_width_m * course_scale / 2 - radius - Safety <= radius * .65f)
                throw new ArgumentException("Fairway lacks clearance for this ball diameter.");
            if (obstacles == null || hazards == null || decor == null ||
                obstacles.Count + hazards.Count + decor.Count > 128)
                throw new ArgumentException("Invalid layout feature lists.");
            objects = obstacles.Concat(hazards).Concat(decor).ToArray();
            foreach (Feature feature in objects)
                if (feature?.position == null || feature.position.Length != 3 ||
                    !Between(feature.position[2], -1, 2) || !Between(feature.footprint_m, .001f, 2) ||
                    !Inside(Ground(feature.position), feature.footprint_m / 2))
                    throw new ArgumentException("A course feature lies outside the terrain.");
            if (hazards.Any(pool => !Between(pool.radius_m, .001f, pool.footprint_m / 2 + .00001f)) ||
                decor.Any(prop => prop.rotation != null &&
                    (prop.rotation.Length != 3 || !Between(prop.rotation[0], -360, 360))))
                throw new ArgumentException("Invalid feature size or rotation.");

            var surface = new CourseSurface(this);
            if (surface.Length < .1f / course_scale)
                throw new ArgumentException("The route has insufficient length.");
            var interference = new List<string>();
            foreach (Feature obstacle in obstacles)
            {
                Vector2 point = Ground(obstacle.position);
                float clearance = obstacle.footprint_m / 2 + (radius + Safety) / course_scale;
                if (surface.Project(point).Distance < clearance - .00001f)
                    throw new ArgumentException("An obstacle blocks the preferred route.");
                float distance = CourseSurface.DistanceToSegment(point, Ground(start), Ground(hole));
                interference.Add(distance <= clearance * .65f ? "directly obstructing" :
                    distance < clearance ? "partially obstructing" : "peripheral");
            }
            if (difficulty == "easy" && obstacles.Count != 0 ||
                difficulty == "medium" && !interference.Contains("partially obstructing") ||
                difficulty == "hard" && !interference.Contains("directly obstructing"))
                throw new ArgumentException("The shortcut does not meet the difficulty requirements.");

            float maxSlope = 0;
            float step = .002f / course_scale;
            for (int i = 0; i < route.Length; i += Mathf.Max(1, route.Length / 20))
            {
                Vector2 p = Ground(route[i]);
                float dx = surface.Height(p + Vector2.right * step) - surface.Height(p - Vector2.right * step);
                float dz = surface.Height(p + Vector2.up * step) - surface.Height(p - Vector2.up * step);
                maxSlope = Mathf.Max(maxSlope, new Vector2(dx, dz).magnitude / (2 * step));
            }
            if (!Between(maxSlope, 0, mode.Slope))
                throw new ArgumentException("Route slope exceeds the difficulty limit.");
            validation = new Dictionary<string, object>
            {
                ["route_length_m"] = surface.Length * course_scale,
                ["direct_length_m"] = Vector2.Distance(Ground(start), Ground(hole)) * course_scale,
                ["max_route_slope"] = maxSlope, ["interference"] = interference,
                ["terrain_m"] = new[] { terrain.width_m * course_scale, terrain.length_m * course_scale },
                ["grid"] = terrain.grid_size, ["ball_diameter_m"] = ball_diameter_m,
                ["course_scale"] = course_scale, ["fairway_width_m"] = fairway_width_m * course_scale
            };
        }

        public void ValidateVrClearance(float worldScale, float ballDiameter)
        {
            float radius = ballDiameter / (2 * worldScale);
            float safety = Safety / course_scale;
            if (fairway_width_m / 2 - radius - safety <= radius * .65f)
                throw new ArgumentException("The VR ball needs more fairway clearance.");
            var surface = new CourseSurface(this);
            foreach (Feature obstacle in obstacles)
                if (surface.Project(Ground(obstacle.position)).Distance < obstacle.footprint_m / 2 + radius + safety)
                    throw new ArgumentException("An obstacle blocks the VR ball's route.");
        }

        public string ToJson() => JsonConvert.SerializeObject(this, Formatting.Indented,
            new JsonSerializerSettings { NullValueHandling = NullValueHandling.Ignore });

        public static CourseLayout Parse(string json)
        {
            var layout = JsonConvert.DeserializeObject<CourseLayout>(json) ??
                throw new ArgumentException("The course file is empty.");
            layout.Validate();
            return layout;
        }

        private bool Inside(Vector2 point, float padding) =>
            Between(Mathf.Abs(point.x) + padding, 0, terrain.width_m / 2 + .001f) &&
            Between(Mathf.Abs(point.y) + padding, 0, terrain.length_m / 2 + .001f);

        private static bool Between(float value, float min, float max) => value >= min && value <= max;
        public static Vector2 Ground(float[] point) => new(point[0], point[1]);
        public static Vector3 WorldAxes(float[] point) => new(point[0], point[2], point[1]);
    }
}
