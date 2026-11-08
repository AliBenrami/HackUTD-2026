using System;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using Newtonsoft.Json;
using UnityEngine;

namespace GolfAR
{
    internal sealed class PhysicalObstacles
    {
        private const int Limit = 40;
        private static readonly string[] Kinds = { "Rock", "Hill", "Water", "Wall", "Generic" };
        private readonly Transform root;
        private readonly CourseView palette;
        private readonly List<Obstacle> items = new();
        private readonly List<Transform> proxies = new();
        private int selection = -1;
        private bool highlight = true;
        private MeshCollider ground;

        [Serializable]
        private sealed class Obstacle
        {
            public float x, z;
            public float width = .055f, length = .055f, height = .055f;
            public int kind;
        }

        public string Summary => selection >= 0
            ? $"Obstacle {selection + 1}/{items.Count} · {Kinds[items[selection].kind]} · {items[selection].width * 100:F0} cm"
            : "No physical obstacles";

        public PhysicalObstacles(Transform parent, CourseView palette)
        {
            root = CourseView.Group("Table-local physical obstacles", parent);
            this.palette = palette;
        }

        public void Show(bool visible) => root.gameObject.SetActive(visible);

        public void SetGround(MeshCollider terrain)
        {
            ground = terrain;
            if (proxies.Count == 0)
                return;
            if (ground)
                Physics.SyncTransforms();
            foreach (Transform proxy in proxies)
            {
                Vector3 local = proxy.localPosition;
                local.y = 0;
                Vector3 point = root.TransformPoint(local);
                var ray = new Ray(point + root.up, -root.up);
                if (ground && ground.Raycast(ray, out RaycastHit hit, 2))
                    local.y = root.InverseTransformPoint(hit.point).y;
                proxy.localPosition = local;
            }
        }

        public void Add(Vector3 tablePoint)
        {
            if (items.Count >= Limit)
                throw new ArgumentException("The table is full.");
            var item = new Obstacle { x = tablePoint.x, z = tablePoint.z };
            Clamp(item);
            items.Add(item);
            selection = items.Count - 1;
            Refresh();
        }

        public void Cycle()
        {
            if (items.Count == 0)
                return;
            selection = (selection + 1) % items.Count;
            Refresh();
        }

        public void Move(Vector2 delta) => Edit(item => { item.x += delta.x; item.z += delta.y; });
        public void Resize(float delta) => Edit(item => { item.width += delta; item.length += delta; });
        public void ChangeHeight(float delta) => Edit(item => item.height += delta);
        public void ChangeKind() => Edit(item => item.kind = (item.kind + 1) % Kinds.Length);

        public void ToggleHighlight()
        {
            highlight = !highlight;
            Refresh();
        }

        public void Remove()
        {
            if (selection < 0)
                return;
            items.RemoveAt(selection);
            selection = Mathf.Min(selection, items.Count - 1);
            Refresh();
        }

        public void Clear()
        {
            items.Clear();
            selection = -1;
            Refresh();
        }

        public IReadOnlyList<Bounds> Footprints(Transform stage)
        {
            return items.Select(item =>
            {
                var bounds = new Bounds(stage.InverseTransformPoint(root.TransformPoint(
                    new Vector3(item.x, 0, item.z))), Vector3.zero);
                for (int x = -1; x <= 1; x += 2)
                    for (int z = -1; z <= 1; z += 2)
                        bounds.Encapsulate(stage.InverseTransformPoint(root.TransformPoint(new Vector3(
                            item.x + x * item.width / 2, 0, item.z + z * item.length / 2))));
                return bounds;
            }).ToArray();
        }

        public void Save(string path) => File.WriteAllText(path, JsonConvert.SerializeObject(items, Formatting.Indented));

        public void Load(string path)
        {
            var loaded = JsonConvert.DeserializeObject<List<Obstacle>>(File.ReadAllText(path));
            if (loaded == null || loaded.Count > Limit)
                throw new ArgumentException("Invalid obstacle layout.");
            foreach (var item in loaded)
            {
                if (item == null || item.kind < 0 || item.kind >= Kinds.Length ||
                    !float.IsFinite(item.x) || !float.IsFinite(item.z) || !float.IsFinite(item.width) ||
                    !float.IsFinite(item.length) || !float.IsFinite(item.height))
                    throw new ArgumentException("Invalid obstacle layout.");
                Clamp(item);
            }
            items.Clear();
            items.AddRange(loaded);
            selection = items.Count == 0 ? -1 : 0;
            Refresh();
        }

        private void Edit(Action<Obstacle> edit)
        {
            if (selection < 0)
                return;
            var item = items[selection];
            edit(item);
            Clamp(item);
            Refresh();
        }

        private static void Clamp(Obstacle item)
        {
            item.width = Mathf.Clamp(item.width, .02f, .24f);
            item.length = Mathf.Clamp(item.length, .02f, .24f);
            item.height = Mathf.Clamp(item.height, .005f, .25f);
            float x = (CourseLayout.Table.x - item.width) / 2;
            float z = (CourseLayout.Table.y - item.length) / 2;
            item.x = Mathf.Clamp(item.x, -x, x);
            item.z = Mathf.Clamp(item.z, -z, z);
        }

        private void Refresh()
        {
            foreach (Transform proxy in proxies)
            {
                proxy.gameObject.SetActive(false);
                UnityEngine.Object.Destroy(proxy.gameObject);
            }
            proxies.Clear();
            for (int i = 0; i < items.Count; i++)
            {
                var item = items[i];
                var group = CourseView.Group(Kinds[item.kind], root);
                group.localPosition = new Vector3(item.x, 0, item.z);
                var color = i == selection ? CourseView.Lime : item.kind == 2 ? CourseView.Cyan : CourseView.Magenta;
                float height = item.kind == 2 ? .005f : item.height;
                if (highlight)
                {
                    const float line = .0025f;
                    for (int sign = -1; sign <= 1; sign += 2)
                    {
                        var horizontal = palette.Block(group, "Footprint edge", new Vector3(0, .006f, sign * item.length / 2),
                            new Vector3(item.width + line, line, line), color);
                        var vertical = palette.Block(group, "Footprint edge", new Vector3(sign * item.width / 2, .006f, 0),
                            new Vector3(line, line, item.length + line), color);
                        horizontal.GetComponent<Collider>().enabled = false;
                        vertical.GetComponent<Collider>().enabled = false;
                    }
                }
                else if (item.kind is 0 or 1)
                {
                    var rock = GameObject.CreatePrimitive(PrimitiveType.Sphere);
                    rock.transform.SetParent(group, false);
                    rock.transform.localPosition = Vector3.up * height / 2;
                    rock.transform.localScale = new Vector3(item.width, height, item.length);
                    rock.GetComponent<Renderer>().sharedMaterial = palette.Paint(color);
                    rock.GetComponent<Collider>().enabled = false;
                }
                else
                {
                    var visual = palette.Block(group, "Obstacle proxy", Vector3.up * height / 2,
                        new Vector3(item.width, height, item.length), color);
                    visual.GetComponent<Collider>().enabled = false;
                }
                var collider = group.gameObject.AddComponent<BoxCollider>();
                collider.center = Vector3.up * item.height / 2;
                collider.size = new Vector3(item.width, item.height, item.length);
                proxies.Add(group);
            }
            SetGround(ground);
        }
    }
}
