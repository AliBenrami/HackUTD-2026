using System;
using System.Collections.Generic;
using System.Threading.Tasks;
using UnityEngine;

namespace GolfAR
{
    // Spatial persistence is optional. The session table stays usable when
    // Quest cannot create or localize an anchor in the current room.
    public sealed class TableAnchor : MonoBehaviour
    {
        private const string AnchorKey = "golfar.table.anchor";
        private OVRSpatialAnchor active;
        public bool Busy { get; private set; }

        public void Detach()
        {
            transform.SetParent(null, true);
        }

        public async Task<string> SaveAsync()
        {
            Busy = true;
            OVRSpatialAnchor pending = null;
            try
            {
                if (active && transform.parent == active.transform)
                    return "This table anchor is already saved.";
                if (!active)
                    await RestoreSavedHandleAsync();
                var root = new GameObject("Saved Meta table anchor");
                root.transform.SetPositionAndRotation(transform.position, transform.rotation);
                pending = root.AddComponent<OVRSpatialAnchor>();
                if (!await pending.WhenCreatedAsync() || !(await pending.SaveAnchorAsync()).Success)
                    return "Quest could not save the table anchor. Placement is active for this session.";

                var previous = active;
                Attach(pending);
                PlayerPrefs.SetString(AnchorKey, active.Uuid.ToString());
                PlayerPrefs.Save();
                pending = null;
                if (previous && previous != active)
                {
                    try
                    {
                        await previous.EraseAnchorAsync();
                    }
                    finally
                    {
                        Destroy(previous.gameObject);
                    }
                }
                return "Table anchor saved.";
            }
            finally
            {
                if (pending)
                    Destroy(pending.gameObject);
                Busy = false;
            }
        }

        public async Task<string> RestoreAsync()
        {
            Busy = true;
            try
            {
                if (!active)
                    await RestoreSavedHandleAsync();
                if (!active)
                    return "No saved table could be located. Place it again in this room.";
                Attach(active);
                return "Saved table restored.";
            }
            finally
            {
                Busy = false;
            }
        }

        private async Task RestoreSavedHandleAsync()
        {
            if (!Guid.TryParse(PlayerPrefs.GetString(AnchorKey), out Guid uuid))
                return;
            var loaded = new List<OVRSpatialAnchor.UnboundAnchor>();
            var result = await OVRSpatialAnchor.LoadUnboundAnchorsAsync(new[] { uuid }, loaded);
            if (!result.Success || loaded.Count == 0 || !await loaded[0].LocalizeAsync(8))
                return;
            var root = new GameObject("Saved Meta table anchor");
            var anchor = root.AddComponent<OVRSpatialAnchor>();
            loaded[0].BindTo(anchor);
            active = anchor;
        }

        private void Attach(OVRSpatialAnchor anchor)
        {
            active = anchor;
            transform.SetParent(anchor.transform, false);
            transform.SetLocalPositionAndRotation(Vector3.zero, Quaternion.identity);
        }
    }
}
