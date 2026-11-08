using System;
using System.Collections.Generic;
using System.IO;
using Newtonsoft.Json.Linq;
using UnityEngine;

namespace GolfAR.Editor
{
    public static class CourseParity
    {
        private const double GeometryTolerance = .000015;
        private const double RoundedReportTolerance = .00051;

        public static void Verify()
        {
            string[] args = Environment.GetCommandLineArgs();
            int flag = Array.IndexOf(args, "-courseReference");
            if (flag < 0 || flag + 1 >= args.Length)
                throw new ArgumentException("Pass -courseReference followed by the exported reference JSON path.");

            var fixtures = JArray.Parse(File.ReadAllText(args[flag + 1]));
            foreach (JToken fixture in fixtures)
                VerifyFixture(fixture);
            Debug.Log($"[course-parity] {fixtures.Count} reference courses passed.");
        }

        private static void VerifyFixture(JToken fixture)
        {
            JToken inputs = fixture["inputs"];
            JToken expected = fixture["layout"];
            int seed = inputs.Value<int>("seed");
            string mode = inputs.Value<string>("difficulty");
            string label = $"{mode}/{seed}";
            if (inputs.Value<double>("width_m") != .60 || inputs.Value<double>("length_m") != .40)
                throw new ArgumentException($"{label}: fixture is outside the VR design reference.");
            var reserved = new List<Bounds>();
            if (inputs["reserved"] is JArray footprints)
            {
                foreach (JToken footprint in footprints)
                    reserved.Add(new Bounds(new Vector3((float)footprint[0], 0, (float)footprint[1]),
                        new Vector3(2 * (float)footprint[2], 0, 2 * (float)footprint[3])));
            }
            CourseLayout actual;
            try
            {
                actual = CourseLayout.Generate(seed, mode, expected.Value<double>("course_scale"),
                    expected.Value<double>("ball_diameter_m"), expected["terrain"].Value<int>("grid_size"),
                    reserved, expected.Value<double>("margin_m"), inputs.Value<int>("decoration_count"));
                actual.ValidateVrClearance(actual.course_scale * 8, .043f);
            }
            catch (Exception error)
            {
                throw new InvalidOperationException($"{label}: generation or VR validation failed.", error);
            }

            var serialized = JObject.Parse(actual.ToJson());
            Compare(expected, serialized, label);
            // Check both producers' v5 files through the same parser used by Load Layout.
            Compare(expected, JObject.Parse(CourseLayout.Parse(expected.ToString()).ToJson()), label + "/import");
            Compare(serialized, JObject.Parse(CourseLayout.Parse(actual.ToJson()).ToJson()), label + "/reload");
            Compare(serialized, JObject.Parse(CourseLayout.Generate(seed, mode, expected.Value<double>("course_scale"),
                expected.Value<double>("ball_diameter_m"), expected["terrain"].Value<int>("grid_size"),
                reserved, expected.Value<double>("margin_m"), inputs.Value<int>("decoration_count")).ToJson()), label + "/regen");

            var surface = new CourseSurface(actual);
            float slopeStep = .002f / actual.course_scale;
            float normalStep = Mathf.Min(actual.terrain.width_m, actual.terrain.length_m) / Mathf.Max(32, actual.terrain.grid_size - 1);
            foreach (JToken sample in fixture["samples"])
            {
                Vector2 p = new(sample.Value<float>("x"), sample.Value<float>("y"));
                Near(sample.Value<double>("height"), surface.Height(p), GeometryTolerance, label + "/height");
                Vector3 slopeNormal = surface.Normal(p, slopeStep);
                Near(sample.Value<double>("slope"), new Vector2(slopeNormal.x, slopeNormal.z).magnitude / slopeNormal.y,
                    .001, label + "/slope");
                JToken n = sample["normal"];
                Vector3 normal = surface.Normal(p, normalStep);
                if (Vector3.Distance(normal, new Vector3((float)n[0], (float)n[2], (float)n[1])) > .001f)
                    throw new InvalidOperationException($"{label}: normal differs at {p}.");
            }
        }

        private static void Compare(JToken expected, JToken actual, string path)
        {
            if (expected is JObject obj && actual is JObject got)
            {
                foreach (JProperty property in obj.Properties())
                    Compare(property.Value, got[property.Name], path + "/" + property.Name);
                return;
            }
            if (expected is JArray expectedArray && actual is JArray actualArray && expectedArray.Count == actualArray.Count)
            {
                for (int i = 0; i < expectedArray.Count; i++)
                    Compare(expectedArray[i], actualArray[i], path + "/" + i);
                return;
            }
            if (IsNumber(expected) && IsNumber(actual))
            {
                Near((double)expected, (double)actual, path.Contains("/validation/") ? RoundedReportTolerance : GeometryTolerance, path);
                return;
            }
            if (!JToken.DeepEquals(expected, actual))
                throw new InvalidOperationException($"{path}: expected {expected}, got {actual}.");
        }

        private static bool IsNumber(JToken value) => value?.Type is JTokenType.Integer or JTokenType.Float;

        private static void Near(double expected, double actual, double tolerance, string path)
        {
            if (!(Math.Abs(expected - actual) <= tolerance))
                throw new InvalidOperationException($"{path}: expected {expected:R}, got {actual:R}.");
        }
    }
}
