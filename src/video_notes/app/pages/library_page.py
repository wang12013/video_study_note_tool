from __future__ import annotations

import os
from datetime import datetime
from pathlib import Path

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFileDialog,
    QHBoxLayout,
    QHeaderView,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMenu,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from video_notes.core.config import Store
from video_notes.core.library import LibraryStore
from video_notes.ingest.bilibili import BilibiliClient


def _fmt_duration(seconds: float) -> str:
    seconds = int(seconds or 0)
    hours, rem = divmod(seconds, 3600)
    minutes, secs = divmod(rem, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{secs:02d}"
    return f"{minutes}:{secs:02d}"


class _EnumerateThread(QThread):
    done = Signal(object, object)
    failed = Signal(str)

    def __init__(self, url: str, cookie: str) -> None:
        super().__init__()
        self.url = url
        self.cookie = cookie

    def run(self) -> None:
        client = BilibiliClient(cookie=self.cookie)
        try:
            season, refs = client.enumerate(self.url)
            self.done.emit(season, refs)
        except Exception as exc:  # noqa: BLE001
            self.failed.emit(str(exc))
        finally:
            client.close()


class LibraryPage(QWidget):
    course_opened = Signal(int)

    def __init__(self, library: LibraryStore, settings: Store) -> None:
        super().__init__()
        self.library = library
        self.settings = settings
        self._season = None
        self._refs: list = []

        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 24)
        layout.setSpacing(10)

        title = QLabel("课程库")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        subtitle = QLabel("粘贴 B 站视频/合集链接，或导入本地视频，然后开始生成笔记。")
        subtitle.setStyleSheet("color: #6b7280;")
        layout.addWidget(title)
        layout.addWidget(subtitle)

        row = QHBoxLayout()
        self.input = QLineEdit()
        self.input.setPlaceholderText("https://space.bilibili.com/317080675/lists/4878258?type=season")
        self.parse_button = QPushButton("解析")
        self.parse_button.setFixedWidth(80)
        self.import_button = QPushButton("导入课程")
        self.import_button.setFixedWidth(100)
        self.import_button.setEnabled(False)
        self.local_button = QPushButton("导入本地视频")
        self.local_button.setFixedWidth(120)
        row.addWidget(self.input, 1)
        row.addWidget(self.parse_button)
        row.addWidget(self.import_button)
        row.addWidget(self.local_button)
        layout.addLayout(row)

        self.status = QLabel("")
        self.status.setStyleSheet("color: #6b7280;")
        layout.addWidget(self.status)

        hint = QLabel("提示：双击课程行，或点右侧「打开」进入课程详情。")
        hint.setStyleSheet("color: #9ca3af; font-size: 11px;")
        layout.addWidget(hint)

        self.table = QTableWidget(0, 6)
        self.table.setHorizontalHeaderLabels(["课程", "来源", "视频数", "已完成", "创建时间", "操作"])
        self.table.horizontalHeader().setSectionResizeMode(0, QHeaderView.ResizeMode.Stretch)
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        layout.addWidget(self.table, 1)

        self.parse_button.clicked.connect(self._start_parse)
        self.input.returnPressed.connect(self._start_parse)
        self.import_button.clicked.connect(self._import_course)
        self.local_button.clicked.connect(self._import_local)
        self.table.cellDoubleClicked.connect(self._open_row)
        self.table.cellClicked.connect(self._on_cell_clicked)
        self.table.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.table.customContextMenuRequested.connect(self._context_menu)

        self.refresh()

    def refresh(self) -> None:
        courses = self.library.list_courses()
        self.table.setRowCount(0)
        for course in courses:
            row = self.table.rowCount()
            self.table.insertRow(row)
            created = str(course.get("created_at") or "").replace("T", " ")[:16]
            values = [
                course.get("title") or "",
                "B 站" if course.get("source_type") == "bilibili" else "本地",
                f"{course.get('done_count', 0)}/{course.get('video_count', 0)}",
                str(course.get("done_count", 0)),
                created,
                "打开",
            ]
            for column, value in enumerate(values):
                item = QTableWidgetItem(value)
                if column == 0:
                    item.setData(Qt.ItemDataRole.UserRole, course["id"])
                self.table.setItem(row, column, item)

    def _start_parse(self) -> None:
        url = self.input.text().strip()
        if not url:
            self.status.setText("请先粘贴链接")
            return
        self.parse_button.setEnabled(False)
        self.import_button.setEnabled(False)
        self.status.setText("解析中…")
        cookie = self.settings.get_secret("bilibili_cookie") or ""
        self._thread = _EnumerateThread(url, cookie)
        self._thread.done.connect(self._on_parsed)
        self._thread.failed.connect(self._on_parse_failed)
        self._thread.start()

    def _on_parsed(self, season, refs) -> None:
        self.parse_button.setEnabled(True)
        self._season = season
        self._refs = list(refs)
        total = sum(ref.duration for ref in refs)
        name = getattr(season, "title", "") or "视频"
        self.status.setText(f"解析成功：{name}，{len(refs)} 个视频，总时长 {_fmt_duration(total)}")
        self.import_button.setEnabled(bool(refs))

    def _on_parse_failed(self, message: str) -> None:
        self.parse_button.setEnabled(True)
        self.status.setText(f"解析失败：{message}")

    def _import_course(self) -> None:
        if not self._refs:
            return
        name = getattr(self._season, "title", "") or "未命名课程"
        description = getattr(self._season, "intro", "") or ""
        source_url = self.input.text().strip()
        duplicated = [
            course
            for course in self.library.list_courses()
            if course.get("source_url") == source_url and course.get("title") == name
        ]
        if duplicated:
            answer = QMessageBox.question(
                self,
                "课程已存在",
                f"已经导入过这个链接（{duplicated[0].get('title')}），仍要再导入一份吗？",
            )
            if answer != QMessageBox.StandardButton.Yes:
                return
        output_dir = self.settings.get("output_dir") or ""
        course_id = self.library.add_course(
            title=name,
            source_type="bilibili",
            source_url=source_url,
            description=description,
            output_dir=output_dir,
        )
        for index, ref in enumerate(self._refs):
            self.library.add_video(
                course_id,
                index,
                ref.title,
                description=ref.desc,
                source_url=ref.url,
                duration=ref.duration,
            )
        self._refs = []
        self._season = None
        self.import_button.setEnabled(False)
        self.status.setText(f"已导入课程：{name}")
        self.refresh()
        self.course_opened.emit(course_id)

    def _import_local(self) -> None:
        paths, _ = QFileDialog.getOpenFileNames(
            self,
            "选择本地视频",
            "",
            "视频文件 (*.mp4 *.mkv *.flv *.mov *.webm *.avi);;所有文件 (*.*)",
        )
        if not paths:
            return
        default_name = "本地视频 " + datetime.now().strftime("%m%d %H%M")
        name, ok = QInputDialog.getText(self, "课程名称", "给这批本地视频起个名字：", text=default_name)
        if not ok or not name.strip():
            return
        course_id = self.library.add_course(
            title=name.strip(),
            source_type="local",
            output_dir=self.settings.get("output_dir") or "",
        )
        for index, path in enumerate(paths):
            self.library.add_video(course_id, index, Path(path).stem, local_path=path)
        self.status.setText(f"已导入 {len(paths)} 个本地视频")
        self.refresh()
        self.course_opened.emit(course_id)

    def _context_menu(self, position) -> None:
        item = self.table.itemAt(position)
        if item is None:
            return
        row = item.row()
        name = self.table.item(row, 0).text() if self.table.item(row, 0) else "课程"
        menu = QMenu(self)
        open_action = menu.addAction("打开课程")
        delete_action = menu.addAction("删除课程记录")
        chosen = menu.exec(self.table.viewport().mapToGlobal(position))
        if chosen is open_action:
            self._open_row(row, 0)
        elif chosen is delete_action:
            answer = QMessageBox.question(
                self,
                "删除课程",
                f"确定删除课程「{name}」吗？\n只删除记录，已生成的笔记文件不会删除。",
            )
            if answer == QMessageBox.StandardButton.Yes:
                course_id = self.table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if course_id:
                    self.library.delete_course(int(course_id))
                    self.refresh()

    def _on_cell_clicked(self, row: int, column: int) -> None:
        if column == 5:
            self._open_row(row, column)

    def _open_row(self, row: int, _column: int) -> None:
        item = self.table.item(row, 0)
        if item is None:
            return
        course_id = item.data(Qt.ItemDataRole.UserRole)
        if course_id:
            self.course_opened.emit(int(course_id))