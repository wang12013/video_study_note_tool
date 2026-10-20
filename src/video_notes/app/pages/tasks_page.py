from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget


class TasksPage(QWidget):
    def __init__(self) -> None:
        super().__init__()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(32, 28, 32, 28)
        title = QLabel("任务中心")
        title.setStyleSheet("font-size: 20px; font-weight: 600;")
        hint = QLabel("下载、转写、课件识别的进度会显示在这里。")
        hint.setStyleSheet("color: #6b7280;")
        hint.setAlignment(Qt.AlignmentFlag.AlignTop)
        layout.addWidget(title)
        layout.addWidget(hint)
        layout.addStretch(1)
