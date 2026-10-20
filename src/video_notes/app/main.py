from __future__ import annotations

import datetime
import os
import sys
import traceback

from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication

from video_notes.core import paths

from .main_window import MainWindow


def _install_error_log() -> None:
    log_path = paths.logs_dir() / "app.log"

    def hook(exc_type, exc, tb) -> None:
        try:
            with open(log_path, "a", encoding="utf-8") as handle:
                handle.write(f"\n[{datetime.datetime.now():%Y-%m-%d %H:%M:%S}]\n")
                traceback.print_exception(exc_type, exc, tb, file=handle)
        except OSError:
            pass
        sys.__excepthook__(exc_type, exc, tb)

    sys.excepthook = hook


def run(argv: list[str] | None = None) -> int:
    _install_error_log()
    app = QApplication(argv if argv is not None else sys.argv)
    app.setApplicationName("VideoNotes")
    app.setApplicationDisplayName("VideoNotes")
    app.setStyle("Fusion")
    font = QFont("Microsoft YaHei UI", 9)
    app.setFont(font)
    window = MainWindow()
    window.show()
    open_course_id = os.environ.get("VNOTE_OPEN_COURSE")
    if open_course_id:
        from PySide6.QtCore import QTimer

        def _probe() -> None:
            log_path = paths.logs_dir() / "open_course.log"
            try:
                window.open_course(int(open_course_id))
                page = type(window.stack.currentWidget()).__name__
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(f"opened course {open_course_id} -> {page}\n")
            except Exception:
                with open(log_path, "a", encoding="utf-8") as handle:
                    handle.write(f"failed course {open_course_id}\n")
                    traceback.print_exc(file=handle)
            app.quit()

        QTimer.singleShot(800, _probe)
    if os.environ.get("VNOTE_SMOKE"):
        from PySide6.QtCore import QTimer

        QTimer.singleShot(1500, app.quit)
    return app.exec()