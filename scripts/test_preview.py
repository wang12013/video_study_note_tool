# -*- coding: utf-8 -*-
import sys
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from video_notes.app.dialogs.note_preview import NotePreviewDialog

app = QApplication(sys.argv)
for font in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"]:
    QFontDatabase.addApplicationFont(font)
app.setFont(QFont("Microsoft YaHei UI", 9))

note = Path(r"D:\notes_ai_generate\培训类PPT快速制作：目录搭建与AI辅助\notes.md")
dialog = NotePreviewDialog(note)
dialog.resize(980, 760)
dialog.show()
app.processEvents()
QTimer.singleShot(800, app.quit)
app.exec()
print("saved:", dialog.grab().save("ui_preview.png"))
print("resources:", len(dialog.browser.document().resource(0).__class__.__name__))
