using UnityEngine;

namespace GolfAR
{
    internal sealed class GreenPlay
    {
        public const float CourseMagnification = 14f;
        public const float BallDiameter = .043f;
        private const float ShaftLength = .90f;
        private const float HeadHalfWidth = .058f;
        private const float HeadHalfHeight = .018f;
        private const float FaceDepth = .026f;
        private const float StanceRadius = .10f;
        private const string SwingDirectionPreference = "GolfAR.GyroSwingDirection";
        private readonly Transform origin, eye, club, shaft, head;
        private readonly TextMesh hud, sensorHint, strikeLabel;
        private readonly Renderer strikeFace;
        private readonly LineRenderer sensorAimLine, strikeGate;
        private readonly Material touchFace, sensorFace, addressFace, backswingFace, countedFace;
        private readonly SensorPutter sensor = new();
        private readonly bool xr;
        private Vector3 savedPosition, stance, previousFace, previousNormal;
        private bool sampled, hasStance;
        public bool Passthrough { get; private set; }
        private float sensorAim;
        private float? previewAim;
        private Vector3? passthroughSpot;
        private bool aimStickLatched;
        private ClubLink.Motion? trainingStart;
        private Vector3 trainingAxis;
        private float trainingTime;
        private float hitUntil;
        private Vector3 hitAddress, hitNormal;
        private Vector3 mountedHead, mountedFace;
        private bool mountedCalibrated, mountedAddressSeen, mountedArmed;
        public bool Active { get; private set; }

        public GreenPlay(Transform parent, Transform origin, Camera eye, CourseView palette, bool xr)
        {
            this.origin = origin;
            this.eye = eye.transform;
            this.xr = xr;
            if (xr && PlayerPrefs.HasKey(SwingDirectionPreference))
                sensor.LearnBackswing(JsonUtility.FromJson<Vector3>(PlayerPrefs.GetString(SwingDirectionPreference)));
            club = CourseView.Group("Touch putter", parent);
            shaft = palette.Block(club, "Shaft", Vector3.zero, Vector3.one, Color.gray);
            head = CourseView.Group("Putter head", club);
            AddHeadPart("Head", Vector3.zero, new Vector3(2 * HeadHalfWidth, 2 * HeadHalfHeight, 2 * FaceDepth),
                new Color32(50, 85, 99, 255));
            strikeFace = AddHeadPart("Strike face", new Vector3(0, 0, FaceDepth),
                new Vector3(2 * HeadHalfWidth, .026f, .002f), CourseView.Cyan);
            touchFace = palette.Paint(CourseView.Cyan);
            sensorFace = palette.Paint(CourseView.Lime);
            addressFace = palette.Paint(CourseView.Amber);
            backswingFace = palette.Paint(CourseView.Cyan);
            countedFace = palette.Paint(Color.white);
            AddHeadPart("Alignment mark", new Vector3(0, HeadHalfHeight, 0),
                new Vector3(.004f, .002f, .042f), Color.white);
            shaft.GetComponent<Collider>().enabled = false;
            hud = TableMenu.Text("", eye.transform, new Vector3(0, -.38f, 1.1f), .022f, TextAnchor.MiddleCenter);
            sensorHint = TableMenu.Text("", eye.transform, new Vector3(0, -.43f, 1.1f), .019f, TextAnchor.MiddleCenter);
            sensorAimLine = CourseView.Group("Sensor aim", parent).gameObject.AddComponent<LineRenderer>();
            sensorAimLine.sharedMaterial = sensorFace;
            sensorAimLine.widthMultiplier = .008f;
            sensorAimLine.positionCount = 2;
            strikeGate = CourseView.Group("Club address gate", parent).gameObject.AddComponent<LineRenderer>();
            strikeGate.widthMultiplier = .008f;
            strikeGate.positionCount = 4;
            strikeLabel = TableMenu.Text("", parent, Vector3.zero, .038f, TextAnchor.MiddleCenter);
            HideClub();
            hud.gameObject.SetActive(false);

            Renderer AddHeadPart(string name, Vector3 position, Vector3 size, Color color)
            {
                var part = palette.Block(head, name, position, size, color);
                part.GetComponent<Collider>().enabled = false;
                return part.GetComponent<Renderer>();
            }
        }

        public void Enter()
        {
            if (Active)
                return;
            savedPosition = origin.position;
            Active = true;
        }

        public void Exit()
        {
            if (!Active)
                return;
            origin.position = savedPosition;
            Active = false;
            hasStance = false;
            passthroughSpot = null;
            HideClub();
            hud.gameObject.SetActive(false);
        }

        public void SetPassthrough(bool enabled)
        {
            if (Passthrough == enabled)
                return;
            Passthrough = enabled;
            if (Active && enabled)
                origin.position = savedPosition;
            hasStance = false;
            passthroughSpot = null;
            HideClub();
        }

        public bool AtLie
        {
            get
            {
                if (!Passthrough)
                    return true;
                // A putting posture moves the headset forward even when the feet stay planted.
                float reach = eye.forward.y < -.35f ? .60f : .35f;
                return hasStance && Vector3.ProjectOnPlane(eye.position - stance, Vector3.up).sqrMagnitude <= reach * reach;
            }
        }

        public void ShowStatus(string status, bool visible)
        {
            hud.text = status;
            hud.gameObject.SetActive(Active && visible);
        }

        public void HideClub()
        {
            sampled = false;
            mountedAddressSeen = mountedArmed = false;
            sensor.Reset();
            previewAim = null;
            trainingStart = null;
            sensorHint.gameObject.SetActive(false);
            sensorAimLine.enabled = false;
            strikeGate.enabled = false;
            strikeLabel.gameObject.SetActive(false);
            club.gameObject.SetActive(false);
        }

        public void Spawn(CourseView course, Vector3 ball, bool keepAim = false)
        {
            hitUntil = 0;
            if (!keepAim)
                sensorAim = 0;
            if (Passthrough)
            {
                Vector3 spot = !keepAim && passthroughSpot.HasValue
                    ? passthroughSpot.Value : eye.position + Forward() * .48f;
                PlacePassthroughBall(course, ball, spot);
                return;
            }
            Vector3 heading = course.PuttHeading(ball);
            Vector3 right = Vector3.Cross(Vector3.up, heading);
            Vector3 feet = ball - heading * .07f - right * .48f;
            Bounds bounds = course.TerrainCollider.bounds;
            feet.x = Mathf.Clamp(feet.x, bounds.min.x + .07f, bounds.max.x - .07f);
            feet.z = Mathf.Clamp(feet.z, bounds.min.z + .07f, bounds.max.z - .07f);
            Vector3 offset = feet - eye.position;
            offset.y = Ground(course, feet, out float floor) ? floor + (xr ? 0 : 1.55f) - origin.position.y : 0;
            origin.position += offset;
            stance = feet;
            hasStance = true;
            HideClub();
        }

        public bool TryPassthroughSpot(Ray ray, out Vector3 spot)
        {
            spot = default;
            if (!Passthrough || ray.direction.y > -.12f ||
                !new Plane(Vector3.up, origin.position).Raycast(ray, out float distance) || distance > 3f)
                return false;
            spot = ray.GetPoint(distance);
            float reach = Vector3.ProjectOnPlane(spot - eye.position, Vector3.up).magnitude;
            return reach >= .18f && reach <= 1.05f;
        }

        public void PlacePassthroughBall(CourseView course, Vector3 ball, Vector3 spot)
        {
            // Translate the virtual lie in floor-level tracking space.
            spot.y = origin.position.y + BallDiameter / 2 + .001f;
            passthroughSpot = spot;
            course.transform.parent.position += spot - ball;
            Physics.SyncTransforms();
            stance = eye.position;
            hasStance = true;
            hitUntil = 0;
            HideClub();
        }

        public void KeepAtLie()
        {
            if (!Active || !hasStance || Passthrough)
                return;
            Vector3 lean = Vector3.ProjectOnPlane(eye.position - stance, Vector3.up);
            if (lean.sqrMagnitude <= StanceRadius * StanceRadius)
                return;
            origin.position -= lean - Vector3.ClampMagnitude(lean, StanceRadius);
            sampled = false;
        }

        public void UpdateClub(CourseView course, Putting putting, Transform controller, bool armed)
        {
            sensorHint.gameObject.SetActive(false);
            sensorAimLine.enabled = false;
            strikeGate.enabled = false;
            strikeLabel.gameObject.SetActive(false);
            Vector3 grip = controller.position;
            Vector3 down = controller.TransformDirection(new Vector3(0, -.97f, .24f).normalized);
            Vector3 tip = grip + down * ShaftLength;
            bool playable = down.y < -.35f;
            if (Ground(course, tip, out float floor) && tip.y < floor + HeadHalfHeight)
            {
                playable &= tip.y >= floor - .055f;
                tip.y = floor + HeadHalfHeight;
            }
            Vector3 flatFace = Vector3.ProjectOnPlane(-controller.right, Vector3.up);
            playable &= flatFace.sqrMagnitude >= .16f;
            Vector3 normal = playable ? flatFace.normalized : Forward();
            DrawClub(grip, tip, normal, touchFace);
            Vector3 face = tip + normal * FaceDepth;
            if (armed && playable && sampled && !putting.Rolling && !putting.Holed &&
                TryImpact(previousFace, previousNormal, face, normal, putting.BallCenter, putting.BallRadius,
                    Time.deltaTime, out Vector3 direction, out float speed))
                putting.Strike(direction, LaunchSpeed(speed));
            sampled = armed && playable;
            previousFace = face;
            previousNormal = normal;
        }

        public void AdjustSensorAim(float degrees)
        {
            sensorAim = Mathf.DeltaAngle(0, sensorAim + degrees);
            sensor.Reset();
        }

        public void UpdateAimStick(float horizontal)
        {
            if (Mathf.Abs(horizontal) <= .25f)
                aimStickLatched = false;
            if (aimStickLatched || Mathf.Abs(horizontal) < .70f)
                return;
            aimStickLatched = true;
            AdjustSensorAim(Mathf.Sign(horizontal) * 5);
        }

        public bool FlipBackswing()
        {
            if (!sensor.FlipBackswing())
                return false;
            HideClub();
            SaveSwingDirection();
            return true;
        }

        private void SaveSwingDirection()
        {
            if (!xr)
                return;
            PlayerPrefs.SetString(SwingDirectionPreference, JsonUtility.ToJson(sensor.SwingDirection));
            PlayerPrefs.Save();
        }

        public bool TrainBackswing(ClubLink.Motion? motion, bool pressed)
        {
            if (pressed && trainingStart.HasValue)
            {
                HideClub();
                return true;
            }
            if (pressed && motion.HasValue)
            {
                HideClub();
                trainingStart = motion;
                trainingTime = motion.Value.Seconds;
                trainingAxis = Vector3.zero;
            }
            if (!trainingStart.HasValue)
                return false;
            if (!motion.HasValue || motion.Value.Seconds < trainingTime || motion.Value.Seconds - trainingTime > .12f)
            {
                HideClub();
                ShowClubHint("Gyro interrupted · click left stick to retry");
                return true;
            }
            var sample = motion.Value;
            trainingTime = sample.Seconds;
            Vector3 travel = sample.Angle - trainingStart.Value.Angle -
                trainingStart.Value.Rate * (sample.Seconds - trainingStart.Value.Seconds);
            if (trainingAxis == Vector3.zero && travel.sqrMagnitude >= 10 * 10)
                trainingAxis = travel.normalized;
            if (trainingAxis != Vector3.zero && travel.sqrMagnitude <= 3 * 3 && sample.Rate.sqrMagnitude < 12 * 12)
            {
                sensor.LearnBackswing(trainingAxis);
                SaveSwingDirection();
                trainingStart = null;
                ShowClubHint("Backswing direction set · hold still");
            }
            else
                ShowClubHint(trainingAxis == Vector3.zero ? "Take the club straight back" : "Return slowly to address");
            return true;
        }

        public void ClearMountedCalibration() => mountedCalibrated = false;

        public void UpdateMountedClub(CourseView course, Putting putting, Transform controller, bool calibrate)
        {
            if (putting.Rolling || putting.Holed || !controller)
            {
                HideClub();
                if (putting.Rolling || putting.Holed)
                {
                    if (Time.unscaledTime < hitUntil)
                        ShowStrikeGate(hitAddress, hitNormal, countedFace, "HIT COUNTED");
                }
                else
                    ShowClubHint("Keep the right Touch in view");
                return;
            }

            Vector3 ball = putting.BallCenter;
            Vector3 guide = course.PuttHeading(ball);
            float contactDistance = putting.BallRadius + FaceDepth + .003f;
            Vector3 address = ball - guide * contactDistance;
            if (calibrate)
            {
                mountedHead = controller.InverseTransformPoint(address);
                mountedFace = controller.InverseTransformDirection(guide);
                mountedCalibrated = true;
                mountedAddressSeen = mountedArmed = sampled = false;
            }
            if (!mountedCalibrated)
            {
                ShowStrikeGate(address, guide, addressFace, "CALIBRATE");
                ShowClubHint("Square the club at the bracket · press left X");
                return;
            }

            Vector3 tip = controller.TransformPoint(mountedHead);
            Vector3 flatFace = Vector3.ProjectOnPlane(controller.TransformDirection(mountedFace), Vector3.up);
            if (flatFace.sqrMagnitude < .25f)
            {
                HideClub();
                ShowClubHint("Set the club head down at address");
                return;
            }
            Vector3 normal = flatFace.normalized;
            Vector3 face = tip + normal * FaceDepth;
            Vector3 relative = ball - face;
            float setback = Vector3.Dot(relative, normal) - putting.BallRadius;
            float sideways = Mathf.Abs(Vector3.Dot(relative, Vector3.Cross(Vector3.up, normal)));
            bool linedUp = sideways <= HeadHalfWidth && Mathf.Abs(relative.y) <= HeadHalfHeight;
            mountedAddressSeen |= linedUp && setback >= -.02f && setback <= .04f;
            mountedArmed |= mountedAddressSeen && linedUp && setback >= .05f;
            Material readiness = mountedArmed ? backswingFace : mountedAddressSeen ? sensorFace : addressFace;
            DrawClub(controller.position, tip, normal, readiness, showShaft: !Passthrough);
            ShowStrikeGate(address, guide, readiness, mountedArmed ? "ARMED" : mountedAddressSeen ? "READY" : "SET CLUB");
            ShowClubHint(mountedArmed ? "Swing through the ball" : "Left X recalibrates the club");
            if (sampled && mountedArmed && TryImpact(previousFace, previousNormal, face, normal, ball,
                putting.BallRadius, Time.deltaTime, out Vector3 direction, out float speed))
            {
                putting.Strike(direction, LaunchSpeed(speed));
                hitUntil = Time.unscaledTime + 1f;
                hitAddress = address;
                hitNormal = guide;
                ShowStrikeGate(address, guide, countedFace, "HIT COUNTED");
                Debug.Log("[golf-club] Tracked club putt");
            }
            sampled = true;
            previousFace = face;
            previousNormal = normal;
        }

        public void PreviewSensorAim(CourseView course, Vector3 ball, Ray ray)
        {
            sensor.Reset();
            club.gameObject.SetActive(false);
            strikeGate.enabled = false;
            strikeLabel.gameObject.SetActive(false);
            Vector3 target;
            if (course.TerrainCollider.Raycast(ray, out RaycastHit hit, 15))
                target = hit.point;
            else if (new Plane(Vector3.up, ball).Raycast(ray, out float distance) && distance <= 15)
                target = ray.GetPoint(distance);
            else
                target = ball + Vector3.ProjectOnPlane(ray.direction, Vector3.up).normalized * 2;

            Vector3 aim = Vector3.ProjectOnPlane(target - ball, Vector3.up);
            if (aim.sqrMagnitude < .07f * .07f)
            {
                previewAim = null;
                sensorAimLine.enabled = false;
                ShowClubHint("Point beyond the ball to aim");
                return;
            }
            previewAim = Vector3.SignedAngle(course.PuttHeading(ball), aim, Vector3.up);
            sensorAimLine.enabled = true;
            sensorAimLine.sharedMaterial = touchFace;
            sensorAimLine.SetPosition(0, ball + aim.normalized * .05f);
            sensorAimLine.SetPosition(1, target + Vector3.up * .035f);
            ShowClubHint("Release trigger to lock this aim");
        }

        public void FinishSensorAim()
        {
            if (!previewAim.HasValue)
                return;
            sensorAim = previewAim.Value;
            previewAim = null;
            sensor.Reset();
        }

        public void ShowClubHint(string message)
        {
            sensorHint.text = message;
            sensorHint.gameObject.SetActive(true);
        }

        public void UpdateSensorClub(CourseView course, Putting putting, ClubLink.Motion? motion)
        {
            sampled = false;
            if (putting.Rolling || putting.Holed)
            {
                HideClub();
                if (Time.unscaledTime < hitUntil)
                    ShowStrikeGate(hitAddress, hitNormal, countedFace, "HIT COUNTED");
                return;
            }
            Vector3 ball = putting.BallCenter;
            Vector3 normal = Quaternion.Euler(0, sensorAim, 0) * course.PuttHeading(ball);
            float speed = 0;
            if (motion.HasValue)
                speed = sensor.Update(motion.Value);
            else
                sensor.Reset();

            Material readiness = sensor.Backswing ? backswingFace :
                sensor.Addressed && !sensor.Canceled ? sensorFace : addressFace;
            sensorAimLine.enabled = motion.HasValue;
            sensorAimLine.sharedMaterial = readiness;
            sensorAimLine.SetPosition(0, ball + normal * .05f);
            sensorAimLine.SetPosition(1, ball + normal * .40f);
            Vector3 address = ball - normal * (putting.BallRadius + FaceDepth + .003f);
            if (motion.HasValue)
            {
                float angle = sensor.Angle * Mathf.Deg2Rad;
                Vector3 tip = address - normal * (Mathf.Sin(angle) * SensorPutter.LeverMeters) +
                    Vector3.up * ((1 - Mathf.Cos(angle)) * SensorPutter.LeverMeters);
                Vector3 grip = address + Vector3.up * .86f + Vector3.Cross(normal, Vector3.up) * .24f;
                DrawClub(grip, tip, normal, readiness, showShaft: !Passthrough);
                ShowStrikeGate(address, normal, readiness, sensor.Backswing ? "ARMED" :
                    sensor.Canceled ? "RESET" : sensor.Addressed ? "READY" : "HOLD STILL");
            }
            else
            {
                club.gameObject.SetActive(false);
                strikeGate.enabled = false;
                strikeLabel.gameObject.SetActive(false);
            }
            ShowClubHint(!motion.HasValue ? "Club · waiting for live gyro" : sensor.Canceled ?
                "Return the club to address" : sensor.Backswing ? "Swing through the ball" : sensor.Addressed ?
                "Club ready · take it back until the line turns blue" : "Hold the club still behind the ball");
            if (speed > 0)
            {
                float launchSpeed = LaunchSpeed(speed);
                putting.Strike(normal, launchSpeed);
                hitUntil = Time.unscaledTime + 1f;
                hitAddress = address;
                hitNormal = normal;
                ShowStrikeGate(hitAddress, hitNormal, countedFace, "HIT COUNTED");
                Debug.Log($"[golf-club] Sensor putt at {launchSpeed:F2} m/s");
            }
        }

        private void ShowStrikeGate(Vector3 address, Vector3 normal, Material material, string label)
        {
            Vector3 side = Vector3.Cross(Vector3.up, normal) * .086f;
            Vector3 left = address - side;
            Vector3 right = address + side;
            strikeGate.enabled = true;
            strikeGate.sharedMaterial = material;
            strikeGate.SetPosition(0, left - normal * .025f);
            strikeGate.SetPosition(1, left);
            strikeGate.SetPosition(2, right);
            strikeGate.SetPosition(3, right - normal * .025f);
            strikeLabel.color = material.color;
            strikeLabel.text = label;
            strikeLabel.transform.SetPositionAndRotation(address + Vector3.up * .145f,
                Quaternion.LookRotation(eye.forward, eye.up));
            strikeLabel.gameObject.SetActive(true);
        }

        private void DrawClub(Vector3 grip, Vector3 tip, Vector3 normal, Material face, bool showShaft = true)
        {
            club.gameObject.SetActive(true);
            shaft.gameObject.SetActive(showShaft);
            Vector3 shaftVector = grip - tip;
            shaft.SetPositionAndRotation((grip + tip) * .5f, Quaternion.FromToRotation(Vector3.up, shaftVector));
            shaft.localScale = new Vector3(.012f, shaftVector.magnitude, .012f);
            head.SetPositionAndRotation(tip, Quaternion.LookRotation(normal));
            if (strikeFace.sharedMaterial != face)
                strikeFace.sharedMaterial = face;
        }

        internal static bool TryImpact(Vector3 from, Vector3 fromNormal, Vector3 to, Vector3 toNormal,
            Vector3 ball, float radius, float deltaTime, out Vector3 direction, out float speed)
        {
            direction = default;
            speed = 0;
            float before = Vector3.Dot(ball - from, fromNormal) - radius;
            float after = Vector3.Dot(ball - to, toNormal) - radius;
            if (before <= 0 || after > 0)
                return false;

            float t = before / (before - after);
            Vector3 face = Vector3.Slerp(fromNormal, toNormal, t);
            Vector3 contact = ball - face * radius - Vector3.Lerp(from, to, t);
            Vector3 right = Vector3.Cross(Vector3.up, face);
            float lateral = Mathf.Abs(Vector3.Dot(contact, right));
            if (lateral > HeadHalfWidth + radius * .3f || Mathf.Abs(contact.y) > HeadHalfHeight + radius * .4f)
                return false;

            Vector3 velocity = Vector3.ProjectOnPlane(to - from, Vector3.up) / Mathf.Max(deltaTime, .001f);
            float normalSpeed = Vector3.Dot(velocity, face);
            if (normalSpeed < .08f || velocity.sqrMagnitude > 64f)
                return false;

            float centered = 1 - Mathf.Clamp01(lateral / HeadHalfWidth);
            direction = Vector3.Lerp(face, velocity.normalized, .15f).normalized;
            speed = normalSpeed * Mathf.Lerp(.65f, 1f, centered);
            return true;
        }

        private static float LaunchSpeed(float speed)
        {
            float gain = Mathf.Lerp(1.3f, 1.9f, Mathf.InverseLerp(.45f, 3.2f, speed));
            return Mathf.Clamp(speed * gain, .08f, Putting.MaxImmersiveLaunchSpeed);
        }

        private static bool Ground(CourseView course, Vector3 point, out float y)
        {
            var ray = new Ray(new Vector3(point.x, course.TerrainCollider.bounds.max.y + 1, point.z), Vector3.down);
            bool hit = course.TerrainCollider.Raycast(ray, out RaycastHit ground, 3f);
            y = ground.point.y;
            return hit;
        }

        private Vector3 Forward()
        {
            Vector3 forward = Vector3.ProjectOnPlane(eye.forward, Vector3.up);
            return forward.sqrMagnitude > .01f ? forward.normalized : Vector3.forward;
        }

    }
}
