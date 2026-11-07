"""Audio playback (sound only) using ffpyplayer. The video itself is decoded by OpenCV.
If ffpyplayer is missing or the file has no audio, the app simply runs without sound."""
import time


class AudioPlayer:
    def __init__(self, path):
        self.player = None
        try:
            from ffpyplayer.player import MediaPlayer
            # 'vn' = ignore video, 'paused' = wait until we say go
            self.player = MediaPlayer(path, ff_opts={"vn": True, "sn": True, "paused": True})
            t0 = time.time()
            md = None
            while time.time() - t0 < 5.0:           # wait until the file is opened
                md = self.player.get_metadata()
                if md and md.get("duration"):
                    break
                time.sleep(0.05)
            if md and md.get("duration"):
                print(f"[audio] ready (duration {md['duration']:.1f}s)")
            else:
                print("[audio] WARNING: could not read audio info - the file may have no sound track")
        except Exception as e:
            print(f"[audio] sound disabled: {e}")
            print("[audio] install it with:  python -m pip install ffpyplayer")
            self.player = None

    @property
    def ok(self):
        return self.player is not None

    def play(self, pos):
        if self.ok:
            self.player.seek(pos, relative=False, accurate=True)
            self.player.set_pause(False)

    def pause(self):
        if self.ok:
            self.player.set_pause(True)

    def seek(self, pos):
        if self.ok:
            self.player.seek(pos, relative=False, accurate=True)

    def pts(self):
        return self.player.get_pts() if self.ok else 0.0

    def close(self):
        if self.ok:
            try:
                self.player.close_player()
            except Exception:
                pass
            self.player = None
