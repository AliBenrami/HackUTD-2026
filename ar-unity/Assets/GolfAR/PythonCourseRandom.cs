using System;

namespace GolfAR
{
    // Match Python 3.12 random.Random for the signed 32-bit course seed.
    // MT19937 initialization and tempering are credited in ThirdPartyNotices.md.
    internal sealed class PythonCourseRandom
    {
        private const int Size = 624;
        private const int PeriodOffset = 397;
        private readonly uint[] state = new uint[Size];
        private int index = Size;

        public PythonCourseRandom(int seed)
        {
            unchecked
            {
                uint key = (uint)Math.Abs((long)seed);
                state[0] = 19650218;
                for (int i = 1; i < Size; i++)
                    state[i] = 1812433253u * Fold(state[i - 1]) + (uint)i;

                int position = 1;
                for (int i = 0; i < Size; i++)
                {
                    state[position] = (state[position] ^ (1664525u * Fold(state[position - 1]))) + key;
                    position = AdvanceSeed(position);
                }
                for (int i = 0; i < Size - 1; i++)
                {
                    state[position] = (state[position] ^ (1566083941u * Fold(state[position - 1]))) - (uint)position;
                    position = AdvanceSeed(position);
                }
                state[0] = 0x80000000u;
            }
        }

        private static uint Fold(uint value) => value ^ (value >> 30);

        private int AdvanceSeed(int position)
        {
            if (position + 1 < Size)
                return position + 1;
            state[0] = state[^1];
            return 1;
        }

        private uint NextWord()
        {
            if (index == Size)
            {
                for (int i = 0; i < Size; i++)
                {
                    uint combined = (state[i] & 0x80000000u) | (state[(i + 1) % Size] & 0x7fffffffu);
                    state[i] = state[(i + PeriodOffset) % Size] ^ (combined >> 1) ^
                        ((combined & 1) == 0 ? 0u : 0x9908b0dfu);
                }
                index = 0;
            }
            uint word = state[index++];
            word ^= word >> 11;
            word ^= (word << 7) & 0x9d2c5680u;
            word ^= (word << 15) & 0xefc60000u;
            return word ^ (word >> 18);
        }

        public double Range(double low, double high)
        {
            double unit = ((NextWord() >> 5) * 67108864.0 + (NextWord() >> 6)) / 9007199254740992.0;
            return low + (high - low) * unit;
        }

        public int Index(int count)
        {
            int bits = 0;
            for (int remaining = count; remaining > 0; remaining >>= 1)
                bits++;
            uint value;
            do
            {
                value = NextWord() >> (32 - bits);
            } while (value >= count);
            return (int)value;
        }
    }
}
