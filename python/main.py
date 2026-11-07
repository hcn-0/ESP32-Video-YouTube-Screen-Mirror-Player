"""Play an MP4 on the laptop and mirror it (1-bit) to an ESP32 OLED. ESP32 buttons control playback.

Usage:  python main.py ["video.mp4" | "https://youtube.com/watch?v=..."]
        (no argument = asks for a YouTube link; Enter = videos/video.mp4)
Keys in the video window: SPACE or K = play/pause, LEFT/A = -5 s, RIGHT/D = +5 s, Q or ESC = quit.
"""
import os
import sys
import time

import cv2

import config
from audio_player import AudioPlayer
from esp32_link import ESP32Link
from frame_convert import to_oled_bytes
import youtube


def fmt(t):
    t = max(0, int(t))
    return f"{t // 60:02d}:{t % 60:02d}"


def resolve_source():
    """Return a local video path. Accepts a YouTube URL or a file path."""
    project_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    videos_dir = os.path.join(project_dir, "videos")

    default = config.VIDEO_PATH
    if not os.path.isabs(default):
        default = os.path.join(project_dir, default)

    # 1) command line: a URL or a file path
    source = sys.argv[1] if len(sys.argv) > 1 else ""

    # 2) otherwise ask in the console (Enter = default file)
    if not source and config.ASK_SOURCE:
        print("Paste a YouTube link, or press Enter to play", os.path.relpath(default, project_dir))
        source = input("> ").strip().strip('"')

    if source and youtube.is_url(source):
        try:
            return youtube.download(source, videos_dir, config.YOUTUBE_MAX_HEIGHT)
        except Exception as e:
            print(f"[youtube] failed: {e}")
            return ""
    if source:
        return source

    # 3) default file, else file dialog
    if os.path.isfile(default):
        return default
    print(f"[video] {default} not found - opening file dialog")
    from tkinter import Tk, filedialog
    root = Tk()
    root.withdraw()
    root.attributes("-topmost", True)
    path = filedialog.askopenfilename(
        title="Select a video", initialdir=videos_dir,
        filetypes=[("Video", "*.mp4 *.mkv *.avi *.mov *.webm"), ("All files", "*.*")])
    root.destroy()
    return path


class VideoPlayer:
    """Video decoding driven by a master clock, so the video never drifts from real time."""

    def __init__(self, path, audio=None):
        self.audio = audio
        self.audio_ignore_until = 0.0   # skip drift checks right after play/seek
        self.cap = cv2.VideoCapture(path)
        if not self.cap.isOpened():
            raise RuntimeError(f"Cannot open video: {path}")
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.fps = fps if 1 < fps <= 240 else 30.0
        self.total = int(self.cap.get(cv2.CAP_PROP_FRAME_COUNT))
        self.duration = self.total / self.fps if self.total > 0 else 0.0
        self.width = int(self.cap.get(cv2.CAP_PROP_FRAME_WIDTH))
        self.height = int(self.cap.get(cv2.CAP_PROP_FRAME_HEIGHT))
        self.paused = False
        self.ended = False
        self.next_idx = 0
        self.base_pos = 0.0
        self.base_wall = time.perf_counter()
        self.last_frame = None
        self.frame_serial = 0           # increments for every new frame decoded
        self.preview_pending = False    # show one frame after seeking while paused

    def clock(self):
        if self.paused:
            return self.base_pos
        return self.base_pos + (time.perf_counter() - self.base_wall)

    def position(self):
        pos = self.clock()
        return min(pos, self.duration) if self.duration else pos

    def progress255(self):
        return int(255 * self.position() / self.duration) if self.duration > 0 else 0

    def time_to_next(self):
        return self.next_idx / self.fps - self.clock()

    def start(self):
        """Begin playback from the start (video clock + audio together)."""
        self.base_wall = time.perf_counter()
        if self.audio:
            self.audio.play(self.base_pos)
        self.audio_ignore_until = time.perf_counter() + 2.0

    def toggle(self):
        if self.paused:
            if self.ended:
                self.seek_to(0.0)
            self.base_wall = time.perf_counter()
            self.paused = False
            if self.audio:
                self.audio.play(self.base_pos)
            self.audio_ignore_until = time.perf_counter() + 2.0
        else:
            self.base_pos = self.clock()
            self.paused = True
            if self.audio:
                self.audio.pause()

    def sync_audio(self):
        """Gently re-align audio if it drifted more than 0.25 s from the video clock."""
        if not self.audio or not self.audio.ok or self.paused:
            return
        if time.perf_counter() < self.audio_ignore_until:
            return
        if abs(self.audio.pts() - self.clock()) > 0.25:
            self.audio.seek(self.clock())
            self.audio_ignore_until = time.perf_counter() + 2.0

    def seek(self, delta):
        self.seek_to(self.clock() + delta)

    def seek_to(self, target):
        top = max(0.0, self.duration - 0.2) if self.duration else float("inf")
        target = min(max(0.0, target), top)
        idx = int(target * self.fps)
        self.cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
        self.next_idx, self.base_pos = idx, target
        self.base_wall = time.perf_counter()
        self.ended = False
        self.preview_pending = True
        if self.audio and not self.paused:
            self.audio.seek(target)
            self.audio_ignore_until = time.perf_counter() + 2.0

    def _end(self):
        print("[video] end of video (or unreadable frame)")
        self.base_pos = self.duration if self.duration else self.clock()
        self.paused = True
        self.ended = True
        if self.audio:
            self.audio.pause()

    def _store(self, frame):
        self.last_frame = frame
        self.frame_serial += 1
        return frame

    def advance(self):
        """Return a new frame if one is due, else None. Drops frames if we are late."""
        self.preview_pending = False
        if self.time_to_next() > 0:
            return None
        t = self.clock()
        skipped = 0
        while (self.next_idx + 1) / self.fps <= t and skipped < 60:   # current frame is stale
            if not self.cap.grab():
                self._end()
                return None
            self.next_idx += 1
            skipped += 1
        ok, frame = self.cap.read()
        if not ok or frame is None:
            self._end()
            return None
        self.next_idx += 1
        return self._store(frame)

    def preview(self):
        self.preview_pending = False
        ok, frame = self.cap.read()
        if ok and frame is not None:
            self.next_idx += 1
            return self._store(frame)
        return None


def main():
    path = resolve_source()
    if not path:
        print("No file selected.")
        return
    audio = AudioPlayer(path) if config.AUDIO else None
    try:
        player = VideoPlayer(path, audio)
    except RuntimeError as e:
        print(e)
        return
    print(f"[video] {player.width}x{player.height} @ {player.fps:.2f} fps, {fmt(player.duration)}")

    link = ESP32Link(config.SERIAL_PORT, config.BAUD_RATE, config.ACK_TIMEOUT, config.RECONNECT_INTERVAL)
    link.start()

    win = "Video (mirrored to ESP32 OLED)"
    cv2.namedWindow(win, cv2.WINDOW_NORMAL)
    scale = min(1.0, 960 / max(1, player.width), 540 / max(1, player.height))
    cv2.resizeWindow(win, max(320, int(player.width * scale)), max(180, int(player.height * scale)))

    player.start()                      # starts video clock and audio together
    oled_dirty, was_connected = True, False
    last_oled, sent_serial, shown_once = 0.0, -1, False

    try:
        while True:
            now = time.perf_counter()

            # 1) commands from ESP32 buttons
            for cmd in link.drain_commands():
                if cmd == "PLAY":
                    player.toggle()
                elif cmd == "LEFT":
                    player.seek(-config.SEEK_SECONDS)
                elif cmd == "RIGHT":
                    player.seek(config.SEEK_SECONDS)
                oled_dirty = True

            # 2) get next frame
            if not player.paused:
                new_frame = player.advance()
            elif player.preview_pending:
                new_frame = player.preview()
            else:
                new_frame = None

            # 3) laptop window (plain video, no overlay)
            if player.last_frame is not None and (new_frame is not None or player.paused):
                cv2.imshow(win, player.last_frame)
                shown_once = True
            player.sync_audio()

            # 4) OLED update
            connected = link.connected
            if connected and not was_connected:
                oled_dirty = True
            was_connected = connected
            if player.paused and not link.last_acked:
                oled_dirty = True           # last frame was lost: resend while paused

            if connected and player.last_frame is not None and link.ready_for_frame():
                due = (now - last_oled) >= 1.0 / config.OLED_FPS
                fresh = player.frame_serial != sent_serial
                if oled_dirty or (not player.paused and due and fresh):
                    bits = to_oled_bytes(player.last_frame, config.DITHER, config.THRESHOLD, config.INVERT)
                    link.send_frame(bits, player.progress255(), player.paused)
                    last_oled, sent_serial, oled_dirty = now, player.frame_serial, False

            if connected and now - link.last_tx >= config.HEARTBEAT_INTERVAL:
                link.send_heartbeat()

            # 5) keyboard / window
            delay = 30 if player.paused else max(1, min(15, int(player.time_to_next() * 1000)))
            key = cv2.waitKeyEx(delay)
            if key == -1:
                pass
            elif (key & 0xFF) in (ord("q"), 27):
                break
            elif (key & 0xFF) in (ord(" "), ord("k")):
                player.toggle(); oled_dirty = True
            elif key in (2424832, 65361, 81) or (key & 0xFF) == ord("a"):      # Left arrow / A
                player.seek(-config.SEEK_SECONDS); oled_dirty = True
            elif key in (2555904, 65363, 83) or (key & 0xFF) == ord("d"):      # Right arrow / D
                player.seek(config.SEEK_SECONDS); oled_dirty = True
            if shown_once and cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
                break
    except KeyboardInterrupt:
        pass
    finally:
        print(f"[link] frames sent={link.frames_sent} acks={link.acks} crc_errors={link.errors}")
        link.stop()
        player.cap.release()
        if audio:
            audio.close()
        cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
