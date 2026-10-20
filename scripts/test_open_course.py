# -*- coding: utf-8 -*-
import sys
import traceback

from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)

from video_notes.app.main_window import MainWindow

window = MainWindow()
window.show()
app.processEvents()
print("library rows:", window.library_page.table.rowCount())
for row in range(window.library_page.table.rowCount()):
    print(" row", row, window.library_page.table.item(row, 0).text(), window.library_page.table.item(row, 2).text())

try:
    window.open_course(2)
    app.processEvents()
    widget = window.stack.currentWidget()
    print("current page:", type(widget).__name__)
except Exception:
    traceback.print_exc()
