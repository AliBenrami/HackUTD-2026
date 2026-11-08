package com.golfar.clubble;

final class ClubFrames {
    // V1 stream from embedded/src/protocol.h. Notification boundaries are arbitrary.
    private static final int HEADER = 11;
    private static final int MAX_PAYLOAD = 48;
    private final byte[] frame = new byte[HEADER + MAX_PAYLOAD + 1];
    private int size;

    interface Sample {
        void motion(float x, float y, float z, int timeMs);
    }

    void reset() {
        size = 0;
    }

    void feed(byte[] chunk, Sample sample) {
        for (byte value : chunk) {
            frame[size++] = value;
            parse(sample);
        }
    }

    private void parse(Sample sample) {
        while (size > 0) {
            if (unsigned(0) != 0xA5 || (size >= 2 && unsigned(1) != 1)) {
                discard(1);
                continue;
            }
            if (size < HEADER)
                return;
            int payload = unsigned(10);
            if (payload > MAX_PAYLOAD) {
                discard(1);
                continue;
            }
            int total = HEADER + payload + 1;
            if (size < total)
                return;
            int sum = 0;
            for (int i = 0; i < total - 1; i++)
                sum += unsigned(i);
            if ((sum & 255) != unsigned(total - 1)) {
                discard(1);
                continue;
            }
            if (unsigned(2) == 1 && payload >= 16) {
                float x = readShort(HEADER + 6) * .1f;
                float y = readShort(HEADER + 8) * .1f;
                float z = readShort(HEADER + 10) * .1f;
                int timeMs = unsigned(6) | (unsigned(7) << 8) | (unsigned(8) << 16) | (unsigned(9) << 24);
                sample.motion(x, y, z, timeMs);
            }
            discard(total);
        }
    }

    private int unsigned(int index) {
        return frame[index] & 255;
    }

    private short readShort(int index) {
        return (short)(unsigned(index) | (unsigned(index + 1) << 8));
    }

    private void discard(int count) {
        size -= count;
        System.arraycopy(frame, count, frame, 0, size);
    }
}
