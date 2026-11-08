using System;
using System.Collections.Generic;
using UnityEngine;

namespace GolfAR
{
    internal sealed class TableMenu
    {
        public readonly struct Entry
        {
            public readonly string Label;
            public readonly Action Press;

            public Entry(string label, Action press)
            {
                Label = label;
                Press = press;
            }
        }

        private readonly Dictionary<Collider, (Action Action, Renderer Renderer)> buttons = new();
        private readonly Transform root;
        private readonly TextMesh title, status;
        private readonly CourseView palette;
        private Transform page;
        private Renderer hovered;
        private BoxCollider panel;
        public bool Visible { get => root.gameObject.activeSelf; set => root.gameObject.SetActive(value); }

        public TableMenu(Transform parent, CourseView palette)
        {
            this.palette = palette;
            root = CourseView.Group("World-space course menu", parent);
            title = Text("GolfAR", root, new Vector3(-.214f, .055f, -.007f), .027f);
            status = Text("", root, new Vector3(-.214f, .021f, -.007f), .016f);
        }

        public void Place(Camera eye, float? tabletopHeight)
        {
            Vector3 direction = Vector3.ProjectOnPlane(eye.transform.forward, Vector3.up);
            if (direction.sqrMagnitude < .001f)
                direction = Vector3.forward;
            direction.Normalize();
            Vector3 right = Vector3.Cross(Vector3.up, direction);
            Vector3 position = eye.transform.position + direction * .86f + right * .19f;
            position.y = tabletopHeight.HasValue
                ? Mathf.Max(position.y + .04f, tabletopHeight.Value + .38f)
                : position.y - .07f;
            root.position = position;
            root.rotation = Quaternion.LookRotation(direction);
        }

        public void Set(string heading, string message, Entry[] entries)
        {
            if (page)
            {
                page.gameObject.SetActive(false);
                UnityEngine.Object.Destroy(page.gameObject);
            }
            buttons.Clear();
            hovered = null;
            title.text = heading;
            status.text = message;
            page = CourseView.Group("Menu page", root);
            int rows = Mathf.CeilToInt(entries.Length / 3f);
            float height = .10f + .039f * rows;
            var backing = palette.Block(page, "Panel", new Vector3(0, .078f - height / 2, .002f),
                new Vector3(.456f, height, .007f), new Color32(19, 30, 41, 255));
            panel = backing.GetComponent<BoxCollider>();
            for (int i = 0; i < entries.Length; i++)
            {
                var entry = entries[i];
                Vector3 center = new(-.146f + i % 3 * .146f, -.014f - i / 3 * .039f, -.006f);
                var tile = palette.Block(page, entry.Label, center,
                    new Vector3(.138f, .033f, .009f), Normal);
                Text(entry.Label, page, center + Vector3.forward * -.006f, .020f, TextAnchor.MiddleCenter);
                buttons.Add(tile.GetComponent<Collider>(), (entry.Press, tile.GetComponent<Renderer>()));
            }
            Physics.SyncTransforms();
        }

        public bool Raycast(Ray ray, out RaycastHit hit)
        {
            hit = default;
            if (!Visible || !panel || !panel.Raycast(ray, out hit, 5f))
                return false;
            foreach (Collider button in buttons.Keys)
                if (button.Raycast(ray, out RaycastHit candidate, hit.distance))
                    hit = candidate;
            return true;
        }

        public void UpdateHover(Collider target)
        {
            Renderer next = target && buttons.TryGetValue(target, out var button) ? button.Renderer : null;
            if (next == hovered)
                return;
            if (hovered)
                hovered.sharedMaterial = palette.Paint(Normal);
            hovered = next;
            if (hovered)
                hovered.sharedMaterial = palette.Paint(new Color32(23, 118, 133, 255));
        }

        public bool Press(Collider target)
        {
            if (!target || !buttons.TryGetValue(target, out var button))
                return false;
            button.Action();
            return true;
        }

        private static readonly Color Normal = new Color32(40, 63, 80, 255);

        internal static TextMesh Text(string value, Transform parent, Vector3 position, float size,
            TextAnchor anchor = TextAnchor.MiddleLeft)
        {
            var label = CourseView.Group("Label", parent).gameObject.AddComponent<TextMesh>();
            label.transform.localPosition = position;
            label.text = value;
            label.font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            label.GetComponent<MeshRenderer>().sharedMaterial = label.font.material;
            label.fontSize = 64;
            label.characterSize = size * .12f;
            label.anchor = anchor;
            label.alignment = anchor == TextAnchor.MiddleCenter ? TextAlignment.Center : TextAlignment.Left;
            label.color = Color.white;
            return label;
        }
    }
}
