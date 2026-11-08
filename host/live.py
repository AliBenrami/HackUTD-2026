"""Print the live sensor stream. Run from the repo root: python -m host"""

from __future__ import annotations

import argparse
import asyncio
import sys

from host.link import SensorLink
from host.protocol import DEVICE_NAME, ImuReading, UnknownReading


def format_reading(reading) -> str:
    if isinstance(reading, ImuReading):
        return (
            f"imu src={reading.source} seq={reading.seq} t={reading.time_ms}  "
            f"accel {reading.ax_g:6.2f} {reading.ay_g:6.2f} {reading.az_g:6.2f} g   "
            f"gyro {reading.gx_dps:7.1f} {reading.gy_dps:7.1f} {reading.gz_dps:7.1f} dps   "
            f"angle {reading.pitch_deg:6.1f} {reading.roll_deg:6.1f} {reading.yaw_deg:6.1f}   "
            f"{reading.temp_c:4.1f} C  {reading.kind}"
        )
    if isinstance(reading, UnknownReading):
        return (
            f"sensor {reading.sensor_id} seq={reading.seq} t={reading.time_ms}  "
            f"{reading.payload.hex()}"
        )
    return str(reading)


async def run(name: str) -> None:
    link = SensorLink(name=name)
    last_seq: dict[int, int] = {}
    async for reading in link.readings():
        sensor_id = reading.sensor_id
        previous = last_seq.get(sensor_id)
        if previous is not None and reading.seq != (previous + 1) & 0xFFFF:
            missed = (reading.seq - previous - 1) & 0xFFFF
            print(f"gap on sensor {sensor_id}: missed {missed}", file=sys.stderr)
        last_seq[sensor_id] = reading.seq
        print(format_reading(reading), flush=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Print live ESP32 sensor readings over BLE")
    parser.add_argument("--name", default=DEVICE_NAME, help="advertised BLE name")
    args = parser.parse_args()
    try:
        asyncio.run(run(args.name))
    except KeyboardInterrupt:
        print("\nstopped", file=sys.stderr)


if __name__ == "__main__":
    main()
