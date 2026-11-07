# ESP32 Synchronized OLED Video Player

```
esp32-oled-player/
├── README.md
├── requirements.txt
├── videos/                <- put your video.mp4 here
├── firmware/esp32_oled_player/esp32_oled_player.ino   <- upload with Arduino IDE
└── python/
    ├── main.py            <- run this
    ├── config.py          <- serial port, baud rate, fps, dithering
    ├── esp32_link.py      <- serial protocol + reconnect
    ├── audio_player.py    <- laptop sound (ffpyplayer)
    └── frame_convert.py   <- frame -> 1-bit 128x64
```

## Wiring (ESP32 DevKit V1, 30-pin)

| Part | Pin | ESP32 |
|---|---|---|
| OLED | VCC | 3V3 |
| OLED | GND | GND |
| OLED | SDA | GPIO 21 |
| OLED | SCL | GPIO 22 |

No buttons are needed. Playback is controlled from the laptop keyboard.

## Install (Windows)
1. Install Python 3.9+ from python.org (tick **Add Python to PATH**).
2. In a terminal inside the project folder:
   ```
   python -m pip install -r requirements.txt
   ```
3. If Windows doesn't show a COM port when the ESP32 is plugged in, install the CP210x or CH340 USB driver (check the chip on your board).

## Upload firmware
1. Arduino IDE → Boards Manager → install **esp32 by Espressif Systems**.
2. Library Manager → install **Adafruit SSD1306** and **Adafruit GFX Library** (accept "install all" dependencies).
3. Open `firmware/esp32_oled_player/esp32_oled_player.ino`.
4. Tools → Board → **ESP32 Dev Module**; Tools → Port → your COM port.
5. Upload. If it stays on "Connecting...", hold the **BOOT** button until upload starts.
6. The OLED should show "PC: not connected / Waiting...". **Close the Serial Monitor** afterwards (it blocks the port).

## Run
```
cd python
python main.py                 # plays ..\videos\video.mp4 (or opens a file dialog if missing)
python main.py "C:\videos\clip.mp4"
```
Click the video window, then: **SPACE** or **K** = play/pause, **Left arrow** or **A** = -5 s, **Right arrow** or **D** = +5 s, **Q** or **ESC** = quit.

### Changing port / baud rate
Edit `python/config.py`: `SERIAL_PORT = "COM5"` (or `"AUTO"`), `BAUD_RATE = 921600`.
If you change the baud rate, change `const uint32_t BAUD` in the `.ino` to the same value and re-upload.
Find your port: Device Manager → Ports (COM & LPT), or Arduino IDE → Tools → Port.

## Testing
1. **Link:** run `main.py`. Console prints `[link] connected on COMx`, the OLED shows "PC: connected", then video. On quit it prints `frames sent / acks / crc_errors`; acks should be about equal to frames sent and crc_errors near 0.
2. **Sync:** play a video with an on-screen stopwatch. Compare laptop vs OLED; they should match within a frame or two. Seek and pause and confirm the OLED follows.
3. **Controls:** press SPACE (pause icon appears top-left of OLED), Left/Right arrows (5 s jumps); the progress bar along the bottom moves.
4. **Error handling:** unplug USB while playing. The video keeps playing, the window says "NOT connected", and the app reconnects automatically after replugging. Unplug the PC side/close the app: the OLED returns to "PC: not connected" after 3 s.

## Troubleshooting
| Problem | Fix |
|---|---|
| `could not open port` / access denied | Close Arduino Serial Monitor and any other program using the port; check `SERIAL_PORT`. |
| No COM port shown | Install CP210x/CH340 driver; use a data-capable USB cable. |
| Upload fails "Connecting..." | Hold BOOT during upload; lower Upload Speed to 115200. |
| OLED blank, nothing happens | Check SDA/SCL and 3V3. Some modules use address 0x3D: change `OLED_ADDR`. |
| Image is scrambled | Make sure both sides are the latest provided versions (page-layout packing). |
| Many `crc_errors`, flicker | Lower `BAUD_RATE` (460800 / 115200) on both sides; use a shorter cable; lower `OLED_FPS`. |
| OLED lags behind / low fps | Normal ceiling is ~20-30 fps. Lower `OLED_FPS`; set `I2C_CLOCK` to 800000 if your OLED tolerates it. |
| Video won't open | Re-encode to H.264 MP4, or try `pip install --upgrade opencv-python`. |
| No sound | Run `python -m pip install ffpyplayer`; check `AUDIO = True` in config.py and the laptop volume. |
| Seek lands slightly off | MP4 keyframe seeking is approximate. |
| Keys do nothing | Click the video window first so it has keyboard focus. |
