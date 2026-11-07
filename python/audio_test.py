"""Run this to test sound only:  python audio_test.py   (plays videos/video.mp4 audio for 8 seconds)"""
import os, sys, time
path = sys.argv[1] if len(sys.argv) > 1 else os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "videos", "video.mp4")
print("File:", os.path.abspath(path), "exists:", os.path.isfile(path))
try:
    from ffpyplayer.player import MediaPlayer
    print("ffpyplayer imported OK")
except Exception as e:
    print("ffpyplayer NOT installed/working:", e)
    print("Fix:  python -m pip install ffpyplayer")
    sys.exit(1)
p = MediaPlayer(path, ff_opts={"vn": True, "sn": True})
for i in range(8):
    time.sleep(1)
    print(f"playing... pts={p.get_pts():.1f}s  (do you hear sound?)")
p.close_player()
