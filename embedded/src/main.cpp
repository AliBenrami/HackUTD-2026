#include <Arduino.h>
#include <BLE2902.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <TFT_eSPI.h>
#include <Wire.h>
#include <math.h>
#include <stdio.h>
#include <string.h>

#include "protocol.h"

// Onboard 4.0" ST7796, same init and pins as Kori (TFT_eSPI User_Setup.h).
// GY-521 on this board's I2C socket. GPIO 21 and 22 are not that socket:
// 22 drives the red LED, and 21 is the spare SPI chip select.
//   VCC -> 3V3
//   GND -> GND
//   SDA -> GPIO 32
//   SCL -> GPIO 25
//   AD0 -> GND (address 0x68) or 3V3 (address 0x69)
constexpr int kScreenW = 480;
constexpr int kScreenH = 320;
constexpr int kPlotX = 10;
constexpr int kPlotY = 44;
constexpr int kPlotW = 156;
constexpr int kPlotH = 228;
constexpr int kPanelX = 174;
constexpr int kPanelY = 44;
constexpr int kPanelW = 296;
constexpr int kPanelH = 228;
constexpr uint32_t kI2cHz = 100000;
constexpr uint32_t kSamplePeriodMs = 5;  // 200 Hz
constexpr uint32_t kPublishPeriodMs = 10;
constexpr uint32_t kNotifyPeriodMs = 15;
constexpr uint32_t kLogPeriodMs = 1000;
constexpr uint32_t kDisplayPeriodMs = 100;

constexpr char kDeviceName[] = "HackUTD";
constexpr char kServiceUuid[] = "6f4c0001-5a1e-4b3d-9c8a-1e2f3a4b5c6d";
constexpr char kStreamUuid[] = "6f4c0002-5a1e-4b3d-9c8a-1e2f3a4b5c6d";

constexpr uint8_t kRegSampleRate = 0x19;
constexpr uint8_t kRegConfig = 0x1A;
constexpr uint8_t kRegGyroConfig = 0x1B;
constexpr uint8_t kRegAccelConfig = 0x1C;
constexpr uint8_t kRegAccelXOutH = 0x3B;
constexpr uint8_t kRegPwrMgmt1 = 0x6B;
constexpr uint8_t kRegWhoAmI = 0x75;

constexpr float kAccelLsbPerG = 2048.0f;  // ±16 g
constexpr float kGyroLsbPerDps = 16.4f;   // ±2000 deg/s
constexpr size_t kTxCapacity = 256;
constexpr size_t kImuPayloadLen = 22;

enum class ImuKind : uint8_t { Mpu6050 = 1, Mpu6500 = 2 };

struct ImuSample {
  float ax;
  float ay;
  float az;
  float gx;
  float gy;
  float gz;
  float tempC;
  ImuKind kind;
};

TFT_eSPI tft;
TFT_eSprite plot(&tft);
bool plotReady = false;
uint16_t colInk = 0;
uint16_t colPanel = 0;
uint16_t colRaised = 0;
uint16_t colLine = 0;
uint16_t colCyan = 0;
uint16_t colViolet = 0;
uint16_t colMagenta = 0;
uint16_t colMist = 0;
uint16_t colSlate = 0;
BLEServer *bleServer = nullptr;
BLECharacteristic *streamChar = nullptr;
volatile bool clientConnected = false;
volatile bool resetTx = false;
#if defined(CONFIG_BLUEDROID_ENABLED)
volatile bool notificationsEnabled = false;
#else
constexpr bool notificationsEnabled = true;
#endif
bool notifySent = false;

uint8_t txBuf[kTxCapacity];
size_t txLen = 0;
uint32_t droppedFrames = 0;
uint32_t notifyErrors = 0;
uint16_t sequence = 0;
ImuKind imuKind = ImuKind::Mpu6050;
bool imuReady = false;
int sdaPin = 32;
int sclPin = 25;
uint8_t mpuAddress = 0x68;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    (void)server;
    clientConnected = true;
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    clientConnected = false;
#if defined(CONFIG_BLUEDROID_ENABLED)
    notificationsEnabled = false;
#endif
    resetTx = true;
  }
#if defined(CONFIG_BLUEDROID_ENABLED)
  void onDisconnect(BLEServer *, esp_ble_gatts_cb_param_t *param) override {
    Serial.printf("BLE disconnect reason 0x%02X\n", static_cast<unsigned>(param->disconnect.reason));
  }
#endif
};

#if defined(CONFIG_BLUEDROID_ENABLED)
class SubscriptionCallbacks : public BLEDescriptorCallbacks {
  void onWrite(BLEDescriptor *descriptor) override {
    notificationsEnabled = static_cast<BLE2902 *>(descriptor)->getNotifications();
    if (!notificationsEnabled) {
      resetTx = true;
    }
  }
};
#endif

class StreamCallbacks : public BLECharacteristicCallbacks {
  void onStatus(BLECharacteristic *, Status status, uint32_t) override {
    notifySent = status == Status::SUCCESS_NOTIFY;
  }
};

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegs(uint8_t reg, uint8_t *buf, size_t len) {
  Wire.beginTransmission(mpuAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(mpuAddress, static_cast<uint8_t>(len)) != len) {
    return false;
  }
  for (size_t i = 0; i < len; ++i) {
    buf[i] = Wire.read();
  }
  return true;
}

int16_t readBe16(const uint8_t *bytes) {
  return static_cast<int16_t>((bytes[0] << 8) | bytes[1]);
}

int16_t clampI16(float value) {
  if (value >= 0.0f) {
    value += 0.5f;
  } else {
    value -= 0.5f;
  }
  if (value > 32767.0f) {
    return 32767;
  }
  if (value < -32768.0f) {
    return -32768;
  }
  return static_cast<int16_t>(value);
}

void writeI16(uint8_t *out, int16_t value) {
  out[0] = static_cast<uint8_t>(value & 0xFF);
  out[1] = static_cast<uint8_t>((value >> 8) & 0xFF);
}

bool beginMpu() {
  uint8_t who = 0;
  if (!readRegs(kRegWhoAmI, &who, 1)) {
    return false;
  }
  if (who == 0x68) {
    imuKind = ImuKind::Mpu6050;
    Serial.println("found MPU-6050");
  } else if (who == 0x70) {
    imuKind = ImuKind::Mpu6500;
    Serial.println("found MPU-6500 on a GY-521 board");
  } else {
    Serial.printf("unexpected whoami 0x%02X\n", who);
    return false;
  }

  if (!writeReg(kRegPwrMgmt1, 0x00)) {
    return false;
  }
  delay(50);
  return writeReg(kRegSampleRate, 4) &&  // 200 Hz from the 1 kHz gyro clock
         writeReg(kRegConfig, 0x01) &&
         writeReg(kRegGyroConfig, 0x18) &&  // ±2000 deg/s
         writeReg(kRegAccelConfig, 0x18);   // ±16 g
}

bool readImu(ImuSample *sample) {
  uint8_t raw[14];
  if (!readRegs(kRegAccelXOutH, raw, sizeof(raw))) {
    return false;
  }
  sample->ax = readBe16(raw + 0) / kAccelLsbPerG;
  sample->ay = readBe16(raw + 2) / kAccelLsbPerG;
  sample->az = readBe16(raw + 4) / kAccelLsbPerG;
  const int16_t tempRaw = readBe16(raw + 6);
  sample->tempC = imuKind == ImuKind::Mpu6500 ? tempRaw / 333.87f + 21.0f
                                              : tempRaw / 340.0f + 36.53f;
  sample->gx = readBe16(raw + 8) / kGyroLsbPerDps;
  sample->gy = readBe16(raw + 10) / kGyroLsbPerDps;
  sample->gz = readBe16(raw + 12) / kGyroLsbPerDps;
  sample->kind = imuKind;
  return true;
}

struct Quat {
  float w;
  float x;
  float y;
  float z;
};

Quat pose = {1, 0, 0, 0};
Quat addressPose = {1, 0, 0, 0};
float clubPitch = 0;
float clubRoll = 0;
float clubYaw = 0;
float clubSwing = 0;
bool addressLocked = false;
float viewPitch = 0;
float viewRoll = 0;
uint32_t lastPoseMs = 0;
uint32_t stillSinceMs = 0;
bool holdingStill = false;
bool capturedThisHold = false;

Quat quatMul(Quat a, Quat b) {
  return {
      a.w * b.w - a.x * b.x - a.y * b.y - a.z * b.z,
      a.w * b.x + a.x * b.w + a.y * b.z - a.z * b.y,
      a.w * b.y - a.x * b.z + a.y * b.w + a.z * b.x,
      a.w * b.z + a.x * b.y - a.y * b.x + a.z * b.w,
  };
}

void normalizeQuat(Quat &v) {
  const float n = sqrtf(v.w * v.w + v.x * v.x + v.y * v.y + v.z * v.z);
  if (n < 1e-6f) {
    v = {1, 0, 0, 0};
    return;
  }
  v.w /= n;
  v.x /= n;
  v.y /= n;
  v.z /= n;
}

void eulerDegrees(Quat v, float &pitch, float &roll, float &yaw) {
  float sinPitch = 2.0f * (v.w * v.y - v.z * v.x);
  if (sinPitch > 1.0f) {
    sinPitch = 1.0f;
  } else if (sinPitch < -1.0f) {
    sinPitch = -1.0f;
  }
  constexpr float kRadToDeg = 57.2957795f;
  pitch = asinf(sinPitch) * kRadToDeg;
  roll = atan2f(2.0f * (v.w * v.x + v.y * v.z),
                1.0f - 2.0f * (v.x * v.x + v.y * v.y)) *
         kRadToDeg;
  yaw = atan2f(2.0f * (v.w * v.z + v.x * v.y),
               1.0f - 2.0f * (v.y * v.y + v.z * v.z)) *
        kRadToDeg;
}

// Pitch, roll, and yaw in degrees from the pose where the club was held still.
// Gravity corrects tilt only while the head is quiet. During the swing the
// gyro carries the angle, because the swing's acceleration swamps gravity.
void updateClubAngle(const ImuSample &sample, uint32_t now) {
  float dt = 0.005f;
  if (lastPoseMs != 0 && now > lastPoseMs) {
    dt = (now - lastPoseMs) / 1000.0f;
  }
  lastPoseMs = now;
  if (dt < 0.001f) {
    dt = 0.001f;
  } else if (dt > 0.05f) {
    dt = 0.05f;
  }

  constexpr float kDegToRad = 0.01745329252f;
  float wx = sample.gx * kDegToRad;
  float wy = sample.gy * kDegToRad;
  float wz = sample.gz * kDegToRad;
  const float amag = sqrtf(sample.ax * sample.ax + sample.ay * sample.ay + sample.az * sample.az);
  const float gmag = sqrtf(sample.gx * sample.gx + sample.gy * sample.gy + sample.gz * sample.gz);
  const bool gravityPlausible = amag > 0.85f && amag < 1.15f;
  const bool quiet = gravityPlausible && gmag < 6.0f;
  if (gravityPlausible && gmag < 15.0f) {
    const float inv = 1.0f / amag;
    const float axn = sample.ax * inv;
    const float ayn = sample.ay * inv;
    const float azn = sample.az * inv;
    const float vx = 2.0f * (pose.x * pose.z - pose.w * pose.y);
    const float vy = 2.0f * (pose.w * pose.x + pose.y * pose.z);
    const float vz = pose.w * pose.w - pose.x * pose.x - pose.y * pose.y + pose.z * pose.z;
    const float ex = ayn * vz - azn * vy;
    const float ey = azn * vx - axn * vz;
    const float ez = axn * vy - ayn * vx;
    constexpr float kTiltGain = 2.0f;
    wx += kTiltGain * ex;
    wy += kTiltGain * ey;
    wz += kTiltGain * ez;
  }

  pose = quatMul(pose, {1.0f, wx * dt * 0.5f, wy * dt * 0.5f, wz * dt * 0.5f});
  normalizeQuat(pose);

  static float swingX = 0;
  static float swingY = 0;
  static float swingZ = 0;
  if (quiet) {
    if (!holdingStill) {
      holdingStill = true;
      stillSinceMs = now;
      capturedThisHold = false;
    } else if (!capturedThisHold && now - stillSinceMs >= (addressLocked ? 2500u : 400u)) {
      addressPose = pose;
      addressLocked = true;
      capturedThisHold = true;
      swingX = swingY = swingZ = 0;
    }
  } else {
    holdingStill = false;
  }

  const Quat fromAddress = quatMul(
      {addressPose.w, -addressPose.x, -addressPose.y, -addressPose.z}, pose);
  eulerDegrees(fromAddress, clubPitch, clubRoll, clubYaw);

  // Draw the shaft along the observed swing axis instead of assuming the
  // module is mounted so its pitch axis always matches the swing.
  const float sign = fromAddress.w < 0 ? -1.0f : 1.0f;
  const float length = sqrtf(fromAddress.x * fromAddress.x + fromAddress.y * fromAddress.y +
                             fromAddress.z * fromAddress.z);
  const float angle = 114.59156f * atan2f(length, fabsf(fromAddress.w));
  if (quiet && angle < 2.0f) {
    swingX = swingY = swingZ = 0;
  } else if (angle >= 3.0f && swingX == 0 && swingY == 0 && swingZ == 0) {
    swingX = sign * fromAddress.x / length;
    swingY = sign * fromAddress.y / length;
    swingZ = sign * fromAddress.z / length;
  }
  clubSwing = length > 1e-6f ?
      sign * angle * (fromAddress.x * swingX + fromAddress.y * swingY + fromAddress.z * swingZ) / length : 0;
}

bool publish(uint8_t sensorId, const uint8_t *payload, uint8_t payloadLen) {
  if (payloadLen > kMaxPayload) {
    return false;
  }
  const size_t frameLen = kFrameHeaderLen + payloadLen + 1;
  if (txLen + frameLen > kTxCapacity) {
    ++droppedFrames;
    return false;
  }

  uint8_t *frame = txBuf + txLen;
  frame[0] = kFrameMagic;
  frame[1] = kFrameVersion;
  frame[2] = sensorId;
  frame[3] = 0;
  frame[4] = static_cast<uint8_t>(sequence & 0xFF);
  frame[5] = static_cast<uint8_t>((sequence >> 8) & 0xFF);
  const uint32_t timeMs = millis();
  frame[6] = static_cast<uint8_t>(timeMs & 0xFF);
  frame[7] = static_cast<uint8_t>((timeMs >> 8) & 0xFF);
  frame[8] = static_cast<uint8_t>((timeMs >> 16) & 0xFF);
  frame[9] = static_cast<uint8_t>((timeMs >> 24) & 0xFF);
  frame[10] = payloadLen;
  memcpy(frame + kFrameHeaderLen, payload, payloadLen);

  uint8_t sum = 0;
  for (size_t i = 0; i < frameLen - 1; ++i) {
    sum = static_cast<uint8_t>(sum + frame[i]);
  }
  frame[frameLen - 1] = sum;
  txLen += frameLen;
  ++sequence;
  return true;
}

void publishImu(const ImuSample &sample) {
  uint8_t payload[kImuPayloadLen];
  writeI16(payload + 0, clampI16(sample.ax * 1000.0f));
  writeI16(payload + 2, clampI16(sample.ay * 1000.0f));
  writeI16(payload + 4, clampI16(sample.az * 1000.0f));
  writeI16(payload + 6, clampI16(sample.gx * 10.0f));
  writeI16(payload + 8, clampI16(sample.gy * 10.0f));
  writeI16(payload + 10, clampI16(sample.gz * 10.0f));
  writeI16(payload + 12, clampI16(sample.tempC * 100.0f));
  payload[14] = static_cast<uint8_t>(sample.kind);
  payload[15] = 0;
  writeI16(payload + 16, clampI16(clubPitch * 10.0f));
  writeI16(payload + 18, clampI16(clubRoll * 10.0f));
  writeI16(payload + 20, clampI16(clubYaw * 10.0f));
  publish(SENSOR_IMU, payload, kImuPayloadLen);
}

size_t notifyLimit() {
  uint16_t mtu = 23;
  if (bleServer != nullptr) {
    const uint16_t peer = bleServer->getPeerMTU(bleServer->getConnId());
    if (peer >= 23) {
      mtu = peer;
    }
  }
  return static_cast<size_t>(mtu - 3);
}

void flushTx() {
  if (!clientConnected || !notificationsEnabled || streamChar == nullptr || txLen == 0) {
    return;
  }
  for (int burst = 0; burst < 4 && clientConnected && notificationsEnabled && txLen > 0; ++burst) {
    size_t chunk = notifyLimit();
    if (chunk == 0) {
      return;
    }
    if (chunk > txLen) {
      chunk = txLen;
    }
    streamChar->setValue(txBuf, chunk);
    notifySent = false;
    streamChar->notify();
    if (!notifySent) {
      ++notifyErrors;
      return;
    }
    memmove(txBuf, txBuf + chunk, txLen - chunk);
    txLen -= chunk;
  }
}

bool useBus(int sda, int scl, bool diagnose) {
  // Arduino ESP32 keeps the original pins when begin() is called on an active bus.
  Wire.end();
  sdaPin = sda;
  sclPin = scl;
  pinMode(sda, INPUT_PULLUP);
  pinMode(scl, INPUT_PULLUP);
  delay(2);
  const int idleSda = digitalRead(sda);
  const int idleScl = digitalRead(scl);
  const bool started = Wire.begin(sda, scl, kI2cHz);
  if (diagnose) {
    Serial.printf("I2C SDA %d=%s SCL %d=%s: %s\n", sda, idleSda ? "high" : "low",
                  scl, idleScl ? "high" : "low", started ? "started" : "init failed");
  }
  return started;
}

bool addressAcks(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

// This display's I2C socket is SDA 32 / SCL 25. The other pairs cover a
// swapped plug and the older 21/22 wiring.
bool probeMpu(bool diagnose = false) {
  static constexpr int kBuses[][2] = {{32, 25}, {25, 32}, {21, 22}, {22, 21}};
  static constexpr uint8_t kAddresses[] = {0x68, 0x69};
  for (const auto &bus : kBuses) {
    if (!useBus(bus[0], bus[1], diagnose)) {
      continue;
    }
    for (uint8_t addr : kAddresses) {
      if (!addressAcks(addr)) {
        continue;
      }
      mpuAddress = addr;
      Serial.printf("gyro at 0x%02X  SDA %d SCL %d\n", addr, sdaPin, sclPin);
      if (beginMpu()) {
        return true;
      }
    }
    if (diagnose && bus[0] == 32 && bus[1] == 25) {
      bool found = false;
      Serial.print("I2C socket ACKs:");
      for (uint8_t addr = 0x08; addr <= 0x77; ++addr) {
        if (addressAcks(addr)) {
          Serial.printf(" 0x%02X", addr);
          found = true;
        }
      }
      Serial.println(found ? "" : " none");
    }
  }
  Serial.println("gyro not found on SDA 32 SCL 25");
  return false;
}

void loadPalette() {
  colInk = tft.color565(8, 12, 18);
  colPanel = tft.color565(17, 25, 35);
  colRaised = tft.color565(23, 34, 50);
  colLine = tft.color565(36, 48, 62);
  colCyan = tft.color565(0, 217, 232);
  colViolet = tft.color565(139, 92, 246);
  colMagenta = tft.color565(232, 121, 249);
  colMist = tft.color565(243, 246, 250);
  colSlate = tft.color565(139, 151, 168);
}

void paintText(int x, int y, uint8_t font, uint16_t color, uint16_t bg, int pad,
               const char *text) {
  tft.setTextFont(font);
  tft.setTextColor(color, bg);
  tft.setTextDatum(TL_DATUM);
  tft.setTextPadding(pad);
  tft.drawString(text, x, y);
}

void drawChrome() {
  tft.fillScreen(colInk);
  tft.fillRect(0, 0, kScreenW, 3, colCyan);
  paintText(16, 12, 4, colCyan, colInk, 0, "GOLFAR");
  paintText(392, 14, 2, colSlate, colInk, 0, "PHONE");

  tft.fillRect(kPlotX, kPlotY, kPlotW, kPlotH, colPanel);
  tft.drawRect(kPlotX - 1, kPlotY - 1, kPlotW + 2, kPlotH + 2, colLine);
  tft.fillRect(kPanelX, kPanelY, kPanelW, kPanelH, colRaised);
  tft.drawRect(kPanelX - 1, kPanelY - 1, kPanelW + 2, kPanelH + 2, colLine);

  const char *angles[] = {"PITCH", "ROLL", "YAW"};
  for (int i = 0; i < 3; ++i) {
    paintText(kPanelX + 12, 56 + i * 32, 2, colSlate, colRaised, 0, angles[i]);
  }
  tft.drawFastHLine(kPanelX + 10, 148, kPanelW - 20, colLine);
  paintText(kPanelX + 12, 156, 2, colSlate, colRaised, 0, "GYRO");
  paintText(kPanelX + 250, 156, 2, colSlate, colRaised, 0, "dps");
  tft.drawFastHLine(kPanelX + 10, 200, kPanelW - 20, colLine);
  paintText(kPanelX + 12, 208, 2, colSlate, colRaised, 0, "ACCEL");
  paintText(kPanelX + 262, 208, 2, colSlate, colRaised, 0, "g");
}

void paintField(int x, int y, int w, int h, uint8_t font, uint16_t color, const char *text) {
  tft.fillRect(x, y, w, h, colRaised);
  paintText(x, y, font, color, colRaised, 0, text);
}

void placeTip(float deg, float want, int originX, int originY, int &x, int &y) {
  const float rad = deg * 0.01745329252f;
  const float dx = sinf(rad);
  const float dy = -cosf(rad);
  float len = want;
  constexpr float kMargin = 8.0f;
  if (dx > 0.02f) {
    const float lim = (kPlotW - kMargin - originX) / dx;
    if (lim < len) len = lim;
  } else if (dx < -0.02f) {
    const float lim = (kMargin - originX) / dx;
    if (lim < len) len = lim;
  }
  if (dy > 0.02f) {
    const float lim = (kPlotH - kMargin - originY) / dy;
    if (lim < len) len = lim;
  } else if (dy < -0.02f) {
    const float lim = (kMargin - originY) / dy;
    if (lim < len) len = lim;
  }
  if (len < 12.0f) len = 12.0f;
  x = originX + static_cast<int>(lroundf(dx * len));
  y = originY + static_cast<int>(lroundf(dy * len));
}

void renderClub(bool live, bool swinging) {
  if (!plotReady) {
    if (!live) {
      paintText(kPlotX + 36, kPlotY + 92, 2, colMagenta, colPanel, 100, "NO GYRO");
    }
    return;
  }
  plot.fillSprite(colPanel);
  const int ox = kPlotW / 2;
  const int oy = kPlotH - 22;
  if (!live) {
    plot.setTextDatum(MC_DATUM);
    plot.setTextFont(4);
    plot.setTextColor(colMagenta, colPanel);
    plot.setTextPadding(0);
    plot.drawString("NO GYRO", ox, oy - 70);
    plot.pushSprite(kPlotX, kPlotY);
    return;
  }

  for (int deg = -60; deg <= 60; deg += 30) {
    const float rad = deg * 0.01745329252f;
    const float inner = deg == 0 ? 40.0f : 48.0f;
    const float outer = 62.0f;
    const int x0 = ox + static_cast<int>(lroundf(sinf(rad) * inner));
    const int y0 = oy - static_cast<int>(lroundf(cosf(rad) * inner));
    const int x1 = ox + static_cast<int>(lroundf(sinf(rad) * outer));
    const int y1 = oy - static_cast<int>(lroundf(cosf(rad) * outer));
    plot.drawLine(x0, y0, x1, y1, deg == 0 ? colCyan : colLine);
  }

  int ax = ox;
  int ay = oy - 120;
  placeTip(0, 132, ox, oy, ax, ay);
  plot.drawWideLine(ox, oy, ax, ay, 2, colLine, colPanel);

  int tx = ox;
  int ty = oy - 120;
  placeTip(viewPitch, 132, ox, oy, tx, ty);
  const uint16_t shaft = swinging ? colViolet : colCyan;
  plot.drawWideLine(ox, oy, tx, ty, 4, shaft, colPanel);

  const float head = (viewPitch + viewRoll) * 0.01745329252f;
  const float hx = cosf(head);
  const float hy = sinf(head);
  plot.drawWideLine(tx - hx * 8.0f, ty - hy * 8.0f, tx + hx * 24.0f, ty + hy * 24.0f, 5,
                    colMist, colPanel);
  plot.fillCircle(ox, oy, 6, shaft);
  plot.fillCircle(ox, oy, 2, colPanel);
  plot.pushSprite(kPlotX, kPlotY);
}

void paintAngle(int index, float value, bool ok, uint16_t color) {
  char buf[12];
  if (!ok) {
    snprintf(buf, sizeof(buf), "--.-");
  } else {
    snprintf(buf, sizeof(buf), "%+.1f", value);
  }
  paintField(kPanelX + 132, 50 + index * 32, 150, 26, 4, ok ? color : colSlate, buf);
}

void paintAxes(int y, bool ok, const char *fmt, float x, float yy, float z) {
  const int cols[] = {kPanelX + 12, kPanelX + 108, kPanelX + 204};
  const char *names[] = {"X", "Y", "Z"};
  const float values[] = {x, yy, z};
  for (int i = 0; i < 3; ++i) {
    char buf[16];
    if (!ok) {
      snprintf(buf, sizeof(buf), "%s --", names[i]);
    } else {
      char num[12];
      snprintf(num, sizeof(num), fmt, values[i]);
      snprintf(buf, sizeof(buf), "%s %s", names[i], num);
    }
    paintField(cols[i], y, 88, 16, 2, ok ? colMist : colSlate, buf);
  }
}

void paintLive(bool connected, bool haveLatest, const ImuSample &sample) {
  const bool live = imuReady && haveLatest;
  float gmag = 0;
  if (live) {
    gmag = sqrtf(sample.gx * sample.gx + sample.gy * sample.gy + sample.gz * sample.gz);
    viewPitch += (clubSwing - viewPitch) * 0.45f;
    viewRoll += (clubRoll - viewRoll) * 0.45f;
  }
  const bool swinging = live && gmag >= 35.0f;

  const char *state = "HOLD";
  const char *hint = "Hold the club still at address";
  uint16_t stateColor = colSlate;
  if (!live) {
    state = "NO CLUB";
    hint = "I2C socket   SDA 32   SCL 25";
    stateColor = colMagenta;
  } else if (swinging) {
    state = "SWING";
    hint = "In the swing";
    stateColor = colViolet;
  } else if (holdingStill && addressLocked) {
    state = "ADDRESS";
    hint = "Address set. This is zero.";
    stateColor = colCyan;
  } else if (addressLocked) {
    state = "READY";
    hint = "Swing when you are ready";
    stateColor = colMist;
  }

  tft.fillCircle(206, 22, 4, stateColor);
  paintText(218, 14, 2, stateColor, colInk, 150, state);
  tft.fillCircle(458, 22, 5, connected ? colCyan : colSlate);

  renderClub(live, swinging);
  paintAngle(0, clubPitch, live, colCyan);
  paintAngle(1, clubRoll, live, colMist);
  paintAngle(2, clubYaw, live, colMist);
  paintAxes(178, live, "%+.0f", sample.gx, sample.gy, sample.gz);
  paintAxes(228, live, "%+.2f", sample.ax, sample.ay, sample.az);
  paintText(16, 284, 2, colSlate, colInk, 450, hint);
}

void startBle() {
  BLEDevice::init(kDeviceName);
  BLEDevice::setMTU(185);

  bleServer = BLEDevice::createServer();
  bleServer->setCallbacks(new ServerCallbacks());
  bleServer->advertiseOnDisconnect(true);

  BLEService *service = bleServer->createService(kServiceUuid);
  streamChar = service->createCharacteristic(
      kStreamUuid, BLECharacteristic::PROPERTY_NOTIFY);
  streamChar->setCallbacks(new StreamCallbacks());
#if defined(CONFIG_BLUEDROID_ENABLED)
  auto *subscription = new BLE2902();
  subscription->setCallbacks(new SubscriptionCallbacks());
  streamChar->addDescriptor(subscription);
#endif
  service->start();

  BLEAdvertising *advertising = BLEDevice::getAdvertising();
  advertising->addServiceUUID(kServiceUuid);
  advertising->setScanResponse(true);
  advertising->setMinInterval(160);  // 100 ms
  advertising->setMaxInterval(240);  // 150 ms
  BLEDevice::startAdvertising();
  Serial.printf("BLE advertising as %s\n", kDeviceName);
}

void setup() {
  Serial.begin(115200);
  delay(200);
  Serial.println("GolfAR club display");

  tft.init();
  tft.setRotation(1);
  tft.setTextWrap(false);
  loadPalette();
  plot.setColorDepth(16);
  plotReady = plot.createSprite(kPlotW, kPlotH) != nullptr;
  if (!plotReady) {
    Serial.println("club graphic skipped, not enough RAM");
  }

  imuReady = probeMpu(true);
  if (!imuReady) {
    Serial.println("IMU not found yet. BLE will still advertise.");
  }

  drawChrome();
  paintLive(false, false, ImuSample{});
  startBle();
}

void loop() {
  static uint32_t lastSampleMs = 0;
  static uint32_t lastPublishMs = 0;
  static uint32_t lastNotifyMs = 0;
  static uint32_t lastLogMs = 0;
  static uint32_t lastDisplayMs = 0;
  static uint32_t lastImuRetryMs = 0;
  static bool wasConnected = false;
  static ImuSample latest = {};
  static bool haveLatest = false;

  if (resetTx) {
    txLen = 0;
    resetTx = false;
  }

  const bool connected = clientConnected;
  if (connected && !wasConnected) {
    sequence = 0;
    Serial.println("BLE client connected");
  } else if (!connected && wasConnected) {
    Serial.println("BLE client disconnected");
  }
  wasConnected = connected;

  const uint32_t now = millis();
  if (!imuReady && now - lastImuRetryMs >= 2000) {
    lastImuRetryMs = now;
    imuReady = probeMpu();
  }

  if (imuReady && now - lastSampleMs >= kSamplePeriodMs) {
    lastSampleMs = now;
    ImuSample sample;
    if (readImu(&sample)) {
      latest = sample;
      haveLatest = true;
      updateClubAngle(sample, now);
      if (connected && notificationsEnabled && now - lastPublishMs >= kPublishPeriodMs) {
        lastPublishMs = now;
        publishImu(sample);
      }
    } else {
      imuReady = false;
      haveLatest = false;
      Serial.println("IMU read failed");
    }
  }

  if (now - lastNotifyMs >= kNotifyPeriodMs) {
    lastNotifyMs = now;
    flushTx();
  }

  if (now - lastDisplayMs >= kDisplayPeriodMs) {
    lastDisplayMs = now;
    paintLive(connected, haveLatest, latest);
  }

  if (now - lastLogMs >= kLogPeriodMs) {
    lastLogMs = now;
    if (haveLatest) {
      Serial.printf(
          "ble %s seq=%u drops=%lu notify-errors=%lu  a %6.2f %6.2f %6.2f  g %6.1f %6.1f %6.1f  "
          "angle %6.1f %6.1f %6.1f\n",
          connected ? "up" : "down", sequence, static_cast<unsigned long>(droppedFrames),
          static_cast<unsigned long>(notifyErrors),
          latest.ax, latest.ay, latest.az, latest.gx, latest.gy, latest.gz, clubPitch,
          clubRoll, clubYaw);
    } else {
      Serial.printf("ble %s, imu offline\n", connected ? "up" : "down");
    }
  }
}
