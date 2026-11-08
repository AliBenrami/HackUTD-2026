using System;
using UnityEngine;
#if UNITY_ANDROID && !UNITY_EDITOR
using UnityEngine.Android;
#endif

namespace GolfAR
{
    internal sealed class ClubLink : IDisposable
    {
        public readonly struct Motion
        {
            public readonly Vector3 Rate, Angle;
            public readonly float Seconds;
            public Motion(Vector3 rate, Vector3 angle, float seconds)
            {
                Rate = rate;
                Angle = angle;
                Seconds = seconds;
            }
        }

        public bool Requested { get; private set; }
        public string Status { get; private set; } = "Club disconnected";
#if UNITY_ANDROID && !UNITY_EDITOR
        private const string Scan = "android.permission.BLUETOOTH_SCAN";
        private const string Connect = "android.permission.BLUETOOTH_CONNECT";
        private AndroidJavaObject client;
        private PermissionCallbacks permissions;
        private float nextPoll;
        private string reported = "Club disconnected";

        public void ConnectIfAuthorized()
        {
            if (!Requested && HasPermissions())
                Toggle();
        }

        public void Toggle()
        {
            if (Requested)
            {
                Requested = false;
                client?.Call("disconnect");
                Status = "Club disconnected";
                return;
            }
            Requested = true;
            if (HasPermissions())
            {
                Start();
                return;
            }

            Status = "Allow Nearby devices for the club";
            permissions = new PermissionCallbacks();
            permissions.PermissionGranted += _ =>
            {
                if (Requested && HasPermissions() && Status == "Allow Nearby devices for the club")
                    Start();
            };
            permissions.PermissionDenied += _ =>
            {
                Requested = false;
                Status = "Nearby devices permission denied";
            };
            Permission.RequestUserPermissions(new[] { Scan, Connect }, permissions);
        }

        private static bool HasPermissions() => Permission.HasUserAuthorizedPermission(Scan) &&
            Permission.HasUserAuthorizedPermission(Connect);

        private void Start()
        {
            if (client == null)
            {
                using var player = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
                using var activity = player.GetStatic<AndroidJavaObject>("currentActivity");
                client = new AndroidJavaObject("com.golfar.clubble.ClubBle", activity);
            }
            Status = "Searching for club · power it on";
            nextPoll = Time.unscaledTime + .5f;
            client.Call("connect");
        }

        public bool Poll()
        {
            if (Requested && client != null && HasPermissions() && Time.unscaledTime >= nextPoll &&
                Status != "Allow Nearby devices for the club")
            {
                nextPoll = Time.unscaledTime + .25f;
                Status = client.Call<string>("status");
                Requested = client.Call<bool>("isActive");
            }
            if (Status == reported)
                return false;
            reported = Status;
            return true;
        }

        public bool TryMotion(out Motion motion)
        {
            motion = default;
            var packet = Requested && client != null ? client.Call<float[]>("motion") : null;
            if (packet == null || packet.Length != 7)
                return false;
            motion = new Motion(new Vector3(packet[0], packet[1], packet[2]),
                new Vector3(packet[3], packet[4], packet[5]), packet[6]);
            return true;
        }

        public void Dispose()
        {
            Requested = false;
            client?.Call("disconnect");
            client?.Dispose();
        }
#else
        public void ConnectIfAuthorized() { }
        public void Toggle() => Status = "Club BLE is available on Quest";
        public bool Poll() => false;
        public bool TryMotion(out Motion motion)
        {
            motion = default;
            return false;
        }
        public void Dispose() { }
#endif
    }
}
