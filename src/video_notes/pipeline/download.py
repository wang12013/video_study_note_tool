from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from ..core import paths
from ..core.config import Store
from ..ingest.bilibili import VideoRef


class DownloadError(RuntimeError):
    pass


def _ytdlp_command() -> list[str]:
    if getattr(sys, "frozen", False):
        return [str(paths.runtime_dir() / "yt-dlp.exe")]
    return [sys.executable, "-m", "yt_dlp"]


def download_video(ref: VideoRef, dest_dir: Path, store: Store, progress=print) -> Path:
    dest_dir.mkdir(parents=True, exist_ok=True)
    output = dest_dir / "video.%(ext)s"

    cookie_text = store.get_secret("bilibili_cookie")
    cookie_file = None
    if cookie_text.strip().startswith("# Netscape") or "\t" in cookie_text:
        cookie_file = dest_dir / "cookies.txt"
        cookie_file.write_text(cookie_text, encoding="utf-8")

    height = store.get("max_height") or "1080"
    retries = int(store.get("retry") or 0)
    command = _ytdlp_command() + [
        "--no-playlist",
        "--no-warnings",
        "--ffmpeg-location",
        str(paths.runtime_dir()),
        "-f",
        f"bv*[height<={height}][vcodec^=avc]+ba/b[height<={height}]",
        "--merge-output-format",
        "mp4",
        "-o",
        str(output),
    ]
    if cookie_file:
        command += ["--cookies", str(cookie_file)]
    command.append(ref.url)

    last = ""
    for attempt in range(max(1, retries + 1)):
        progress(f"下载视频（第 {attempt + 1} 次）")
        result = subprocess.run(
            command,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="ignore",
            timeout=3600,
        )
        if result.returncode == 0:
            candidates = sorted(dest_dir.glob("video.*"))
            candidates = [c for c in candidates if c.suffix.lower() in (".mp4", ".mkv", ".webm", ".flv")]
            if candidates:
                if cookie_file:
                    cookie_file.unlink(missing_ok=True)
                return candidates[0]
        last = (result.stderr or "")[-600:]
    raise DownloadError(f"下载失败：{last}")