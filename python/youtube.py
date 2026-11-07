"""Download a YouTube video (low resolution, with sound) into the videos/ folder using yt-dlp."""
import glob
import os


def is_url(text: str) -> bool:
    return text.strip().lower().startswith(("http://", "https://", "www.", "youtu.be/", "youtube.com/"))


def download(url: str, out_dir: str, max_height: int = 480) -> str:
    """Return the local file path. Already-downloaded videos are reused (no second download)."""
    try:
        import yt_dlp
    except ImportError:
        raise RuntimeError("yt-dlp is not installed. Run:  python -m pip install -U yt-dlp")

    url = url.strip()
    if url.lower().startswith(("www.", "youtu.be/", "youtube.com/")):
        url = "https://" + url
    os.makedirs(out_dir, exist_ok=True)

    opts = {
        # prefer H.264 (OpenCV can decode it), small size, audio+video merged into mp4
        "format": (f"bv*[height<={max_height}][vcodec^=avc1]+ba[ext=m4a]/"
                   f"b[height<={max_height}][ext=mp4]/b[height<={max_height}]/b"),
        "merge_output_format": "mp4",
        "outtmpl": os.path.join(out_dir, "youtube_%(id)s.%(ext)s"),
        "noplaylist": True,
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [_progress],
    }
    try:                                    # bundled ffmpeg (needed to merge audio + video)
        import imageio_ffmpeg
        opts["ffmpeg_location"] = imageio_ffmpeg.get_ffmpeg_exe()
    except Exception:
        pass

    with yt_dlp.YoutubeDL(opts) as ydl:
        info = ydl.extract_info(url, download=False)
        if info.get("is_live"):
            raise RuntimeError("Live streams are not supported. Use a normal video.")
        vid = info["id"]
        print(f"[youtube] {info.get('title', vid)}")
        existing = [p for p in glob.glob(os.path.join(out_dir, f"youtube_{vid}.*"))
                    if p.lower().endswith((".mp4", ".mkv", ".webm"))]
        if existing:
            print("[youtube] already downloaded, reusing file")
            return existing[0]
        ydl.download([url])

    files = [p for p in glob.glob(os.path.join(out_dir, f"youtube_{vid}.*"))
             if p.lower().endswith((".mp4", ".mkv", ".webm"))]
    if not files:
        raise RuntimeError("Download finished but the file was not found.")
    print()
    return files[0]


def _progress(d):
    if d.get("status") == "downloading":
        pct = d.get("_percent_str", "").strip()
        print(f"\r[youtube] downloading {pct}   ", end="", flush=True)
