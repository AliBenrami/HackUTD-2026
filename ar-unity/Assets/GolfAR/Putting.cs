using System;
using UnityEngine;

namespace GolfAR
{
    internal sealed class Putting : MonoBehaviour
    {
        private const float FullChargeSeconds = 1.1f;
        internal const float MaxImmersiveLaunchSpeed = 6.5f;
        internal const float DropReach = 1.5f;
        private readonly Collider[] dropOverlaps = new Collider[16];
        private CourseView course;
        private CourseLayout layout;
        private Rigidbody body;
        private LineRenderer guide, power;
        private PhysicsMaterial ballMaterial;
        private Action<string> report;
        private Vector3 lie, aim, lastPosition;
        private float chargeStarted, rollTime, restTime;
        private int strokes;
        private float Radius => course.Ball.lossyScale.x / 2;

        public bool Aiming { get; private set; }
        public bool Rolling { get; private set; }
        public bool Holed { get; private set; }
        public Vector3 BallCenter => body.position;
        public float BallRadius => Radius;
        public bool Immersive { get; set; }
        public event Action<Putting> BallRested;

        public void Initialize(CourseView view, CourseLayout data, Action<string> status)
        {
            course = view;
            layout = data;
            report = status;
            var sphere = course.Ball.GetComponentInChildren<SphereCollider>();
            sphere.contactOffset = .001f;
            ballMaterial = new PhysicsMaterial("Putt ball")
            {
                dynamicFriction = .22f, staticFriction = .28f, bounciness = .08f,
                frictionCombine = PhysicsMaterialCombine.Minimum
            };
            sphere.sharedMaterial = ballMaterial;
            body = course.Ball.gameObject.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.linearDamping = 1.4f;
            body.angularDamping = .6f;
            body.maxAngularVelocity = 180;
            body.maxDepenetrationVelocity = 1f;
            guide = Line("Aim", new Color32(87, 146, 154, 255), .0015f);
            power = Line("Power", CourseView.Lime, .003f);
        }

        public void ResetRound()
        {
            CancelAim();
            Stop();
            Holed = false;
            strokes = 0;
            course.Ball.gameObject.SetActive(true);
            Move(course.transform.TransformPoint(course.Tee) + course.transform.up * (Radius + .001f));
        }

        public void Stop()
        {
            if (Rolling)
            {
                Freeze();
                Move(course.transform.TransformPoint(lie));
            }
        }

        public bool TryDropTarget(Ray ray, out Vector3 center)
        {
            center = default;
            if (!Immersive || Rolling || Holed || !course.TerrainCollider.Raycast(ray, out RaycastHit hit, 12))
                return false;
            Vector3 up = course.transform.up;
            float radius = Radius;
            Vector3 local = course.transform.InverseTransformPoint(hit.point);
            float clearance = (radius + .025f) / course.transform.lossyScale.x;
            Vector3 cup = course.transform.TransformPoint(course.Cup);
            if (Vector3.ProjectOnPlane(hit.point - BallCenter, up).sqrMagnitude > DropReach * DropReach ||
                Vector3.ProjectOnPlane(hit.point - cup, up).sqrMagnitude < .15f * .15f ||
                Vector3.Dot(hit.normal, up) < .87f ||
                Mathf.Abs(local.x) > layout.terrain.width_m / 2 - clearance ||
                Mathf.Abs(local.z) > layout.terrain.length_m / 2 - clearance)
                return false;
            center = hit.point + up * (radius + .001f);
            int count = Physics.OverlapSphereNonAlloc(center, radius + .025f, dropOverlaps,
                Physics.DefaultRaycastLayers, QueryTriggerInteraction.Collide);
            if (count == dropOverlaps.Length)
                return false;
            for (int i = 0; i < count; i++)
            {
                Collider other = dropOverlaps[i];
                if (other != course.TerrainCollider && other.transform.IsChildOf(course.transform) &&
                    !other.transform.IsChildOf(course.Ball))
                    return false;
            }
            return true;
        }

        public void Drop(Vector3 center)
        {
            CancelAim();
            Move(center);
            strokes++;
            report($"Ball dropped · +1 stroke · {StrokeLabel}");
            BallRested?.Invoke(this);
        }

        public bool TryAim(Ray ray, RaycastHit hit)
        {
            if (Rolling || Holed)
                return false;
            Vector3 center = body.position;
            float depth = Vector3.Dot(center - ray.origin, ray.direction);
            float tolerance = Radius + .016f;
            if (depth <= 0 || depth > 5 || (ray.GetPoint(depth) - center).sqrMagnitude > tolerance * tolerance)
                return false;
            if (hit.collider && !hit.transform.IsChildOf(course.Ball) && hit.distance < depth - tolerance)
                return false;
            aim = course.PuttHeading(center);
            chargeStarted = Time.unscaledTime;
            Aiming = true;
            UpdateAim(ray);
            return true;
        }

        public void UpdateAim(Ray ray)
        {
            Vector3 center = body.position;
            Vector3 up = course.transform.up;
            var plane = new Plane(up, center);
            if (plane.Raycast(ray, out float distance) && distance < 5)
            {
                Vector3 direction = ray.GetPoint(distance) - center;
                if (direction.sqrMagnitude > Mathf.Pow(Radius + .008f, 2))
                    aim = direction.normalized;
            }
            Vector3 start = center + up * (Radius + .003f);
            float length = Immersive ? .85f : .17f;
            SetLine(guide, start, start + aim * length);
            SetLine(power, start, start + aim * length * Mathf.Lerp(.07f, 1, Charge));
        }

        public void Release()
        {
            if (!Aiming)
                return;
            float speed = Mathf.Lerp(.20f, Immersive ? MaxImmersiveLaunchSpeed : 1.08f, Charge);
            CancelAim();
            Strike(aim, speed);
        }

        public void Strike(Vector3 direction, float speed)
        {
            if (Rolling || Holed)
                return;
            lie = course.transform.InverseTransformPoint(body.position);
            lastPosition = body.position;
            rollTime = restTime = 0;
            body.isKinematic = false;
            body.linearDamping = Immersive ? .65f : 1.4f;
            body.collisionDetectionMode = CollisionDetectionMode.ContinuousDynamic;
            body.linearVelocity = direction * speed;
            body.angularVelocity = Vector3.Cross(course.transform.up, direction) * (speed / Radius);
            strokes++;
            Rolling = true;
            report($"{StrokeLabel} · rolling");
        }

        public void CancelAim()
        {
            Aiming = false;
            guide.enabled = power.enabled = false;
        }

        private float Charge => Mathf.Clamp01((Time.unscaledTime - chargeStarted) / FullChargeSeconds);
        private string StrokeLabel => $"{strokes} {(strokes == 1 ? "stroke" : "strokes")}";

        private void FixedUpdate()
        {
            if (!Rolling)
                return;
            rollTime += Time.fixedDeltaTime;
            Vector3 position = body.position;
            Vector3 local = course.transform.InverseTransformPoint(position);
            float speed = body.linearVelocity.magnitude;
            Vector3 up = course.transform.up;
            Vector3 cup = course.transform.TransformPoint(course.Cup) + up * Radius;
            Vector3 step = position - lastPosition;
            float t = Mathf.Clamp01(Vector3.Dot(cup - lastPosition, step) / Mathf.Max(step.sqrMagnitude, 1e-10f));
            Vector3 cupOffset = lastPosition + t * step - cup;
            float cupRadius = Immersive ? .065f : Radius * 1.25f;
            if (speed <= (Immersive ? .65f : .28f) && Mathf.Abs(Vector3.Dot(cupOffset, up)) <= Radius &&
                Vector3.ProjectOnPlane(cupOffset, up).sqrMagnitude <= cupRadius * cupRadius)
            {
                Freeze();
                Move(cup);
                Holed = true;
                course.Ball.gameObject.SetActive(false);
                report($"Holed in {StrokeLabel}! Reset hole to play again.");
                return;
            }
            lastPosition = position;

            if (Mathf.Abs(local.x) > layout.terrain.width_m / 2 || Mathf.Abs(local.z) > layout.terrain.length_m / 2 ||
                local.y < -.08f / course.transform.lossyScale.y)
            {
                Stop();
                report($"Off the course. Back to your lie · {StrokeLabel}.");
                BallRested?.Invoke(this);
                return;
            }

            bool grounded = Physics.Raycast(position, -up, Radius + .004f, Physics.DefaultRaycastLayers,
                QueryTriggerInteraction.Ignore);
            if (grounded && speed < .045f)
                restTime += Time.fixedDeltaTime;
            else
                restTime = 0;
            if (restTime >= .18f || grounded && rollTime > 8f)
            {
                Freeze();
                report($"{StrokeLabel} · ready for the next putt");
                BallRested?.Invoke(this);
            }
        }

        private void Freeze()
        {
            Rolling = false;
            if (body.isKinematic)
                return;
            body.linearVelocity = Vector3.zero;
            body.angularVelocity = Vector3.zero;
            body.collisionDetectionMode = CollisionDetectionMode.Discrete;
            body.isKinematic = true;
        }

        private void Move(Vector3 position)
        {
            course.Ball.SetPositionAndRotation(position, course.transform.rotation);
            Physics.SyncTransforms();
        }

        private LineRenderer Line(string name, Color color, float width)
        {
            var line = CourseView.Group(name, transform).gameObject.AddComponent<LineRenderer>();
            line.positionCount = 2;
            line.widthMultiplier = width;
            line.sharedMaterial = course.Paint(color);
            line.enabled = false;
            return line;
        }

        private static void SetLine(LineRenderer line, Vector3 from, Vector3 to)
        {
            line.SetPosition(0, from);
            line.SetPosition(1, to);
            line.enabled = true;
        }

        private void OnDestroy()
        {
            if (ballMaterial)
                Destroy(ballMaterial);
        }
    }
}
