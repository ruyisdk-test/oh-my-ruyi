from __future__ import annotations

import os
import signal
import sys

from PySide6.QtCore import QObject, QProcess, Signal, QTimer
from ruyi.config import GlobalConfig

from ..core.state import WizardState
from ..core.state_machine import ProvisionStateMachine
from ..i18n import _
from ..ui.widgets.qt_logger import LogEmitter
from ..ui.widgets.qprocess_utils import configure_qprocess_environment
from ..workers import ProvisionPreparationWorker, WorkerTaskRunner


class ProvisionController(QObject):
    """
    Controller for the main provisioning flow.
    Owns the WizardState, ProvisionStateMachine, and orchestrates workers and processes.
    """

    step_changed = Signal(int)
    busy_changed = Signal(bool)

    # Download Signals
    download_started = Signal()
    download_output = Signal(bytes)
    download_finished = Signal(bool, str)  # download success, message
    preparation_finished = Signal(object)
    preparation_failed = Signal(str)

    def __init__(self, config: GlobalConfig, emitter: LogEmitter, parent=None):
        super().__init__(parent)
        self.state = WizardState(config=config, emitter=emitter)
        self.machine = ProvisionStateMachine(self.state, self._on_step_changed)

        self._runner = WorkerTaskRunner(self)
        self._worker = None

        self._download_process: QProcess | None = None
        self._download_cancelled = False

        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.setInterval(2000)
        self._kill_timer.timeout.connect(self._force_kill_download_process)

    @property
    def is_busy(self) -> bool:
        return self._worker is not None or self._download_process is not None

    @property
    def download_is_busy(self) -> bool:
        """Whether package download or installation is still running."""
        return self._download_process is not None

    def _on_step_changed(self, step: int) -> None:
        self.step_changed.emit(step)

    def cancel_current_task(self) -> None:
        if self._download_process is not None:
            self._cancel_download()

    # --- Package download and preparation ---

    def start_download(self) -> bool:
        if self.is_busy:
            return False

        self.machine.download_ok = False
        self.state.prepared = None
        self.state.host_blkdev_map.clear()
        self.state.host_blkdev_fingerprints.clear()
        self.state.flash_ret = None
        self._download_cancelled = False
        self.machine.download_recoverable = False

        process = QProcess(self)
        self._download_process = process
        process.setProgram(sys.executable)
        process.setArguments(
            ["-m", "oh_my_ruyi.processes.download_child", *self.state.pkg_atoms]
        )

        configure_qprocess_environment(process)

        process.readyReadStandardOutput.connect(self._read_download_output)
        process.finished.connect(
            lambda code, status, p=process: self._on_download_finished(p, code)
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_download_error(p, error)
        )

        self.download_started.emit()
        self.busy_changed.emit(True)
        process.start()
        return True

    def _read_download_output(self) -> None:
        if self._download_process is None:
            return
        data = bytes(self._download_process.readAllStandardOutput())
        self.download_output.emit(data)

    def _on_download_finished(self, process: QProcess, code: int) -> None:
        if process != self._download_process:
            process.deleteLater()
            return
        self._kill_timer.stop()
        self._read_download_output()
        self._download_process = None
        process.deleteLater()

        cancelled = self._download_cancelled
        if cancelled:
            self.machine.download_recoverable = True
            message = _("Download cancelled.")
        elif code != 0:
            self.machine.download_recoverable = True
            message = _("Download failed (exit code {code}).", code=code)
        else:
            message = _("Download successful.")
        success = not cancelled and code == 0
        if success and not self._start_preparation_worker():
            self.download_finished.emit(True, message)
            self.preparation_failed.emit(_("Could not start flash preparation."))
            self.busy_changed.emit(False)
            return
        self.download_finished.emit(success, message)
        if not success:
            self.busy_changed.emit(False)

    def _on_download_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process != self._download_process:
            return
        self._kill_timer.stop()
        self._read_download_output()
        self._download_process = None
        process.deleteLater()

        self.machine.download_recoverable = True
        if error == QProcess.ProcessError.FailedToStart:
            self.download_finished.emit(
                False, _("Failed to start the download process.")
            )
        else:
            self.download_finished.emit(False, _("Download process crashed."))
        self.busy_changed.emit(False)

    def _start_preparation_worker(self) -> bool:
        if self._worker is not None or self.state.mr is None:
            return False
        self._worker = ProvisionPreparationWorker(
            self.state.config,
            self.state.mr,
            list(self.state.pkg_atoms),
        )
        self._worker.finished.connect(self._on_preparation_finished)
        self._worker.failed.connect(self._on_preparation_failed)
        self._runner.run_worker(self._worker)
        return True

    def _on_preparation_finished(self, prepared) -> None:
        self._worker = None
        self.state.prepared = prepared
        self.machine.download_ok = True
        self.preparation_finished.emit(prepared)
        self.busy_changed.emit(False)

    def _on_preparation_failed(self, error: str) -> None:
        self._worker = None
        self.machine.download_ok = False
        self.machine.download_recoverable = True
        self.preparation_failed.emit(error)
        self.busy_changed.emit(False)

    def _cancel_download(self) -> None:
        process = self._download_process
        if process is None or self._download_cancelled:
            return
        self._download_cancelled = True
        pid = process.processId()

        if pid > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
        else:
            process.terminate()
        self._kill_timer.start()

    def _force_kill_download_process(self) -> None:
        process = self._download_process
        if process is None or process.state() == QProcess.ProcessState.NotRunning:
            return
        pid = process.processId()
        if pid > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        process.kill()
