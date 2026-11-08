"""Frame format shared with embedded/src/protocol.h."""

from __future__ import annotations

import struct
from dataclasses import dataclass
from typing import Union

MAGIC = 0xA5
VERSION = 1
HEADER_LEN = 11
MAX_PAYLOAD = 48

SENSOR_IMU = 1
SENSOR_HALL = 2
SENSOR_SHOCK = 3
SENSOR_TAP = 4
SENSOR_ENCODER = 5
SENSOR_BUTTON = 6

SERVICE_UUID = "6f4c0001-5a1e-4b3d-9c8a-1e2f3a4b5c6d"
STREAM_UUID = "6f4c0002-5a1e-4b3d-9c8a-1e2f3a4b5c6d"
DEVICE_NAME = "HackUTD"

IMU_KIND = {1: "mpu6050", 2: "mpu6500"}


@dataclass(frozen=True)
class ImuReading:
    time_ms: int
    seq: int
    ax_g: float
    ay_g: float
    az_g: float
    gx_dps: float
    gy_dps: float
    gz_dps: float
    temp_c: float
    kind: str
    source: int
    pitch_deg: float = 0.0
    roll_deg: float = 0.0
    yaw_deg: float = 0.0
    has_angles: bool = False

    @property
    def sensor_id(self) -> int:
        return SENSOR_IMU


@dataclass(frozen=True)
class UnknownReading:
    """A frame the host does not have a decoder for yet."""

    sensor_id: int
    time_ms: int
    seq: int
    payload: bytes


Reading = Union[ImuReading, UnknownReading]


def checksum(data: bytes) -> int:
    return sum(data) & 0xFF


def encode_frame(sensor_id: int, seq: int, time_ms: int, payload: bytes, flags: int = 0) -> bytes:
    if len(payload) > MAX_PAYLOAD:
        raise ValueError("payload longer than 48 bytes")
    body = struct.pack(
        "<BBBBHIB",
        MAGIC,
        VERSION,
        sensor_id,
        flags,
        seq & 0xFFFF,
        time_ms & 0xFFFFFFFF,
        len(payload),
    ) + payload
    return body + bytes((checksum(body),))


def _decode_imu(time_ms: int, seq: int, payload: bytes) -> ImuReading:
    if len(payload) < 16:
        raise ValueError("imu payload must be at least 16 bytes")
    ax, ay, az, gx, gy, gz, temp, kind, source = struct.unpack_from("<hhhhhhhBB", payload)
    pitch = roll = yaw = 0.0
    has_angles = len(payload) >= 22
    if has_angles:
        pitch, roll, yaw = struct.unpack_from("<hhh", payload, 16)
        pitch /= 10.0
        roll /= 10.0
        yaw /= 10.0
    return ImuReading(
        time_ms=time_ms,
        seq=seq,
        ax_g=ax / 1000.0,
        ay_g=ay / 1000.0,
        az_g=az / 1000.0,
        gx_dps=gx / 10.0,
        gy_dps=gy / 10.0,
        gz_dps=gz / 10.0,
        temp_c=temp / 100.0,
        kind=IMU_KIND.get(kind, f"0x{kind:02x}"),
        source=source,
        pitch_deg=pitch,
        roll_deg=roll,
        yaw_deg=yaw,
        has_angles=has_angles,
    )


DECODERS = {
    SENSOR_IMU: _decode_imu,
}


def decode_frame(frame: bytes) -> Reading:
    sensor_id = frame[2]
    seq = struct.unpack_from("<H", frame, 4)[0]
    time_ms = struct.unpack_from("<I", frame, 6)[0]
    payload = bytes(frame[HEADER_LEN:-1])
    decoder = DECODERS.get(sensor_id)
    if decoder is None:
        return UnknownReading(sensor_id, time_ms, seq, payload)
    try:
        return decoder(time_ms, seq, payload)
    except ValueError:
        return UnknownReading(sensor_id, time_ms, seq, payload)


class FrameParser:
    """Reassembles notification chunks into frames and resyncs after damage."""

    def __init__(self) -> None:
        self.buf = bytearray()
        self.checksum_errors = 0

    def feed(self, data: bytes) -> list[Reading]:
        self.buf.extend(data)
        readings: list[Reading] = []
        while self.buf:
            if len(self.buf) > 512:
                del self.buf[:-64]
            if self.buf[0] != MAGIC:
                del self.buf[0]
                continue
            if len(self.buf) < HEADER_LEN:
                break
            if self.buf[1] != VERSION:
                del self.buf[0]
                continue
            payload_len = self.buf[10]
            if payload_len > MAX_PAYLOAD:
                del self.buf[0]
                continue
            total = HEADER_LEN + payload_len + 1
            if len(self.buf) < total:
                break
            frame = bytes(self.buf[:total])
            if checksum(frame[:-1]) != frame[-1]:
                self.checksum_errors += 1
                del self.buf[0]
                continue
            del self.buf[:total]
            readings.append(decode_frame(frame))
        return readings


def _self_test() -> None:
    payload = struct.pack("<hhhhhhhBB", 630, 460, -630, 20, -6, -4, 3020, 2, 0)
    frame = encode_frame(SENSOR_IMU, 7, 1500, payload)
    parser = FrameParser()
    # Split the frame the way a 20-byte notification would.
    parts = [frame[:20], frame[20:]]
    got = []
    for part in parts:
        got.extend(parser.feed(part))
    assert len(got) == 1, got
    reading = got[0]
    assert isinstance(reading, ImuReading)
    assert reading.seq == 7
    assert reading.time_ms == 1500
    assert reading.ax_g == 0.63
    assert reading.az_g == -0.63
    assert reading.gx_dps == 2.0
    assert reading.gy_dps == -0.6
    assert reading.temp_c == 30.2
    assert reading.kind == "mpu6500"
    assert reading.source == 0

    junk = b"\x00\x01" + frame + b"\xa5\x01garbage"
    parsed = parser.feed(junk)
    assert len(parsed) == 1 and parsed[0].seq == 7

    hall = encode_frame(SENSOR_HALL, 1, 10, b"\x01\x02")
    unknown = parser.feed(hall)
    assert isinstance(unknown[0], UnknownReading)
    assert unknown[0].sensor_id == SENSOR_HALL
    assert unknown[0].payload == b"\x01\x02"
    print("protocol ok")


if __name__ == "__main__":
    _self_test()
