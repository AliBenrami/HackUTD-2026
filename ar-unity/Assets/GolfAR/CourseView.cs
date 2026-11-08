using System.Collections.Generic;
using UnityEngine;

namespace GolfAR
{
    public sealed class CourseView : MonoBehaviour
    {
        private static readonly Color Base = new Color32(49, 72, 90, 255);
        private static readonly Color Steel = new Color32(76, 107, 125, 255);
        private static readonly Color Ridge = new Color32(32, 50, 61, 255);
        private static readonly Color Sidewall = new Color32(42, 64, 80, 255);
        private static readonly Color Fairway = new Color32(15, 126, 138, 255);
        internal static readonly Color Amber = new Color32(255, 194, 71, 255);
        internal static readonly Color Cyan = new Color32(0, 232, 240, 255);
        internal static readonly Color Magenta = new Color32(250, 60, 173, 255);
        internal static readonly Color Lime = new Color32(176, 255, 74, 255);
        private readonly List<Mesh> meshes = new();
        private readonly Dictionary<Color, Material> colors = new();
        private readonly Dictionary<Color, Material> litColors = new();
        private readonly Dictionary<Material, Material> propMaterials = new();
        private readonly List<GameObject> featureNeon = new();
        private static string[] galleryAssets;
        private Material terrainMaterial;
        private Transform neon, debug, ball, gallery;
        private GameObject terrainObject;
        private Vector3[] terrainVertices;
        private CourseLayout layout;
        private CourseSurface surface;
        private float scale;
        public List<Transform> Movable { get; } = new();
        public Transform Ball => ball;
        public Mesh TerrainMesh => terrainObject.GetComponent<MeshFilter>().sharedMesh;
        public MeshCollider TerrainCollider { get; private set; }
        public static string[] GalleryAssets => galleryAssets ??= ReadGalleryAssets();
        internal Vector3 Tee => At(CourseLayout.Ground(layout.start), 0);
        internal Vector3 Cup => At(CourseLayout.Ground(layout.hole), 0);

        internal Vector3 PuttHeading(Vector3 ball)
        {
            Vector3 fromTee = Vector3.ProjectOnPlane(ball - transform.TransformPoint(Tee), transform.up);
            if (fromTee.sqrMagnitude < .10f * .10f)
            {
                Vector2 tangent = CourseLayout.Ground(layout.route[1]) - CourseLayout.Ground(layout.start);
                return transform.TransformDirection(new Vector3(tangent.x, 0, tangent.y)).normalized;
            }
            Vector3 towardCup = Vector3.ProjectOnPlane(transform.TransformPoint(Cup) - ball, transform.up);
            return towardCup.sqrMagnitude < .0001f ? transform.right : towardCup.normalized;
        }

        public void Build(CourseLayout data, Shader vertexShader, Shader flatShader)
        {
            layout = data;
            surface = new CourseSurface(layout, levelTee: true);
            FlatShader = flatShader;
            terrainMaterial = new Material(vertexShader);
            neon = Group("Neon trim", transform);
            debug = Group("Route diagnostic", transform);
            scale = layout.course_scale;
            BuildTerrain();
            BuildRoute();
            for (int i = 0; i < layout.hazards.Count; i++)
            {
                var hazard = layout.hazards[i];
                var center = CourseLayout.Ground(hazard.position);
                var root = Group("Plasma pool", transform);
                root.localPosition = surface.PlaceFeature(hazard.position);
                var tint = i % 2 == 0 ? Cyan : Magenta;
                var glow = FeatureNeon(root);
                Radial("Dark plasma rim", root, center, hazard.radius_m * 1.16f, 0, Lit(Ridge),
                    .0014f, layout.seed + i, root.localPosition);
                Radial("Irregular plasma surface", glow, center, hazard.radius_m, 0, Paint(tint),
                    .0022f, layout.seed + i, origin: root.localPosition);
                Radial("Plasma halo", glow, center, hazard.radius_m * 1.12f, hazard.radius_m * 1.02f,
                    Paint(tint), .0028f, origin: root.localPosition);
                var collider = root.gameObject.AddComponent<BoxCollider>();
                collider.center = Vector3.up * .003f / scale;
                collider.size = new Vector3(hazard.radius_m * 2, .015f / scale, hazard.radius_m * 2);
                collider.isTrigger = true;
                Movable.Add(root);
            }
            foreach (var obstacle in layout.obstacles)
            {
                float width = obstacle.footprint_m;
                bool crystal = obstacle.kind == "crystal";
                var root = Group(obstacle.kind ?? "Barrier", transform);
                root.localPosition = surface.PlaceFeature(obstacle.position);
                root.localRotation = Quaternion.Euler(0, crystal ? 45 : 0, 0);
                BuildBarrier(root, width, crystal);
                Movable.Add(root);
            }
            foreach (var prop in layout.decor)
            {
                var root = City(transform, prop.asset, prop.footprint_m);
                root.localPosition = surface.PlaceFeature(prop.position);
                root.localRotation = Quaternion.Euler(0, prop.rotation?[0] ?? 0, 0);
                Movable.Add(root);
            }
            var hole = CourseLayout.Ground(layout.hole);
            float radius = layout.ball_diameter_m * .72f / scale;
            Radial("Target cup", transform, hole, radius * .48f, 0, Lit(Ridge), .001f);
            Radial("Outer target ring", neon, hole, radius, radius * .78f, Paint(Lime), .002f);
            Radial("Inner target ring", neon, hole, radius * .67f, radius * .52f, Paint(Cyan), .003f);
            var beacon = Block(neon, "Target beacon", At(hole, radius * .9f),
                new Vector3(radius * .06f, radius * 1.8f, radius * .06f), Lime);
            beacon.GetComponent<Collider>().enabled = false;
            ball = Group("Golf ball", transform);
            var sphere = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            sphere.transform.SetParent(ball, false);
            sphere.GetComponent<Renderer>().sharedMaterial = Lit(new Color32(245, 251, 255, 255));
            var mark = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            mark.name = "Ball alignment dot";
            mark.transform.SetParent(FeatureNeon(ball), false);
            mark.transform.localPosition = Vector3.up * .498f;
            mark.transform.localScale = new Vector3(.25f, .013f, .25f);
            mark.GetComponent<Renderer>().sharedMaterial = Paint(Cyan);
            mark.GetComponent<Collider>().enabled = false;
            Movable.Add(ball);
            SetScale(scale);
            ball.localPosition = Tee + Vector3.up * (layout.ball_diameter_m / (2 * scale));
        }

        public void SetScale(float value, float? diameter = null)
        {
            scale = value;
            transform.localScale = Vector3.one * scale;
            ball.localScale = Vector3.one * ((diameter ?? layout.ball_diameter_m) / scale);
        }

        public void SetPassthrough(bool enabled)
        {
            terrainMaterial.SetFloat("_Coverage", enabled ? .35f : 1f);
        }

        public void ShowDebug(bool enabled) => debug.gameObject.SetActive(enabled);
        public void ShowNeon(bool enabled)
        {
            neon.gameObject.SetActive(enabled);
            foreach (GameObject feature in featureNeon)
                feature.SetActive(enabled);
        }

        private Transform FeatureNeon(Transform parent)
        {
            var group = Group("Neon accents", parent);
            featureNeon.Add(group.gameObject);
            return group;
        }

        public void ShowGallery(bool enabled, int index)
        {
            if (gallery)
            {
                gallery.gameObject.SetActive(false);
                Destroy(gallery.gameObject);
            }
            foreach (Transform child in transform)
                if (child != gallery)
                    child.gameObject.SetActive(!enabled);
            if (!enabled)
                return;
            gallery = City(transform, GalleryAssets[index], .20f / scale);
            gallery.localRotation = Quaternion.Euler(0, 25, 0);
        }

        private void BuildTerrain()
        {
            var terrain = layout.terrain;
            int n = terrain.grid_size;
            var vertices = terrainVertices = new Vector3[n * n];
            var tints = new Color[n * n];
            var normals = new Vector3[n * n];
            var indices = new int[(n - 1) * (n - 1) * 6];
            for (int z = 0; z < n; z++)
                for (int x = 0; x < n; x++)
                {
                    Vector2 p = new((x / (n - 1f) - .5f) * terrain.width_m, (z / (n - 1f) - .5f) * terrain.length_m);
                    vertices[z * n + x] = new Vector3(p.x, surface.Height(p), p.y);
                }

            for (int z = 0; z < n; z++)
                for (int x = 0; x < n; x++)
                {
                    int i = z * n + x;
                    Vector3 left = vertices[z * n + Mathf.Max(0, x - 1)];
                    Vector3 right = vertices[z * n + Mathf.Min(n - 1, x + 1)];
                    Vector3 back = vertices[Mathf.Max(0, z - 1) * n + x];
                    Vector3 front = vertices[Mathf.Min(n - 1, z + 1) * n + x];
                    float dx = (right.y - left.y) / (right.x - left.x);
                    float dz = (front.y - back.y) / (front.z - back.z);
                    normals[i] = new Vector3(-dx, 1, -dz).normalized;
                    float slope = Mathf.Clamp01(new Vector2(dx, dz).magnitude / .85f);
                    float variation = CourseSurface.Noise(layout.seed + 1201, x * 3.1f / (n - 1), z * 3.1f / (n - 1)) * .5f + .5f;
                    float elevation = (vertices[i].y - terrain.base_height_m) / Mathf.Max(terrain.height_amplitude_m, 1e-6f);
                    float light = 1 + .20f * Mathf.Clamp01(elevation) - .22f * Mathf.Clamp01(-elevation);
                    tints[i] = Color.Lerp(Color.Lerp(Base.linear, Steel.linear, .16f + .20f * variation) * light,
                        Ridge.linear, slope * .42f);
                    if (z < n - 1 && x < n - 1)
                    {
                        int j = (z * (n - 1) + x) * 6;
                        // Panda's diagonal becomes a-d with reversed winding in Unity's XZ plane.
                        indices[j] = i; indices[j + 1] = i + n + 1; indices[j + 2] = i + 1;
                        indices[j + 3] = i; indices[j + 4] = i + n; indices[j + 5] = i + n + 1;
                    }
                }

            terrainObject = MeshObject("Terrain", transform, vertices, indices, terrainMaterial, tints, normals);
            TerrainCollider = terrainObject.AddComponent<MeshCollider>();
            TerrainCollider.sharedMesh = TerrainMesh;
            TerrainCollider.contactOffset = .001f;
            BuildIslandWalls(vertices, n);
        }

        private void BuildIslandWalls(Vector3[] vertices, int n)
        {
            var edge = new List<Vector3>(4 * (n - 1));
            for (int i = 0; i < n - 1; i++)
                edge.Add(vertices[i]);
            for (int i = 0; i < n - 1; i++)
                edge.Add(vertices[i * n + n - 1]);
            for (int i = 0; i < n - 1; i++)
                edge.Add(vertices[n * n - 1 - i]);
            for (int i = 0; i < n - 1; i++)
                edge.Add(vertices[(n - 1 - i) * n]);
            var sides = new Vector3[edge.Count * 3];
            var colors = new Color[sides.Length];
            var indices = new int[edge.Count * 12];
            var trim = new Vector3[edge.Count + 1];
            for (int i = 0; i < edge.Count; i++)
            {
                int next = (i + 1) % edge.Count;
                int a = 3 * i;
                int b = 3 * next;
                Vector3 tangent = edge[next] - edge[(i + edge.Count - 1) % edge.Count];
                tangent.y = 0;
                Vector3 outward = Vector3.Cross(Vector3.up, tangent).normalized;
                Vector3 bevel = edge[i] + (outward * .002f - Vector3.up * .0015f) / scale;
                sides[a] = edge[i];
                sides[a + 1] = bevel;
                sides[a + 2] = new Vector3(edge[i].x, -.025f / scale, edge[i].z) - outward * (.010f / scale);
                colors[a] = Steel.linear;
                colors[a + 1] = Sidewall.linear;
                colors[a + 2] = Ridge.linear;
                trim[i] = bevel + outward * (.00035f / scale) + Vector3.up * (.00035f / scale);
                int j = i * 12;
                indices[j] = a; indices[j + 1] = b; indices[j + 2] = a + 1;
                indices[j + 3] = b; indices[j + 4] = b + 1; indices[j + 5] = a + 1;
                indices[j + 6] = a + 1; indices[j + 7] = b + 1; indices[j + 8] = a + 2;
                indices[j + 9] = b + 1; indices[j + 10] = b + 2; indices[j + 11] = a + 2;
            }
            trim[^1] = trim[0];
            MeshObject("Beveled island walls", transform, sides, indices, terrainMaterial, colors);
            Polyline("Cyan perimeter trim", neon, trim, Cyan, .00085f / scale);
        }

        private void BuildRoute()
        {
            const int cross = 9;
            int count = layout.route.Length;
            var ribbon = new Vector3[count * cross];
            var normals = new Vector3[ribbon.Length];
            var tints = new Color[ribbon.Length];
            var indices = new int[(count - 1) * (cross - 1) * 6];
            var path = new Vector3[count];
            var left = new Vector3[count];
            var right = new Vector3[count];
            float normalStep = Mathf.Min(layout.terrain.width_m, layout.terrain.length_m) /
                Mathf.Max(32, layout.terrain.grid_size - 1);
            for (int i = 0; i < count; i++)
            {
                Vector2 point = CourseLayout.Ground(layout.route[i]);
                Vector2 tangent = (CourseLayout.Ground(layout.route[Mathf.Min(count - 1, i + 1)]) -
                    CourseLayout.Ground(layout.route[Mathf.Max(0, i - 1)])).normalized;
                float progress = i / (count - 1f);
                Vector2 edge = new Vector2(-tangent.y, tangent.x) * (surface.Width(progress) * .5f);
                Vector3 normal = surface.Normal(point, normalStep);
                Color tint = Fairway.linear * (.84f + .12f * Mathf.Sin(progress * Mathf.PI));
                for (int k = 0; k < cross; k++)
                {
                    int a = i * cross + k;
                    ribbon[a] = At(point + edge * (k * .25f - 1), .0012f / scale);
                    normals[a] = normal;
                    tints[a] = tint;
                    if (i == count - 1 || k == cross - 1)
                        continue;
                    int j = (i * (cross - 1) + k) * 6;
                    indices[j] = a; indices[j + 1] = a + 1; indices[j + 2] = a + cross + 1;
                    indices[j + 3] = a; indices[j + 4] = a + cross + 1; indices[j + 5] = a + cross;
                }
                left[i] = At(point + edge, .002f / scale);
                right[i] = At(point - edge, .002f / scale);
                path[i] = At(point, .004f / scale);
            }

            MeshObject("Dark teal fairway", transform, ribbon, indices, terrainMaterial, tints, normals);
            Polyline("Cyan fairway edge", neon, left, Cyan, .0013f / scale);
            Polyline("Cyan fairway edge", neon, right, Cyan, .0013f / scale);
            for (int i = 5; i < count - 3; i += 8)
            {
                Vector2 a = CourseLayout.Ground(layout.route[i]);
                Vector2 b = CourseLayout.Ground(layout.route[i + 1]);
                Vector2 c = CourseLayout.Ground(layout.route[i + 2]);
                Polyline("Direction dash", neon, new[] { At(a, .0018f / scale),
                    At(b, .0018f / scale), At(c, .0018f / scale) }, Lime, .0015f / scale);
            }
            Polyline("Preferred route", debug, path, Lime, .0025f);
        }

        private void Radial(string name, Transform root, Vector2 point, float outer, float inner, Material material,
            float lift, int? seed = null, Vector3 origin = default)
        {
            const int segments = 40;
            // Several radial bands keep the pool on the mesh across steeper ground.
            int bands = Mathf.Clamp(Mathf.CeilToInt((outer - inner) * scale / .003f), 1, 20);
            float phase = seed.HasValue ? (float)System.Math.IEEERemainder(seed.Value, 2 * System.Math.PI) : 0;
            var vertices = new Vector3[segments * (bands + 1)];
            var indices = new int[segments * bands * 6];
            for (int i = 0; i < segments; i++)
            {
                float angle = 2 * Mathf.PI * i / segments;
                Vector2 direction = new(Mathf.Cos(angle), Mathf.Sin(angle));
                float variation = seed.HasValue ? 1 + .06f * Mathf.Sin(angle * 5 + phase) : 1;
                for (int band = 0; band <= bands; band++)
                {
                    int a = band * segments + i;
                    float radius = Mathf.Lerp(inner, outer, band / (float)bands) * variation;
                    Vector2 p = point + direction * radius;
                    p.x = Mathf.Clamp(p.x, -layout.terrain.width_m / 2, layout.terrain.width_m / 2);
                    p.y = Mathf.Clamp(p.y, -layout.terrain.length_m / 2, layout.terrain.length_m / 2);
                    vertices[a] = At(p, lift / scale) - origin;
                    if (band == bands)
                        continue;
                    int next = (i + 1) % segments + band * segments;
                    int j = a * 6;
                    indices[j] = a; indices[j + 1] = next; indices[j + 2] = a + segments;
                    indices[j + 3] = next; indices[j + 4] = next + segments; indices[j + 5] = a + segments;
                }
            }
            MeshObject(name, root, vertices, indices, material);
        }

        private void BuildBarrier(Transform root, float footprint, bool crystal)
        {
            float size = footprint * (crystal ? .72f : 1);
            float height = footprint * (crystal ? 1.15f : .65f);
            var body = Block(root, "Body", Vector3.up * (height / 2), new Vector3(size, height, size), Steel);
            body.GetComponent<Renderer>().sharedMaterial = Lit(crystal ? Magenta : Steel);

            float a = size / 2;
            var corners = new Vector3[]
            {
                new(-a, 0, -a), new(a, 0, -a), new(a, 0, a), new(-a, 0, a),
                new(-a, height, -a), new(a, height, -a), new(a, height, a), new(-a, height, a)
            };
            int[] order = { 0, 1, 2, 3, 0, 4, 5, 1, 5, 6, 2, 6, 7, 3, 7, 4 };
            var edges = System.Array.ConvertAll(order, i => corners[i]);
            Polyline("Amber obstacle edges", FeatureNeon(root), edges, Amber, .0008f / scale);
        }

        private void Polyline(string name, Transform parent, Vector3[] points, Color color, float width)
        {
            var line = Group(name, parent).gameObject.AddComponent<LineRenderer>();
            line.useWorldSpace = false;
            line.positionCount = points.Length;
            line.SetPositions(points);
            line.widthMultiplier = width;
            line.numCornerVertices = 2;
            line.sharedMaterial = Paint(color);
        }

        private Vector3 At(Vector2 point, float lift)
        {
            // Sample the same triangle plane the collider uses. Raised
            // fairway lines and pool rims then stay above the visible mesh.
            int n = layout.terrain.grid_size;
            float x = Mathf.Clamp01(point.x / layout.terrain.width_m + .5f) * (n - 1);
            float z = Mathf.Clamp01(point.y / layout.terrain.length_m + .5f) * (n - 1);
            int column = Mathf.Min((int)x, n - 2);
            int row = Mathf.Min((int)z, n - 2);
            int a = row * n + column;
            float u = x - column;
            float v = z - row;
            float lower = terrainVertices[a].y;
            float left = terrainVertices[a + n].y;
            float right = terrainVertices[a + 1].y;
            float upper = terrainVertices[a + n + 1].y;
            float height = u >= v ? lower + (right - lower) * u + (upper - right) * v :
                lower + (upper - left) * u + (left - lower) * v;
            return new Vector3(point.x, height + lift, point.y);
        }

        private Transform City(Transform parent, string asset, float size)
        {
            var root = Group(asset ?? "City prop", parent);
            var prefab = asset == null ? null : Resources.Load<GameObject>("CyberpunkModels/" + asset);
            if (prefab && TryPlaceModel(root, prefab, size))
                return root;

            int index = System.Array.IndexOf(CourseLayout.CityAssets, asset);
            float height = size * (index switch { 0 => 1.25f, 3 or 7 => 1.1f, 8 or 9 => .35f, _ => .70f });
            Color accent = index % 2 == 0 ? Cyan : Magenta;
            Block(root, "Chassis", Vector3.up * height * .50f, new Vector3(size * .82f, height, size * .56f), Base);
            Block(root, "Neon sign", new Vector3(0, height * .78f, size * .29f),
                new Vector3(size * .72f, height * .17f, size * .07f), accent);
            Block(root, "Service bay", new Vector3(0, height * .40f, size * .29f),
                new Vector3(size * .46f, height * .34f, size * .07f), Ridge);
            return root;
        }

        private static string[] ReadGalleryAssets()
        {
            var catalog = Resources.Load<TextAsset>("CyberpunkModels/catalog");
            return catalog ? catalog.text.Split(new[] { '\r', '\n' }, System.StringSplitOptions.RemoveEmptyEntries)
                : CourseLayout.CityAssets;
        }

        private bool TryPlaceModel(Transform root, GameObject prefab, float size)
        {
            var model = Instantiate(prefab, root, false);
            var renderers = model.GetComponentsInChildren<Renderer>(true);
            if (renderers.Length == 0)
            {
                model.SetActive(false);
                Destroy(model);
                return false;
            }

            var bounds = new Bounds();
            bool first = true;
            foreach (Renderer renderer in renderers)
            {
                Bounds local = renderer.localBounds;
                Matrix4x4 toRoot = root.worldToLocalMatrix * renderer.localToWorldMatrix;
                for (int corner = 0; corner < 8; corner++)
                {
                    Vector3 p = toRoot.MultiplyPoint3x4(new Vector3(
                        (corner & 1) == 0 ? local.min.x : local.max.x,
                        (corner & 2) == 0 ? local.min.y : local.max.y,
                        (corner & 4) == 0 ? local.min.z : local.max.z));
                    if (first)
                    {
                        bounds = new Bounds(p, Vector3.zero);
                        first = false;
                    }
                    else
                        bounds.Encapsulate(p);
                }
                Material[] materials = renderer.sharedMaterials;
                for (int i = 0; i < materials.Length; i++)
                    if (materials[i])
                        materials[i] = TunePropMaterial(materials[i]);
                renderer.sharedMaterials = materials;
            }

            float factor = size / Mathf.Max(.0001f, bounds.size.x, bounds.size.y, bounds.size.z);
            Vector3 pivot = new(bounds.center.x, bounds.min.y, bounds.center.z);
            model.transform.localScale *= factor;
            model.transform.localPosition = factor * (model.transform.localPosition - pivot);
            var collider = root.gameObject.AddComponent<BoxCollider>();
            collider.center = factor * (bounds.center - pivot);
            collider.size = factor * bounds.size;
            collider.contactOffset = .001f;
            return true;
        }

        private Material TunePropMaterial(Material source)
        {
            if (propMaterials.TryGetValue(source, out Material cached))
                return cached;
            var material = new Material(source);
            foreach (string name in new[] { "_EmissionColor", "_EmissiveFactor" })
                if (material.HasProperty(name))
                    material.SetColor(name, material.GetColor(name) * .8f);
            foreach (string name in material.GetTexturePropertyNames())
                if (material.GetTexture(name) is Texture2D texture && texture.mipmapCount > 1)
                {
                    texture.filterMode = FilterMode.Trilinear;
                    texture.anisoLevel = 8;
                }
            propMaterials.Add(source, material);
            return material;
        }

        internal Shader FlatShader { private get; set; }

        internal Material Paint(Color color)
        {
            if (!colors.TryGetValue(color, out Material material))
            {
                material = new Material(FlatShader) { color = color };
                colors.Add(color, material);
            }
            return material;
        }

        private Material Lit(Color color)
        {
            if (!litColors.TryGetValue(color, out Material material))
            {
                material = new Material(terrainMaterial.shader);
                material.SetColor("_Tint", color);
                material.SetFloat("_UseVertexColor", 0);
                litColors.Add(color, material);
            }
            return material;
        }

        internal Transform Block(Transform parent, string name, Vector3 position, Vector3 size, Color color)
        {
            var item = GameObject.CreatePrimitive(PrimitiveType.Cube).transform;
            item.name = name;
            item.SetParent(parent, false);
            item.localPosition = position;
            item.localScale = size;
            item.GetComponent<Renderer>().sharedMaterial = Paint(color);
            return item;
        }

        internal static Transform Group(string name, Transform parent)
        {
            var group = new GameObject(name).transform;
            group.SetParent(parent, false);
            return group;
        }

        private GameObject MeshObject(string name, Transform parent, Vector3[] vertices, int[] triangles,
            Material material, Color[] tints = null, Vector3[] normals = null)
        {
            var obj = Group(name, parent).gameObject;
            var mesh = new Mesh { name = name, vertices = vertices, triangles = triangles };
            if (tints != null)
                mesh.colors = tints;
            if (normals != null)
                mesh.normals = normals;
            else
                mesh.RecalculateNormals();
            mesh.RecalculateBounds();
            obj.AddComponent<MeshFilter>().sharedMesh = mesh;
            obj.AddComponent<MeshRenderer>().sharedMaterial = material;
            meshes.Add(mesh);
            return obj;
        }

        private void OnDestroy()
        {
            foreach (Mesh mesh in meshes)
                Destroy(mesh);
            foreach (Material material in colors.Values)
                Destroy(material);
            foreach (Material material in litColors.Values)
                Destroy(material);
            foreach (Material material in propMaterials.Values)
                Destroy(material);
            if (terrainMaterial)
                Destroy(terrainMaterial);
        }
    }
}
