from __future__ import annotations

import sqlite3
import threading
from datetime import datetime
from pathlib import Path

from . import paths

SCHEMA = """
CREATE TABLE IF NOT EXISTS courses (
    id INTEGER PRIMARY KEY,
    title TEXT NOT NULL,
    source_type TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    description TEXT DEFAULT '',
    output_dir TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS videos (
    id INTEGER PRIMARY KEY,
    course_id INTEGER NOT NULL,
    seq INTEGER DEFAULT 0,
    title TEXT DEFAULT '',
    description TEXT DEFAULT '',
    source_url TEXT DEFAULT '',
    local_path TEXT DEFAULT '',
    duration REAL DEFAULT 0,
    status TEXT DEFAULT 'pending',
    progress REAL DEFAULT 0,
    error TEXT DEFAULT '',
    note_path TEXT DEFAULT '',
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_videos_course ON videos(course_id);
"""


def _now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class LibraryStore:
    def __init__(self, path: Path | None = None) -> None:
        self.path = path or (paths.app_data_dir() / "app.db")
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.executescript(SCHEMA)
        self._conn.commit()
        columns = [row[1] for row in self._conn.execute("PRAGMA table_info(videos)").fetchall()]
        if "description" not in columns:
            self._conn.execute("ALTER TABLE videos ADD COLUMN description TEXT DEFAULT ''")
            self._conn.commit()

    # courses ---------------------------------------------------------
    def add_course(
        self,
        title: str,
        source_type: str = "",
        source_url: str = "",
        description: str = "",
        output_dir: str = "",
    ) -> int:
        now = _now()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO courses(title, source_type, source_url, description, output_dir, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?)",
                (title, source_type, source_url, description, output_dir, now, now),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_courses(self) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                """
                SELECT c.*,
                       (SELECT COUNT(*) FROM videos v WHERE v.course_id = c.id) AS video_count,
                       (SELECT COUNT(*) FROM videos v WHERE v.course_id = c.id AND v.status = 'done') AS done_count
                FROM courses c ORDER BY c.created_at DESC
                """
            ).fetchall()
        return [dict(row) for row in rows]

    def get_course(self, course_id: int) -> dict | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM courses WHERE id = ?", (course_id,)).fetchone()
        return dict(row) if row else None

    def delete_course(self, course_id: int) -> None:
        with self._lock:
            self._conn.execute("DELETE FROM videos WHERE course_id = ?", (course_id,))
            self._conn.execute("DELETE FROM courses WHERE id = ?", (course_id,))
            self._conn.commit()

    # videos ----------------------------------------------------------
    def add_video(
        self,
        course_id: int,
        seq: int,
        title: str,
        description: str = "",
        source_url: str = "",
        local_path: str = "",
        duration: float = 0,
    ) -> int:
        now = _now()
        with self._lock:
            cursor = self._conn.execute(
                "INSERT INTO videos(course_id, seq, title, description, source_url, local_path, duration, created_at, updated_at) "
                "VALUES(?,?,?,?,?,?,?,?,?)",
                (course_id, seq, title, description, source_url, local_path, duration, now, now),
            )
            self._conn.commit()
            return int(cursor.lastrowid)

    def list_videos(self, course_id: int) -> list[dict]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM videos WHERE course_id = ? ORDER BY seq, id", (course_id,)
            ).fetchall()
        return [dict(row) for row in rows]

    def update_video(
        self,
        video_id: int,
        status: str | None = None,
        note_path: str | None = None,
        error: str | None = None,
        progress: float | None = None,
    ) -> None:
        fields = []
        values: list = []
        if status is not None:
            fields.append("status = ?")
            values.append(status)
        if note_path is not None:
            fields.append("note_path = ?")
            values.append(note_path)
        if error is not None:
            fields.append("error = ?")
            values.append(error)
        if progress is not None:
            fields.append("progress = ?")
            values.append(progress)
        if not fields:
            return
        fields.append("updated_at = ?")
        values.append(_now())
        values.append(video_id)
        with self._lock:
            self._conn.execute(f"UPDATE videos SET {', '.join(fields)} WHERE id = ?", values)
            self._conn.commit()

    def reset_course(self, course_id: int) -> None:
        with self._lock:
            self._conn.execute(
                "UPDATE videos SET status = 'pending', error = '', progress = 0 WHERE course_id = ?",
                (course_id,),
            )
            self._conn.commit()