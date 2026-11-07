"""User settings. Edit this file to change the serial port, baud rate, etc."""

VIDEO_PATH = "videos/video.mp4"   # relative to the project folder (or a full path); if missing, a file dialog opens

ASK_SOURCE = True            # ask for a YouTube link at start (Enter = play VIDEO_PATH). False = never ask
YOUTUBE_MAX_HEIGHT = 480    # download quality limit (the OLED is only 128x64, so low is fine)

# --- screen mirror (mirror.py) ---
MIRROR_MONITOR = 1          # 1 = main monitor, 2 = second monitor ...
MIRROR_REGION = None        # None = choose with the mouse each time, or {"left":0,"top":0,"width":1280,"height":720}

AUDIO = True                # play the video sound on the laptop (needs ffpyplayer)

SERIAL_PORT = "AUTO"        # "AUTO" = try to detect the ESP32, or set e.g. "COM5"
BAUD_RATE = 921600          # must match BAUD in the .ino (try 460800 / 115200 if unstable)

OLED_FPS = 20               # max OLED updates per second (lower = more reliable)
SEEK_SECONDS = 5            # Left/Right button jump

DITHER = "bayer"            # "bayer" (looks like grayscale) or "threshold" (hard black/white)
THRESHOLD = 110             # used when DITHER == "threshold" (0-255)
INVERT = False              # True = swap black and white

HEARTBEAT_INTERVAL = 1.0    # seconds between keep-alive packets when idle
ACK_TIMEOUT = 0.25          # seconds to wait for ESP32 ACK before sending next frame
RECONNECT_INTERVAL = 2.0    # seconds between reconnect attempts
