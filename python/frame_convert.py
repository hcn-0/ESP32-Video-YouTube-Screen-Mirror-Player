"""Convert a BGR video frame into 1024 bytes for the SSD1306 (128x64, page layout)."""
import cv2
import numpy as np

W, H = 128, 64

# 4x4 Bayer matrix tiled over the whole screen -> per-pixel thresholds (0..255)
_BAYER4 = np.array([[0, 8, 2, 10], [12, 4, 14, 6], [3, 11, 1, 9], [15, 7, 13, 5]], dtype=np.float32)
_BAYER = (np.tile(_BAYER4, (H // 4, W // 4)) + 0.5) / 16.0 * 255.0
_WEIGHTS = (1 << np.arange(8)).astype(np.uint8)  # bit i = pixel (page*8 + i)


def to_oled_bytes(frame_bgr, dither="bayer", threshold=110, invert=False) -> bytes:
    gray = cv2.cvtColor(frame_bgr, cv2.COLOR_BGR2GRAY)
    h, w = gray.shape

    # Keep aspect ratio: scale to fit, centre on a black 128x64 canvas
    scale = min(W / w, H / h)
    nw, nh = max(1, int(w * scale)), max(1, int(h * scale))
    small = cv2.resize(gray, (nw, nh), interpolation=cv2.INTER_AREA)
    canvas = np.zeros((H, W), np.uint8)
    x0, y0 = (W - nw) // 2, (H - nh) // 2
    canvas[y0:y0 + nh, x0:x0 + nw] = small

    bits = canvas > (_BAYER if dither == "bayer" else threshold)
    if invert:
        bits = ~bits

    # Adafruit buffer layout: byte index = x + (y // 8) * 128, bit = y % 8 (LSB = top)
    paged = bits.reshape(8, 8, W).astype(np.uint8)          # [page, bit, x]
    packed = (paged * _WEIGHTS[None, :, None]).sum(axis=1).astype(np.uint8)
    return packed.tobytes()                                  # 1024 bytes
