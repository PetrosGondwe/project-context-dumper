"""QObject worker that runs run_dump() on a background QThread.

Uses the moveToThread() pattern (rather than subclassing QThread) as
recommended by Qt: the worker's slots then execute on the worker thread
while all signal deliveries are queued back onto the GUI thread by Qt's
event loop, so no manual locking is needed on the Qt side.
"""
from __future__ import annotations

import threading
import traceback
from pathlib import Path
from typing import Optional

from PySide6.QtCore import QObject, Signal, Slot

from .config import Config
from .dumper import Mode, run_dump


class DumpWorker(QObject):
    # done, total, relative_path, phase ("source" | "pdf")
    progress = Signal(int, int, str, str)
    finished = Signal(object)   # DumpSummary
    failed = Signal(str)        # user-facing error message

    def __init__(
        self,
        root: Path,
        config: Config,
        output_path: Optional[Path],
        mode: Mode,
        overwrite: bool,
    ):
        super().__init__()
        self._root = root
        self._config = config
        self._output_path = output_path
        self._mode = mode
        self._overwrite = overwrite
        self._cancel_event = threading.Event()

    @Slot()
    def request_cancel(self) -> None:
        self._cancel_event.set()

    @Slot()
    def run(self) -> None:
        try:
            summary = run_dump(
                self._root,
                self._config,
                output_path=self._output_path,
                mode=self._mode,
                overwrite=self._overwrite,
                cancel_event=self._cancel_event,
                progress_cb=lambda i, t, r, phase: self.progress.emit(i, t, r, phase),
            )
            self.finished.emit(summary)
        except Exception as e:  # noqa: BLE001 - every failure must reach the UI, never crash silently
            self.failed.emit(f"{e}\n\n{traceback.format_exc()}")
