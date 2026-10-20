from __future__ import annotations

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QStatusBar,
    QVBoxLayout,
    QWidget,
)

from video_notes.core.config import Store
from video_notes.core.library import LibraryStore

from .pages.course_page import CoursePage
from .pages.library_page import LibraryPage
from .pages.settings_page import SettingsPage
from .pages.tasks_page import TasksPage

SIDEBAR_QSS = """
#sidebar { background: #1f2430; }
#appTitle { color: #f2f4f8; font-size: 17px; font-weight: 600; padding: 18px 16px 6px 16px; }
#appSubtitle { color: #8b93a7; font-size: 11px; padding: 0 16px 16px 16px; }
QListWidget { background: transparent; border: none; color: #c9d1e0; outline: none; padding: 6px; }
QListWidget::item { padding: 10px 12px; border-radius: 6px; margin: 2px 6px; }
QListWidget::item:selected { background: #313b52; color: #ffffff; }
QListWidget::item:hover { background: #272f42; }
"""


class MainWindow(QMainWindow):
    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("VideoNotes - 视频转学习笔记")
        self.resize(1160, 760)

        self.settings = Store()
        self.library = LibraryStore()

        root = QWidget()
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(190)
        sidebar.setStyleSheet(SIDEBAR_QSS)
        side_layout = QVBoxLayout(sidebar)
        side_layout.setContentsMargins(0, 0, 0, 0)
        side_layout.setSpacing(0)

        title = QLabel("VideoNotes")
        title.setObjectName("appTitle")
        subtitle = QLabel("视频 → 结构化学习笔记")
        subtitle.setObjectName("appSubtitle")
        side_layout.addWidget(title)
        side_layout.addWidget(subtitle)

        self.nav = QListWidget()
        for name in ("课程库", "任务中心", "设置"):
            QListWidgetItem(name, self.nav)
        self.nav.setCurrentRow(0)
        side_layout.addWidget(self.nav, 1)

        self.stack = QStackedWidget()
        self.library_page = LibraryPage(self.library, self.settings)
        self.tasks_page = TasksPage()
        self.settings_page = SettingsPage()
        self.stack.addWidget(self.library_page)
        self.stack.addWidget(self.tasks_page)
        self.stack.addWidget(self.settings_page)

        self.library_page.course_opened.connect(self.open_course)

        layout.addWidget(sidebar)
        layout.addWidget(self.stack, 1)
        self.setCentralWidget(root)

        self.nav.currentRowChanged.connect(self._on_nav)
        self.setStatusBar(QStatusBar())
        self.show_page(0)

    def _on_nav(self, index: int) -> None:
        if index == 0:
            self.library_page.refresh()
        self.stack.setCurrentIndex(index)

    def show_page(self, index: int) -> None:
        self.nav.setCurrentRow(index)

    def open_course(self, course_id: int) -> None:
        page = CoursePage(self.library, self.settings, course_id)
        page.back.connect(lambda: self.close_course(page))
        self.stack.addWidget(page)
        self.stack.setCurrentWidget(page)

    def close_course(self, page: CoursePage) -> None:
        self.stack.setCurrentWidget(self.library_page)
        self.stack.removeWidget(page)
        page.deleteLater()
        self.library_page.refresh()