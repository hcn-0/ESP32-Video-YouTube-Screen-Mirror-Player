/*
  ESP32 Synchronized OLED Video Player - firmware
  Board: ESP32 DevKit V1 | Display: SSD1306 128x64 I2C (0x3C)
  Libraries: Adafruit SSD1306, Adafruit GFX

  PC -> ESP32 packet:  AA 55 | type | len(LE16) | payload | CRC16-CCITT-FALSE (LE16)
     type 0x01 FRAME     payload = progress(0..255), flags(bit0 = paused, bit1 = live mode), 1024 bytes (SSD1306 page layout)
     type 0x02 HEARTBEAT payload = none
  ESP32 -> PC (text lines): "K" frame OK | "E" bad packet | "READY"
  Playback is controlled from the laptop keyboard (no physical buttons).
*/
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>

// ---------------- Settings ----------------
#define SCREEN_W 128
#define SCREEN_H 64
#define OLED_ADDR 0x3C
#define PIN_SDA 21
#define PIN_SCL 22

const uint32_t BAUD = 921600;               // must match BAUD_RATE in python/config.py
const uint32_t I2C_CLOCK = 400000;          // try 800000 if your OLED allows it
const uint32_t LINK_TIMEOUT_MS = 3000;      // no packet for this long = "PC not connected"
const uint32_t PACKET_TIMEOUT_MS = 200;     // abandon half-received packets

// ---------------- Protocol ----------------
const uint8_t T_FRAME = 0x01, T_HEARTBEAT = 0x02;
const uint16_t FRAME_BYTES = SCREEN_W * SCREEN_H / 8;     // 1024
const uint16_t FRAME_PAYLOAD = FRAME_BYTES + 2;           // + progress + flags
const uint16_t MAX_PAYLOAD = 1100;

Adafruit_SSD1306 display(SCREEN_W, SCREEN_H, &Wire, -1, I2C_CLOCK, I2C_CLOCK);

// ---------------- Receiver state machine ----------------
enum RxState : uint8_t { S_SYNC1, S_SYNC2, S_TYPE, S_LENL, S_LENH, S_PAYLOAD, S_CRCL, S_CRCH };
RxState rxState = S_SYNC1;
uint8_t rxBuf[MAX_PAYLOAD];
uint8_t rxType;
uint16_t rxLen, rxPos, rxCrc, rxCrcRecv;
uint32_t lastByteMs = 0, lastPacketMs = 0;
bool linkSeen = false, lastAlive = false, frameReady = false;
uint8_t progress = 0;
bool paused = false;
bool liveMode = false;     // screen-mirror mode: no progress bar

static inline uint16_t crcUpdate(uint16_t crc, uint8_t b) {
  crc ^= (uint16_t)b << 8;
  for (uint8_t i = 0; i < 8; i++) crc = (crc & 0x8000) ? (uint16_t)((crc << 1) ^ 0x1021) : (uint16_t)(crc << 1);
  return crc;
}

// ---------------- Drawing ----------------
void drawStatus(const char *l1, const char *l2) {
  display.clearDisplay();
  display.setTextSize(1);
  display.setTextColor(SSD1306_WHITE);
  display.setCursor(0, 0);   display.println(F("ESP32 OLED Player"));
  display.setCursor(0, 24);  display.println(l1);
  display.setCursor(0, 36);  display.println(l2);
  display.display();
}

// Called right after a frame is copied into the display buffer
void drawOverlay() {
  // progress bar: 1px track + 3px filled part along the bottom (hidden in live mirror mode)
  if (!liveMode) {
    display.fillRect(0, SCREEN_H - 3, SCREEN_W, 3, SSD1306_BLACK);
    display.drawFastHLine(0, SCREEN_H - 1, SCREEN_W, SSD1306_WHITE);
    uint8_t w = (uint16_t)progress * SCREEN_W / 255;
    if (w) display.fillRect(0, SCREEN_H - 3, w, 3, SSD1306_WHITE);
  }
  // pause icon
  if (paused) {
    display.fillRect(0, 0, 13, 13, SSD1306_BLACK);
    display.fillRect(3, 2, 3, 9, SSD1306_WHITE);
    display.fillRect(8, 2, 3, 9, SSD1306_WHITE);
  }
}

// ---------------- Packet handling ----------------
void handlePacket() {
  lastPacketMs = millis();
  linkSeen = true;
  if (rxType == T_FRAME && rxLen == FRAME_PAYLOAD) {
    progress = rxBuf[0];
    paused = rxBuf[1] & 1;
    liveMode = rxBuf[1] & 2;
    memcpy(display.getBuffer(), rxBuf + 2, FRAME_BYTES);   // CRC already verified: never half-drawn
    drawOverlay();
    frameReady = true;               // display.display() happens once in loop()
    Serial.print("K\n");
  } else if (rxType == T_HEARTBEAT) {
    // nothing else to do: lastPacketMs is the keep-alive
  } else {
    Serial.print("E\n");
  }
}

void processByte(uint8_t b) {
  switch (rxState) {
    case S_SYNC1: if (b == 0xAA) rxState = S_SYNC2; break;
    case S_SYNC2: rxState = (b == 0x55) ? S_TYPE : (b == 0xAA ? S_SYNC2 : S_SYNC1); break;
    case S_TYPE:  rxType = b; rxCrc = crcUpdate(0xFFFF, b); rxState = S_LENL; break;
    case S_LENL:  rxLen = b; rxCrc = crcUpdate(rxCrc, b); rxState = S_LENH; break;
    case S_LENH:
      rxLen |= (uint16_t)b << 8;
      rxCrc = crcUpdate(rxCrc, b);
      rxPos = 0;
      if (rxLen > MAX_PAYLOAD) { Serial.print("E\n"); rxState = S_SYNC1; }
      else rxState = rxLen ? S_PAYLOAD : S_CRCL;
      break;
    case S_PAYLOAD:
      rxBuf[rxPos++] = b;
      rxCrc = crcUpdate(rxCrc, b);
      if (rxPos >= rxLen) rxState = S_CRCL;
      break;
    case S_CRCL: rxCrcRecv = b; rxState = S_CRCH; break;
    case S_CRCH:
      rxCrcRecv |= (uint16_t)b << 8;
      rxState = S_SYNC1;
      if (rxCrcRecv == rxCrc) handlePacket();
      else Serial.print("E\n");      // corrupted: PC will simply send a newer frame
      break;
  }
}

// ---------------- Arduino entry points ----------------
void setup() {
  Serial.setRxBufferSize(4096);      // room for a whole frame while the OLED is refreshing
  Serial.begin(BAUD);

  Wire.begin(PIN_SDA, PIN_SCL);
  Wire.setClock(I2C_CLOCK);
  if (!display.begin(SSD1306_SWITCHCAPVCC, OLED_ADDR)) {
    for (;;) delay(1000);            // OLED not found: check wiring / address
  }
  drawStatus("PC: not connected", "Waiting...");
  Serial.print("READY\n");
}

void loop() {
  // 1) read everything that has arrived
  while (Serial.available()) {
    processByte((uint8_t)Serial.read());
    lastByteMs = millis();
  }
  if (rxState != S_SYNC1 && (millis() - lastByteMs) > PACKET_TIMEOUT_MS) rxState = S_SYNC1;

  // 2) connection status
  bool alive = linkSeen && (millis() - lastPacketMs) < LINK_TIMEOUT_MS;
  if (!alive && lastAlive) { frameReady = false; drawStatus("PC: not connected", "Waiting..."); }
  else if (alive && !lastAlive && !frameReady) drawStatus("PC: connected", "Waiting for video");
  lastAlive = alive;

  // 3) show newest frame (older queued frames are naturally skipped)
  if (frameReady) { display.display(); frameReady = false; }
}
