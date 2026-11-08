#pragma once

#include <stdint.h>

// Binary frames carried in BLE notifications. The Python side in host/protocol.py
// reads the same layout. A notification may contain part of a frame, one frame,
// or several frames. The host stitches the bytes back together.
//
//   0      magic          0xA5
//   1      version        1
//   2      sensor_id
//   3      flags          0 for now
//   4..5   sequence       uint16 little-endian, per connection
//   6..9   time_ms        uint32 little-endian, device millis()
//   10     payload_len
//   11     payload
//   last   checksum       low 8 bits of the sum of every preceding byte
//
// IMU payload, sensor_id 1, 16 bytes, all little-endian:
//   int16 ax_mg, ay_mg, az_mg
//   int16 gx_dps10, gy_dps10, gz_dps10   (tenths of a degree per second)
//   int16 temp_c100                      (hundredths of a degree C)
//   uint8 kind                           (1 = MPU-6050, 2 = MPU-6500)
//   uint8 source                         (0 = first device, 1 = second)

static constexpr uint8_t kFrameMagic = 0xA5;
static constexpr uint8_t kFrameVersion = 1;
static constexpr uint8_t kFrameHeaderLen = 11;
static constexpr uint8_t kMaxPayload = 48;

enum SensorId : uint8_t {
  SENSOR_IMU = 1,
  SENSOR_HALL = 2,
  SENSOR_SHOCK = 3,
  SENSOR_TAP = 4,
  SENSOR_ENCODER = 5,
  SENSOR_BUTTON = 6,
};
