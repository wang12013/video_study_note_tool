from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPlainTextEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from video_notes.app.dialogs.note_preview import NotePreviewDialog
from video_notes.app.workers import BuildWorker
from video_notes.core.config import Store
from video_notes.core.library import LibraryStore
from video_notes.pipeline.runner import safe_name

STATUS_TEXT = {
    "pending": "待生成",
    "running": "生成中",
    "done": "已完成",
    "failed": "失败",
}


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class CoursePage(QWidget):
    back = Signal()

    def __init__(self, library: LibraryStore, settings: Store, course_id: int) -> None:
        super().__init__()
        self.library = library
        self.settings = settings
        self.course_id = course_id
        self.course = library.get_course(course_id) or {}
        self.videos = library.list_videos(course_id)
        self.course_dir = self._course_dir()
        self.worker: BuildWorker | None = None
        self._build_videos: list[dict] = []
        self._build_index: dict[int, int] = {}

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 24, 32, 24)
        layout.setSpacing(10)

        header = QHBoxLayout()
        back_button = QPushButton("← 返回")
        back_button.setFixedWidth(80)
        back_button.clicked.connect(self.back.emit)
        title = QLabel(self.course.get("title") or "课程")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        header.addWidget(back_button)
        header.addWidget(title, 1)
        self.start_button = QPushButton("开始生成")
        self.start_button.setFixedWidth(100)
        self.start_button.clicked.connect(self.start_build)
        self.stop_button = QPushButton("停止")
        self.stop_button.setFixedWidth(70)
        self.stop_button.setEnabled(False)
        self.stop_button.clicked.connect(self.stop_build)
        open_dir = QPushButton("打开课程目录")
        open_dir.setFixedWidth(110)
        open_dir.clicked.connect(self.open_output_dir)
        header.addWidget(self.start_button)
        header.addWidget(self.stop_button)
        header.addWidget(open_dir)
        layout.addLayout(header)

        meta = QLabel(
            f"{len(self.videos)} 个视频 · 来源：{'B 站' if self.course.get('source_type') == 'bilibili' else '本地'}"
            f" · 输出目录：{self.settings.get('output_dir') or '默认'}"
        )
        meta.setStyleSheet("color: #6b7280;")
        layout.addWidget(meta)

        self.table = QTableWidget(0, 5)
        self.table.setHorizontalHeaderLabels(["#", "标题", "时长", "状态", "笔记"])
        self.table.horizontalHeader().setSectionResizeMode(1, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self.table.cellDoubleClicked.connect(self._open_note)
        layout.addWidget(self.table, 1)

        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(2000)
        self.log.setFixedHeight(150)
        self.log.setStyleSheet("font-family: Consolas, 'Microsoft YaHei UI'; font-size: 12px;")
        layout.addWidget(self.log)

        self._fill_table()

    def _course_dir(self) -> Path:
        base = Path(self.settings.get("output_dir") or (Path.home() / "Documents" / "VideoNotes"))
        return base / safe_name(self.course.get("title") or "未命名课程")

    def _write_index(self) -> None:
        self.course_dir.mkdir(parents=True, exist_ok=True)
        lines = [f"### {self.course.get('title') or '未命名课程'}", ""]
        description = (self.course.get("description") or "").strip()
        if description:
            lines += [description, ""]
        lines.append(f"共 {len(self.videos)} 讲。")
        lines.append("")
        for index, video in enumerate(self.videos, 1):
            title = video.get("title") or f"第 {index} 讲"
            note_path = video.get("note_path") or ""
            summary = (video.get("description") or "").strip().replace("\n", " ")
            summary = summary[:60]
            suffix = f" —— {summary}" if summary else ""
            link = ""
            if note_path and Path(note_path).exists():
                try:
                    rel = Path(note_path).parent.relative_to(self.course_dir).as_posix()
                    link = f"[{title}]({rel}/notes.md)"
                except ValueError:
                    link = ""
            lines.append(f"{index}. {link or title}{suffix}")
        (self.course_dir / "index.md").write_text("\n".join(lines) + "\n", encoding="utf-8")

    def _fill_table(self) -> None:
        self.table.setRowCount(0)
        for index, video in enumerate(self.videos):
            row = self.table.rowCount()
            self.table.insertRow(row)
            values = [
                str(index + 1),
                video.get("title") or "",
                _fmt_duration(video.get("duration") or 0),
                STATUS_TEXT.get(video.get("status") or "pending", video.get("status") or ""),
                "打开" if video.get("note_path") else "",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                item.setData(Qt.ItemDataRole.UserRole, video["id"])
                self.table.setItem(row, column, item)

    def _set_status(self, row: int, text: str) -> None:
        item = self.table.item(row, 3)
        if item:
            item.setText(text)

    def _items(self) -> tuple[list[dict], list[dict]]:
        items = []
        videos = []
        for index, video in enumerate(self.videos):
            if video.get("status") == "done" and video.get("note_path"):
                continue
            source = video.get("local_path") or video.get("source_url")
            if not source:
                continue
            folder = f"{index + 1:02d}-{safe_name(video.get('title') or '未命名')}"
            items.append(
                {"source": source, "title": video.get("title") or "", "folder_name": folder}
            )
            videos.append(video)
        return items, videos

    def start_build(self) -> None:
        if self.worker is not None and self.worker.isRunning():
            return
        items, videos = self._items()
        if not items:
            QMessageBox.information(self, "提示", "没有待生成的视频。")
            return
        self._build_videos = videos
        self._build_index = {id(video): index for index, video in enumerate(self.videos)}
        self.start_button.setEnabled(False)
        self.stop_button.setEnabled(True)
        self.worker = BuildWorker(items, self.settings, str(self.course_dir))
        self.worker.video_started.connect(self._on_video_started)
        self.worker.log.connect(self._on_log)
        self.worker.video_done.connect(self._on_video_done)
        self.worker.video_failed.connect(self._on_video_failed)
        self.worker.finished_all.connect(self._on_finished)
        self.worker.start()

    def stop_build(self) -> None:
        if self.worker is not None:
            self.worker.stop()
            self.stop_button.setEnabled(False)
            self._on_log("已请求停止，当前视频完成后停止")

    def _on_video_started(self, index: int, title: str) -> None:
        video = self._build_videos[index]
        self.library.update_video(video["id"], status="running", error="")
        self._set_status(self._build_index[id(video)], "生成中")
        self._on_log(f"[{index + 1}/{len(self._build_videos)}] 开始：{title}")

    def _on_log(self, message: str) -> None:
        self.log.appendPlainText(message)

    def _on_video_done(self, index: int, title: str, notes_path: str) -> None:
        video = self._build_videos[index]
        self.library.update_video(video["id"], status="done", note_path=notes_path, progress=1.0)
        video["status"] = "done"
        video["note_path"] = notes_path
        row = self._build_index[id(video)]
        self._set_status(row, "已完成")
        note_item = self.table.item(row, 4)
        if note_item:
            note_item.setText("打开")
        self._on_log(f"完成：{title} → {notes_path}")

    def _on_video_failed(self, index: int, error: str) -> None:
        video = self._build_videos[index]
        self.library.update_video(video["id"], status="failed", error=error)
        video["status"] = "failed"
        row = self._build_index[id(video)]
        self._set_status(row, "失败")
        self._on_log(f"失败：{video.get('title')} - {error}")

    def _on_finished(self) -> None:
        self.start_button.setEnabled(True)
        self.stop_button.setEnabled(False)
        self._on_log("队列处理结束")
        self.videos = self.library.list_videos(self.course_id)
        self._fill_table()
        self._write_index()
        self._on_log(f"课程总览：{self.course_dir / 'index.md'}")

    def _open_note(self, row: int, _column: int) -> None:
        if row >= len(self.videos):
            return
        note_path = self.videos[row].get("note_path") or ""
        if note_path and Path(note_path).exists():
            NotePreviewDialog(Path(note_path), self).exec()
        else:
            QMessageBox.information(self, "提示", "这条视频还没有生成笔记。")

    def open_output_dir(self) -> None:
        folder = self.course_dir
        try:
            folder.mkdir(parents=True, exist_ok=True)
            os.startfile(folder)
        except OSError as exc:
            QMessageBox.warning(self, "打不开目录", str(exc))