from __future__ import annotations

import os
import re
from pathlib import Path

import markdown as md_render

from PySide6.QtCore import QUrl
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
)


class NotePreviewDialog(QDialog):
    def __init__(self, notes_path: Path, parent=None) -> None:
        super().__init__(parent)
        self.notes_path = Path(notes_path)
        self.setWindowTitle(f"笔记预览 - {self.notes_path.parent.name}")
        self.resize(980, 760)

        layout = QVBoxLayout(self)
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setFont(QFont("Microsoft YaHei UI", 10))
        folder = self.notes_path.parent
        self.browser.setSearchPaths([str(folder)])
        self.browser.document().setBaseUrl(QUrl.fromLocalFile(str(folder) + os.sep))
        try:
            markdown = self.notes_path.read_text(encoding="utf-8")
        except OSError as exc:
            markdown = f"读取失败：{exc}"
        markdown = re.sub(
            r"!\[([^\]]*)\]\(([^)]+)\)",
            lambda match: '<img src="' + match.group(2) + '" alt="' + match.group(1) + '" width="820" />',
            markdown,
        )
        self.browser.document().setDefaultStyleSheet(
            "h3 { font-size: 22px; font-weight: 600; margin-top: 16px; } "
            "h4 { font-size: 17px; font-weight: 600; margin-top: 18px; } "
            "p { margin-top: 8px; margin-bottom: 8px; } "
            "blockquote { color: #4b5563; border-left: 3px solid #d1d5db; padding-left: 10px; } "
            "li { margin-top: 4px; }"
        )
        self.browser.setHtml(md_render.markdown(markdown, extensions=["extra"]))
        layout.addWidget(self.browser, 1)

        buttons = QHBoxLayout()
        open_folder = QPushButton("打开文件夹")
        open_folder.clicked.connect(lambda: os.startfile(str(folder)))
        open_note = QPushButton("用默认程序打开")
        open_note.clicked.connect(lambda: os.startfile(str(self.notes_path)))
        close_button = QPushButton("关闭")
        close_button.clicked.connect(self.accept)
        buttons.addWidget(open_folder)
        buttons.addWidget(open_note)
        buttons.addStretch(1)
        buttons.addWidget(close_button)
        layout.addLayout(buttons)