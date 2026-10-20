# -*- coding: utf-8 -*-
import sys

from PySide6.QtCore import Qt
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication

app = QApplication(sys.argv)
from video_notes.app.main_window import MainWindow

window = MainWindow()
window.resize(1100, 700)
window.show()
app.processEvents()
table = window.library_page.table
print("rows:", table.rowCount(), "cols:", table.columnCount())
item = table.item(0, 5)
print("open cell:", item.text() if item else None)
table.scrollToItem(item)
app.processEvents()
rect = table.visualItemRect(item)
QTest.mouseClick(table.viewport(), Qt.MouseButton.LeftButton, pos=rect.center())
app.processEvents()
print("after click:", type(window.stack.currentWidget()).__name__)
