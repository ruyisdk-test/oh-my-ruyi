"""Controller for metadata repository init and sync operations.

The repository update and news flows are owned by
:class:`~oh_my_ruyi.ui.views.repo_manager_tab.RepoManagementTab`, which runs
its own QProcess children.  This controller only wraps the two blocking
metadata operations that must not run on the Qt UI thread.
"""

from __future__ import annotations

from PySide6.QtCore import QObject, Signal
from ruyi.config import GlobalConfig
from ruyi.ruyipkg.composite_repo import CompositeRepo

from ..workers import RepoInitWorker, RepoSyncWorker, WorkerTaskRunner


class RepoController(QObject):
    """Run metadata repository init and sync off the UI thread."""

    # Init Signals
    init_started = Signal()
    init_finished = Signal(object)  # CompositeRepo
    init_failed = Signal(str)

    # Sync Signals
    sync_started = Signal()
    sync_finished = Signal(object)  # CompositeRepo
    sync_failed = Signal(str)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._runner = WorkerTaskRunner(self)
        self._worker = None

    @property
    def is_busy(self) -> bool:
        return self._worker is not None

    def start_repo_init(self, config: GlobalConfig) -> None:
        if self.is_busy:
            return
        self.init_started.emit()
        self._worker = RepoInitWorker(config)
        self._worker.finished.connect(self._on_init_finished)
        self._worker.failed.connect(self._on_init_failed)
        self._runner.run_worker(self._worker)

    def _on_init_finished(self, mr: CompositeRepo) -> None:
        self._worker = None
        self.init_finished.emit(mr)

    def _on_init_failed(self, error: str) -> None:
        self._worker = None
        self.init_failed.emit(error)

    def start_repo_sync(self, config: GlobalConfig, mr: CompositeRepo) -> None:
        if self.is_busy:
            return
        self.sync_started.emit()
        self._worker = RepoSyncWorker(config, mr)
        self._worker.finished.connect(self._on_sync_finished)
        self._worker.failed.connect(self._on_sync_failed)
        self._runner.run_worker(self._worker)

    def _on_sync_finished(self, mr: CompositeRepo) -> None:
        self._worker = None
        self.sync_finished.emit(mr)

    def _on_sync_failed(self, error: str) -> None:
        self._worker = None
        self.sync_failed.emit(error)
