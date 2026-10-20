# -*- coding: utf-8 -*-
import sys
import time

from PySide6.QtCore import QTimer
from PySide6.QtGui import QFont, QFontDatabase
from PySide6.QtWidgets import QApplication

from video_notes.app.pages.course_page import CoursePage
from video_notes.core.config import Store
from video_notes.core.library import LibraryStore

app = QApplication(sys.argv)
for font in [r"C:\Windows\Fonts\msyh.ttc", r"C:\Windows\Fonts\msyhbd.ttc"]:
    QFontDatabase.addApplicationFont(font)
app.setFont(QFont("Microsoft YaHei UI", 9))

library = LibraryStore(r"D:\vibe-coding-project\video_study_note_tool\.devdata\test_library.db")
for course in library.list_courses():
    library.delete_course(course["id"])
course_id = library.add_course("测试课程（本地）", "local")
library.add_video(course_id, 0, "有这样的app吗", local_path=r"D:\vibe-coding-project\video_study_note_tool\.devdata\dl\BV1MtvXBmEb1.mp4")

settings = Store()
page = CoursePage(library, settings, course_id)
page.resize(900, 620)
page.show()
app.processEvents()
page.grab().save("ui_course.png")
print("course page shot saved")

done = {"value": False, "start": time.time()}

def watch():
    if page.worker is not None and not page.worker.isRunning():
        done["value"] = True
        app.quit()
    elif time.time() - done["start"] > 240:
        app.quit()

timer = QTimer()
timer.timeout.connect(watch)
timer.start(500)

page.start_build()
app.exec()
print("elapsed:", round(time.time() - done["start"], 1))
print("videos:", [(v["title"], v["status"], bool(v["note_path"])) for v in library.list_videos(course_id)])
print("log tail:", page.log.toPlainText().splitlines()[-4:])
page.grab().save("ui_course_done.png")
