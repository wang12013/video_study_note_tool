from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QThread, Signal

from video_notes.core.config import Store
from video_notes.pipeline.runner import BuildOptions, build


class BuildWorker(QThread):
    video_started = Signal(int, str)
    log = Signal(str)
    video_done = Signal(int, str, str)
    video_failed = Signal(int, str)
    finished_all = Signal()

    def __init__(self, items: list[dict], store: Store, out_root: str, parent=None) -> None:
        super().__init__(parent)
        self.items = items
        self.store = store
        self.out_root = out_root
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def run(self) -> None:
        for index, item in enumerate(self.items):
            if self._stopped:
                break
            self.video_started.emit(index, item.get("title") or "")
            try:
                result = build(
                    item["source"],
                    self.store,
                    BuildOptions(
                        out_root=Path(self.out_root) if self.out_root else None,
                        folder_name=item.get("folder_name"),
                    ),
                    progress=self.log.emit,
                )
                self.video_done.emit(index, result.title, str(result.notes_path))
            except Exception as exc:  # noqa: BLE001
                self.video_failed.emit(index, str(exc))
        self.finished_all.emit()