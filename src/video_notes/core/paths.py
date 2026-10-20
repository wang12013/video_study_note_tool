from __future__ import annotations

import os
import sys
from pathlib import Path

APP_NAME = "VideoNotes"


def _home_override() -> Path | None:
    value = os.environ.get("VNOTE_HOME")
    return Path(value) if value else None


def app_data_dir() -> Path:
    override = _home_override()
    if override is not None:
        override.mkdir(parents=True, exist_ok=True)
        return override
    base = os.environ.get("APPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Roaming"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def local_data_dir() -> Path:
    override = _home_override()
    if override is not None:
        override.mkdir(parents=True, exist_ok=True)
        return override
    base = os.environ.get("LOCALAPPDATA")
    root = Path(base) if base else Path.home() / "AppData" / "Local"
    path = root / APP_NAME
    path.mkdir(parents=True, exist_ok=True)
    return path


def cache_dir() -> Path:
    path = local_data_dir() / "cache"
    path.mkdir(parents=True, exist_ok=True)
    return path


def logs_dir() -> Path:
    path = local_data_dir() / "logs"
    path.mkdir(parents=True, exist_ok=True)
    return path


def default_library_dir() -> Path:
    return Path.home() / "Documents" / APP_NAME


def runtime_dir() -> Path:
    override = os.environ.get("VNOTE_RUNTIME_DIR")
    if override:
        return Path(override)
    if getattr(sys, "frozen", False):
        meipass = getattr(sys, "_MEIPASS", None)
        if meipass:
            candidate = Path(meipass) / "runtime"
            if candidate.exists():
                return candidate
        return Path(sys.executable).parent / "runtime"
    return Path(__file__).resolve().parents[3] / "runtime"


def ffmpeg_path() -> str:
    exe = runtime_dir() / "ffmpeg.exe"
    return str(exe) if exe.exists() else "ffmpeg"


def ffprobe_path() -> str:
    exe = runtime_dir() / "ffprobe.exe"
    return str(exe) if exe.exists() else "ffprobe"