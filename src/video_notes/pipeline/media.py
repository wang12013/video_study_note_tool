from __future__ import annotations

import re
import subprocess
from pathlib import Path

from ..core import paths

_DURATION_RE = re.compile(r"Duration:\s*(\d+):(\d+):(\d+\.?\d*)")


class MediaError(RuntimeError):
    pass


def _run(args: list[str], timeout: float = 600) -> subprocess.CompletedProcess:
    result = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="ignore", timeout=timeout)
    if result.returncode != 0:
        tail = (result.stderr or result.stdout or "")[-800:]
        raise MediaError(f"命令失败: {' '.join(args[:3])}...\n{tail}")
    return result


def extract_audio(video: Path, audio: Path, sample_rate: int = 16000) -> Path:
    audio.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            paths.ffmpeg_path(),
            "-y",
            "-i",
            str(video),
            "-vn",
            "-ac",
            "1",
            "-ar",
            str(sample_rate),
            "-c:a",
            "pcm_s16le",
            str(audio),
        ]
    )
    if not audio.exists() or audio.stat().st_size < 1000:
        raise MediaError("音轨提取失败：输出为空")
    return audio


def probe_duration(media: Path) -> float:
    result = subprocess.run(
        [paths.ffmpeg_path(), "-i", str(media)],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="ignore",
        timeout=120,
    )
    match = _DURATION_RE.search(result.stderr or "")
    if not match:
        raise MediaError(f"无法读取时长: {media}")
    hours, minutes, seconds = match.groups()
    return int(hours) * 3600 + int(minutes) * 60 + float(seconds)


def extract_frames(video: Path, out_dir: Path, fps: float = 1.0, width: int = 480) -> list[Path]:
    """Extract downscaled frames in one ffmpeg pass. Returns sorted frame paths."""
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("f_*.jpg"):
        old.unlink()
    _run(
        [
            paths.ffmpeg_path(),
            "-y",
            "-i",
            str(video),
            "-vf",
            f"fps={fps},scale={width}:-1",
            "-q:v",
            "4",
            str(out_dir / "f_%05d.jpg"),
        ],
        timeout=1800,
    )
    return sorted(out_dir.glob("f_*.jpg"))


def extract_frame_at(video: Path, seconds: float, out_path: Path) -> Path:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    _run(
        [
            paths.ffmpeg_path(),
            "-y",
            "-ss",
            f"{seconds:.3f}",
            "-i",
            str(video),
            "-frames:v",
            "1",
            str(out_path),
        ],
        timeout=120,
    )
    if not out_path.exists() or out_path.stat().st_size == 0:
        raise MediaError(f"抽帧失败: {seconds:.1f}s")
    return out_path
