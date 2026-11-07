"""Mirror ANYTHING on your screen (a YouTube video in the browser, etc.) to the ESP32 OLED.
Nothing is downloaded: this captures a part of your screen live. Sound plays normally in your browser.

Usage:
  1. Open YouTube in your browser and start the video (leave it visible on screen).
  2. python mirror.py
  3. Within 5 seconds click your browser so the video is visible, then drag a box around the video
     and press ENTER. (ENTER/ESC with no box = whole screen.)
Keys in the small preview window:  Q = quit,  R = choose the area again.
Control playback (pause, seek, volume) in YouTube itself.
"""
import time

import cv2
import mss
import numpy as np

import config
from esp32_link import ESP32Link
from frame_convert import to_oled_bytes


def select_region(sct):
    mon = sct.monitors[config.MIRROR_MONITOR]
    print("Taking a screenshot in 5 seconds - make sure the video is visible on screen...")
    time.sleep(5)
    shot = np.ascontiguousarray(np.array(sct.grab(mon))[:, :, :3])
    h, w = shot.shape[:2]
    scale = min(1.0, 1280 / w, 720 / h)
    small = cv2.resize(shot, (int(w * scale), int(h * scale))) if scale < 1 else shot
    print("Drag a box around the video, then press ENTER. (ENTER with no box = whole screen)")
    x, y, rw, rh = cv2.selectROI("Select video area", small, showCrosshair=False, fromCenter=False)
    cv2.destroyWindow("Select video area")
    if rw < 8 or rh < 8:
        return {k: mon[k] for k in ("left", "top", "width", "height")}
    return {"left": mon["left"] + int(x / scale), "top": mon["top"] + int(y / scale),
            "width": max(8, int(rw / scale)), "height": max(8, int(rh / scale))}


def bits_to_preview(bits: bytes):
    arr = np.frombuffer(bits, np.uint8).reshape(8, 128)                 # [page, x]
    img = ((arr[:, None, :] >> np.arange(8)[None, :, None]) & 1).reshape(64, 128) * 255
    return cv2.resize(img.astype(np.uint8), (256, 128), interpolation=cv2.INTER_NEAREST)


def main():
    link = ESP32Link(config.SERIAL_PORT, config.BAUD_RATE, config.ACK_TIMEOUT, config.RECONNECT_INTERVAL)
    link.start()
    period = 1.0 / config.OLED_FPS
    try:
        with mss.mss() as sct:
            region = config.MIRROR_REGION or select_region(sct)
            print("[mirror] capturing", region, "- press Q in the preview window to quit")
            win = "OLED preview (Q = quit, R = reselect)"
            cv2.namedWindow(win)
            mon = sct.monitors[config.MIRROR_MONITOR]
            cv2.moveWindow(win, mon["left"] + mon["width"] - 280, mon["top"] + mon["height"] - 220)
            last = 0.0
            while True:
                now = time.perf_counter()
                if link.ready_for_frame() and now - last >= period:
                    img = np.ascontiguousarray(np.array(sct.grab(region))[:, :, :3])
                    bits = to_oled_bytes(img, config.DITHER, config.THRESHOLD, config.INVERT)
                    link.send_frame(bits, 0, False, live=True)
                    last = now
                    cv2.imshow(win, bits_to_preview(bits))
                if link.connected and now - link.last_tx >= config.HEARTBEAT_INTERVAL:
                    link.send_heartbeat()
                key = cv2.waitKey(1) & 0xFF
                if key in (ord("q"), 27):
                    break
                if key == ord("r"):
                    region = select_region(sct)
                if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1 and last > 0:
                    break
    except KeyboardInterrupt:
        pass
    finally:
        print(f"[link] frames sent={link.frames_sent} acks={link.acks} crc_errors={link.errors}")
        link.stop()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
