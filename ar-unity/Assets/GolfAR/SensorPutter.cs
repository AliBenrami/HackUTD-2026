using UnityEngine;

namespace GolfAR
{
    // A fixed address pivot supplies the spatial reference that an IMU alone
    // cannot measure. A taught backswing fixes the axis for the current mount.
    internal sealed class SensorPutter
    {
        public const float LeverMeters = .65f;
        private const float QuietDegreesPerSecond = 4;
        private const float MaxAddressBias = 12;
        private const float AddressRateVariation = 2.5f;
        private const float MinBackswingDegrees = 6.5f;
        private const float AxisLockDegrees = 2.75f;
        private const float ContactDegrees = 1.75f;
        private const float MinReturnRate = 12f;
        private const float MaxSampleGap = .12f;
        private Vector3 zero, axis, bias, addressRate;
        private Vector3 learnedAxis, lastInferredAxis;
        private float quietTime, previousAngle, previousSeconds, zeroSeconds, pauseTime, peakAngle, returnSpeed;
        private bool backedUp, hasSample, canceled;
        public bool Addressed { get; private set; }
        public bool Canceled => canceled;
        public bool Backswing => backedUp && !canceled;
        public float Angle { get; private set; }
        public Vector3 SwingDirection => learnedAxis;

        public void LearnBackswing(Vector3 direction)
        {
            learnedAxis = direction.normalized;
            Reset();
        }

        public bool FlipBackswing()
        {
            Vector3 direction = learnedAxis == Vector3.zero ? lastInferredAxis : learnedAxis;
            if (direction == Vector3.zero)
                return false;
            LearnBackswing(-direction);
            return true;
        }

        public void Reset()
        {
            Addressed = false;
            quietTime = previousAngle = previousSeconds = Angle = zeroSeconds = pauseTime = peakAngle = 0;
            returnSpeed = 0;
            axis = Vector3.zero;
            bias = Vector3.zero;
            backedUp = hasSample = canceled = false;
        }

        public float Update(ClubLink.Motion sample)
        {
            float dt = hasSample ? sample.Seconds - previousSeconds : 0;
            if (hasSample && dt == 0)
                return 0;
            if (dt < 0 || dt > MaxSampleGap)
            {
                Reset();
                dt = 0;
            }
            hasSample = true;
            previousSeconds = sample.Seconds;
            Vector3 correctedRate = sample.Rate - bias;
            bool quiet = correctedRate.sqrMagnitude < QuietDegreesPerSecond * QuietDegreesPerSecond;
            if (!Addressed)
            {
                bool stable = sample.Rate.sqrMagnitude <= MaxAddressBias * MaxAddressBias &&
                    (sample.Rate - addressRate).sqrMagnitude <= AddressRateVariation * AddressRateVariation;
                if (quietTime == 0 || !stable)
                {
                    addressRate = sample.Rate;
                    bias = sample.Rate;
                }
                quietTime = stable ? quietTime + dt : 0;
                TrackAddress(sample, dt);
                if (quietTime >= .45f)
                    Addressed = true;
                return 0;
            }

            Vector3 delta = sample.Angle - zero - bias * (sample.Seconds - zeroSeconds);
            if (axis == Vector3.zero)
            {
                if (quiet)
                    TrackAddress(sample, dt);
                else if (learnedAxis == Vector3.zero)
                {
                    if (delta.sqrMagnitude >= 5 * 5)
                        lastInferredAxis = axis = delta.normalized;
                }
                else if (Mathf.Abs(Vector3.Dot(delta, learnedAxis)) >= AxisLockDegrees)
                    axis = learnedAxis;
                if (axis == Vector3.zero)
                    return 0;
            }

            float angle = Vector3.Dot(delta, axis);
            float rate = Vector3.Dot(correctedRate, axis);
            // Use measured gyro speed near contact so a timestamp jump or a
            // slow settling movement cannot supply the launch force.
            if (angle < previousAngle && rate < 0)
                returnSpeed = Mathf.Max(-rate, returnSpeed * Mathf.Exp(-dt / .065f));
            else
                returnSpeed = 0;
            bool paused = correctedRate.sqrMagnitude < 3 * 3;
            pauseTime = paused ? pauseTime + dt : 0;
            Angle = Mathf.Clamp(angle, -25, 75);
            peakAngle = Mathf.Max(peakAngle, angle);
            backedUp = peakAngle >= MinBackswingDegrees;
            // A long hold cancels the shot while retaining the original address.
            canceled |= backedUp && pauseTime >= 3f;
            if (Backswing && previousAngle > ContactDegrees && angle <= ContactDegrees && returnSpeed >= MinReturnRate)
            {
                float speed = returnSpeed * Mathf.Deg2Rad * LeverMeters;
                Reset();
                return speed;
            }
            previousAngle = angle;
            if (paused && (Mathf.Abs(angle) <= ContactDegrees ||
                !backedUp && pauseTime >= .2f && (learnedAxis == Vector3.zero || angle > 0)))
            {
                TrackAddress(sample, dt);
                axis = Vector3.zero;
                backedUp = canceled = false;
                previousAngle = Angle = pauseTime = peakAngle = returnSpeed = 0;
            }
            return 0;
        }

        private void TrackAddress(ClubLink.Motion sample, float dt)
        {
            zero = sample.Angle;
            zeroSeconds = sample.Seconds;
            bias = Vector3.Lerp(bias, sample.Rate, 1 - Mathf.Exp(-12 * dt));
        }
    }
}
