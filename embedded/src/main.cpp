#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <Arduino.h>
#include <BLEDevice.h>
#include <BLEServer.h>
#include <BLEUtils.h>
#include <Wire.h>
#include <string.h>

#include "protocol.h"

// GY-521 on I2C. A second module can share SDA/SCL with AD0 tied to 3V3.
//   VCC -> 3V3
//   GND -> GND
//   SDA -> GPIO 8
//   SCL -> GPIO 9

// SSD1306 0.96" OLED shares this bus. Address is 0x3C.
// With the glass facing you and the pins along the bottom, the
// usual order is GND, VCC, SCL, SDA. Match the printed labels.
constexpr int kSdaPin = 8;
constexpr int kSclPin = 9;
constexpr int kScreenWidth = 128;
constexpr int kScreenHeight = 64;
// Button module S goes to GPIO 4. Pressure-module S goes to GPIO 5.
// Buzzer on GPIO 18. It sounds only while the button is held.
constexpr int kButtonPin = 4;
constexpr int kPressurePin = 5;
constexpr int kBuzzerPin = 18;
constexpr uint8_t kMpuAddress = 0x68;
constexpr uint32_t kI2cHz = 100000;
constexpr uint32_t kSamplePeriodMs = 20;  // 50 Hz over BLE
constexpr uint32_t kLogPeriodMs = 1000;
constexpr uint32_t kDisplayPeriodMs = 400;

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

constexpr float kAccelLsbPerG = 16384.0f;
constexpr float kGyroLsbPerDps = 131.0f;
constexpr size_t kTxCapacity = 256;
constexpr size_t kImuPayloadLen = 16;

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

BLEServer *bleServer = nullptr;
BLECharacteristic *streamChar = nullptr;
volatile bool clientConnected = false;
volatile bool resetTx = false;

uint8_t txBuf[kTxCapacity];
size_t txLen = 0;
uint32_t droppedFrames = 0;
uint16_t sequence = 0;
ImuKind imuKind = ImuKind::Mpu6050;
bool imuReady = false;
Adafruit_SSD1306 display(kScreenWidth, kScreenHeight, &Wire, -1);
bool displayReady = false;
uint8_t oledAddr = 0x3C;
bool vibrationOn = false;
bool buttonIdleHigh = true;
int pressureLevel = HIGH;

class ServerCallbacks : public BLEServerCallbacks {
  void onConnect(BLEServer *server) override {
    (void)server;
    clientConnected = true;
  }

  void onDisconnect(BLEServer *server) override {
    (void)server;
    clientConnected = false;
    resetTx = true;
  }
};

bool writeReg(uint8_t reg, uint8_t value) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(reg);
  Wire.write(value);
  return Wire.endTransmission() == 0;
}

bool readRegs(uint8_t reg, uint8_t *buf, size_t len) {
  Wire.beginTransmission(kMpuAddress);
  Wire.write(reg);
  if (Wire.endTransmission(false) != 0) {
    return false;
  }
  if (Wire.requestFrom(kMpuAddress, static_cast<uint8_t>(len)) != len) {
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
  if (!writeReg(kRegPwrMgmt1, 0x00)) {
    return false;
  }
  delay(50);

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

  writeReg(kRegSampleRate, 19);  // 50 Hz when the gyro output rate is 1 kHz
  writeReg(kRegConfig, 0x03);
  writeReg(kRegGyroConfig, 0x00);
  writeReg(kRegAccelConfig, 0x00);
  return true;
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

// Any future sensor calls this with its own id and payload.
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
  if (!clientConnected || streamChar == nullptr || txLen == 0) {
    return;
  }
  // A few notifications per loop drains a frame without stalling I2C.
  for (int burst = 0; burst < 6 && clientConnected && txLen > 0; ++burst) {
    size_t chunk = notifyLimit();
    if (chunk == 0) {
      return;
    }
    if (chunk > txLen) {
      chunk = txLen;
    }
    streamChar->setValue(txBuf, chunk);
    streamChar->notify();
    memmove(txBuf, txBuf + chunk, txLen - chunk);
    txLen -= chunk;
  }
}

bool i2cPresent(uint8_t addr) {
  Wire.beginTransmission(addr);
  return Wire.endTransmission() == 0;
}

void scanI2c() {
  Serial.print("I2C scan:");
  bool any = false;
  for (uint8_t addr = 1; addr < 127; ++addr) {
    if (!i2cPresent(addr)) {
      continue;
    }
    any = true;
    Serial.printf(" 0x%02X", addr);
  }
  Serial.println(any ? "" : " none");
}

bool panelCommand(uint8_t cmd) {
  Wire.beginTransmission(oledAddr);
  Wire.write(0x00);
  Wire.write(cmd);
  return Wire.endTransmission() == 0;
}

// Page mode plus both charge-pump commands. The same 0.96" boards
// answer as SSD1306 or SH1106, and horizontal mode leaves the SH1106 dark.
bool panelUp() {
  static const uint8_t seq[] = {
      0xAE, 0xD5, 0x80, 0xA8, 0x3F, 0xD3, 0x00, 0x40, 0xAD, 0x8B,
      0x8D, 0x14, 0x20, 0x02, 0xA1, 0xC8, 0xDA, 0x12, 0x81, 0xCF,
      0xD9, 0xF1, 0xDB, 0x40, 0xA4, 0xA6, 0xAF};
  for (uint8_t cmd : seq) {
    if (!panelCommand(cmd)) {
      return false;
    }
  }
  return true;
}

bool pushPanel() {
  const uint8_t *buffer = display.getBuffer();
  for (uint8_t page = 0; page < 8; ++page) {
    // Column 2 is the visible origin on SH1106 and a 2px shift on SSD1306.
    if (!panelCommand(0xB0 | page) || !panelCommand(0x02) || !panelCommand(0x10)) {
      return false;
    }
    const uint8_t *row = buffer + static_cast<size_t>(page) * kScreenWidth;
    for (int col = 0; col < kScreenWidth; col += 32) {
      Wire.beginTransmission(oledAddr);
      Wire.write(0x40);
      for (int i = 0; i < 32; ++i) {
        Wire.write(row[col + i]);
      }
      if (Wire.endTransmission() != 0) {
        return false;
      }
    }
  }
  return true;
}

bool beginDisplay() {
  uint8_t addr = 0;
  if (i2cPresent(0x3C)) {
    addr = 0x3C;
  } else if (i2cPresent(0x3D)) {
    addr = 0x3D;
  } else {
    return false;
  }
  oledAddr = addr;
  // periphBegin stays false so Wire keeps GPIO 8 and GPIO 9.
  if (!display.begin(SSD1306_SWITCHCAPVCC, addr, false, false)) {
    return false;
  }
  if (!panelUp()) {
    return false;
  }
  display.fillRect(0, 0, kScreenWidth, kScreenHeight, SSD1306_WHITE);
  if (!pushPanel()) {
    return false;
  }
  delay(200);
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setCursor(0, 0);
  display.println("HackUTD");
  display.printf("OLED 0x%02X\n", addr);
  return pushPanel();
}

constexpr uint16_t kBeepHz = 2000;

void silenceBuzzer() { ledcWrite(kBuzzerPin, 0); }

void setBuzzer(bool on) {
  if (on == vibrationOn) {
    return;
  }
  vibrationOn = on;
  if (on) {
    ledcWriteTone(kBuzzerPin, kBeepHz);
    Serial.println("beep");
  } else {
    silenceBuzzer();
  }
}

void updateVibration(uint32_t now) {
  static int lastPrinted = -10000;
  static uint32_t lastPressurePrintMs = 0;
  setBuzzer(digitalRead(kButtonPin) == LOW);

  long sum = 0;
  for (int i = 0; i < 4; ++i) {
    sum += analogRead(kPressurePin);
  }
  pressureLevel = static_cast<int>(sum / 4);
  const bool moved = pressureLevel > lastPrinted + 40 || pressureLevel < lastPrinted - 40;
  if (moved && now - lastPressurePrintMs >= 200) {
    lastPrinted = pressureLevel;
    lastPressurePrintMs = now;
    Serial.printf("pressure %d\n", pressureLevel);
  }
}

void drawStatus(bool connected, bool haveLatest, const ImuSample &latest) {
  if (!displayReady) {
    return;
  }
  display.clearDisplay();
  display.setCursor(0, 0);
  display.println("HackUTD");
  display.printf("BLE %s\n", connected ? "up" : "down");
  if (!imuReady) {
    display.println("IMU offline");
  } else if (haveLatest) {
    display.printf("X %5.2f g\n", latest.ax);
    display.printf("Y %5.2f g\n", latest.ay);
    display.printf("Z %5.2f g\n", latest.az);
  } else {
    display.println("IMU waiting");
  }
  display.printf("P %4d\n", pressureLevel);
  if (!pushPanel()) {
    displayReady = false;
  }
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
  pinMode(kButtonPin, INPUT_PULLUP);
  pinMode(kPressurePin, INPUT);
  pinMode(kBuzzerPin, OUTPUT);
  ledcAttach(kBuzzerPin, 2000, 8);
  silenceBuzzer();
  analogSetPinAttenuation(kPressurePin, ADC_11db);
  delay(50);
  buttonIdleHigh = digitalRead(kButtonPin) == HIGH;
  pressureLevel = analogRead(kPressurePin);
  Serial.printf("inputs idle  button=%s pressure=%d\n",
                buttonIdleHigh ? "high" : "low", pressureLevel);

  Wire.begin(kSdaPin, kSclPin);
  Wire.setClock(kI2cHz);
  scanI2c();
  imuReady = beginMpu();
  if (!imuReady) {
    Serial.println("IMU not found yet. BLE will still advertise.");
  }

  displayReady = beginDisplay();
  Serial.println(displayReady ? "OLED ready" : "OLED not found at 0x3C or 0x3D");

  startBle();
}

void loop() {
  static uint32_t lastSampleMs = 0;
  static uint32_t lastLogMs = 0;
  static uint32_t lastDisplayMs = 0;
  static uint32_t lastImuRetryMs = 0;
  static uint32_t lastDisplayRetryMs = 0;
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
  updateVibration(now);
  if (!imuReady && now - lastImuRetryMs >= 2000) {
    lastImuRetryMs = now;
    imuReady = beginMpu();
  }

  if (!displayReady && now - lastDisplayRetryMs >= 2000) {
    lastDisplayRetryMs = now;
    displayReady = beginDisplay();
    if (displayReady) {
      Serial.printf("OLED ready at 0x%02X\n", oledAddr);
    }
  }

  if (imuReady && now - lastSampleMs >= kSamplePeriodMs) {
    lastSampleMs = now;
    ImuSample sample;
    if (readImu(&sample)) {
      latest = sample;
      haveLatest = true;
      if (connected) {
        publishImu(sample);
      }
    } else {
      imuReady = false;
      Serial.println("IMU read failed");
    }
  }

  flushTx();

  if (displayReady && now - lastDisplayMs >= kDisplayPeriodMs) {
    lastDisplayMs = now;
    drawStatus(connected, haveLatest, latest);
  }

  if (now - lastLogMs >= kLogPeriodMs) {
    lastLogMs = now;
    if (haveLatest) {
      Serial.printf(
          "ble %s seq=%u drops=%lu  accel %5.2f %5.2f %5.2f  btn=%d pressure=%d vib=%d\n",
          connected ? "up" : "down", sequence,
          static_cast<unsigned long>(droppedFrames), latest.ax, latest.ay,
          latest.az, digitalRead(kButtonPin), pressureLevel,
          vibrationOn ? 1 : 0);
    } else {
      Serial.printf("ble %s, imu offline\n", connected ? "up" : "down");
    }
  }
}
