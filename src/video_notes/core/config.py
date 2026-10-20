from __future__ import annotations

import os
import sqlite3
import threading
from pathlib import Path
from typing import Any

from . import paths, secrets

DEFAULTS: dict[str, str] = {
    "output_dir": "",
    "course_index": "true",
    "concurrency": "1",
    "max_height": "1080",
    "max_slides": "150",
    "max_images_per_section": "1",
    "retry": "3",
    "language": "zh",
    "deepseek_base_url": "https://api.deepseek.com",
    "deepseek_model": "deepseek-flash",
    "dashscope_region": "beijing",
    "asr_model": "qwen3-asr-flash",
    "vlm_model": "qwen3-vl-plus",
}

SECRET_KEYS = ("deepseek_api_key", "dashscope_api_key", "bilibili_cookie")

SECRET_ENV = {
    "deepseek_api_key": "DEEPSEEK_API_KEY",
    "dashscope_api_key": "DASHSCOPE_API_KEY",
}


class Store:
    """SQLite-backed settings and DPAPI-encrypted secrets."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (paths.app_data_dir() / "app.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        self._conn.execute(
            "CREATE TABLE IF NOT EXISTS secrets (key TEXT PRIMARY KEY, value_enc BLOB)"
        )
        self._conn.commit()

    # settings ---------------------------------------------------------
    def get(self, key: str, default: str | None = None) -> str | None:
        with self._lock:
            row = self._conn.execute(
                "SELECT value FROM settings WHERE key = ?", (key,)
            ).fetchone()
        if row is not None:
            return row[0]
        if default is not None:
            return default
        return DEFAULTS.get(key)

    def set(self, key: str, value: str) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT INTO settings(key, value) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
                (key, value),
            )
            self._conn.commit()

    def all_settings(self) -> dict[str, str]:
        with self._lock:
            rows = self._conn.execute("SELECT key, value FROM settings").fetchall()
        return {k: v for k, v in rows}

    # secrets ----------------------------------------------------------
    def set_secret(self, key: str, value: str) -> None:
        token = secrets.protect(value) if value else ""
        with self._lock:
            self._conn.execute(
                "INSERT INTO secrets(key, value_enc) VALUES(?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value_enc = excluded.value_enc",
                (key, token),
            )
            self._conn.commit()

    def get_secret(self, key: str, allow_env: bool = True) -> str:
        with self._lock:
            row = self._conn.execute(
                "SELECT value_enc FROM secrets WHERE key = ?", (key,)
            ).fetchone()
        if row is not None and row[0]:
            try:
                return secrets.unprotect(row[0])
            except OSError:
                return ""
        env_name = SECRET_ENV.get(key)
        if allow_env and env_name:
            return os.environ.get(env_name, "")
        return ""

    def has_secret(self, key: str) -> bool:
        return bool(self.get_secret(key))

    def secret_keys(self) -> list[str]:
        with self._lock:
            rows = self._conn.execute("SELECT key FROM secrets WHERE value_enc != ''").fetchall()
        keys = [r[0] for r in rows]
        for key, env in SECRET_ENV.items():
            if key not in keys and os.environ.get(env):
                keys.append(key)
        return keys

    def delete_secret(self, key: str) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM secrets WHERE key = ?", (key,))
            self._conn.commit()

    def close(self) -> None:
        with self._lock:
            self._conn.close()