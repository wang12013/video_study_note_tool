# -*- coding: utf-8 -*-
import sys
import time
from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from video_notes.app.pages.course_page import CoursePage
from video_notes.core.config import Store
from video_notes.core.library import LibraryStore

app = QApplication(sys.argv)
for font in [r"C:\Windows\Fonts\msyh.ttc"]:
    QFontDatabase.addApplicationFont(font)
app.setFont(QFont("Microsoft YaHei UI", 9))

library = LibraryStore(r"D:\vibe-coding-project\video_study_note_tool\.devdata\test_library.db")
for course in library.list_courses():
    library.delete_course(course["id"])
course_id = library.add_course("测试合集：AI 工具", "local", description="两段本地测试视频，用来验证课程目录与总览。")
library.add_video(course_id, 0, "有这样的app吗", description="聊一聊待办 App 需要哪些能力。", local_path=r"D:\vibe-coding-project\video_study_note_tool\.devdata\dl\BV1MtvXBmEb1.mp4")
library.add_video(course_id, 1, "如何快速制作培训类PPT", description="用 AI PPT 工具快速生成培训课件。", local_path=r"D:\vibe-coding-project\video_study_note_tool\.devdata\dl\BV1zG4111775.mp4")

settings = Store()
page = CoursePage(library, settings, course_id)
page.resize(900, 620)
page.show()
app.processEvents()

done = {"start": time.time()}

def watch():
    if page.worker is not None and not page.worker.isRunning():
        app.quit()
    elif time.time() - done["start"] > 300:
        app.quit()

timer = QTimer(); timer.timeout.connect(watch); timer.start(500)
page.start_build()
app.exec()
print("elapsed:", round(time.time() - done["start"], 1))
course_dir = page.course_dir
print("course dir:", course_dir)
for path in sorted(course_dir.rglob("*")):
    print(" ", path.relative_to(course_dir), path.stat().st_size if path.is_file() else "<dir>")
print("--- index.md ---")
index = course_dir / "index.md"
print(index.read_text(encoding="utf-8") if index.exists() else "MISSING")
page.grab().save("ui_course_done.png")
