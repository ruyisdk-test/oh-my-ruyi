from __future__ import annotations

import os
import sys
from typing import TYPE_CHECKING

from PySide6.QtCore import QObject, QProcess, Signal, QTimer
from ruyi.config import GlobalConfig

from ..core.state import WizardState
from ..core.state_machine import ProvisionStateMachine
from ..i18n import _
from ..ui.widgets.qprocess_utils import configure_qprocess_environment
from ..workers import (
    FlashWorker,
    StorageDiscoveryWorker,
    TelemetrySetupWorker,
    WorkerTaskRunner,
)

if TYPE_CHECKING:
    from pathlib import Path
    from ..ui.widgets.qt_logger import LogEmitter

FASTBOOT_PROGRAM = "fastboot"


class ProvisionController(QObject):
    """
    Controller for the main provisioning flow.
    Owns the WizardState, ProvisionStateMachine, and orchestrates workers and processes.
    """

    step_changed = Signal(int)
    busy_changed = Signal(bool)

    # Fastboot Signals
    fastboot_started = Signal()
    fastboot_output = Signal(bytes)
    fastboot_finished = Signal(bool, str)  # success, message

    # Download Signals
    download_started = Signal()
    download_output = Signal(bytes)
    download_finished = Signal(bool, str)  # success, message

    # Storage Discovery Signals
    storage_discovery_started = Signal()
    storage_discovery_finished = Signal(object)  # dict[str, os_storage.HostBlockDevice]
    storage_discovery_failed = Signal(str)

    # Flash Signals
    flash_started = Signal()
    flash_finished = Signal(object)  # ruyi_adapter.FlashResult
    flash_failed = Signal(str)

    # Telemetry Signals
    telemetry_started = Signal()
    telemetry_finished = Signal(bool, str)  # success, message
    telemetry_failed = Signal(str)

    def __init__(self, config: GlobalConfig, emitter: LogEmitter, parent=None):
        super().__init__(parent)
        self.state = WizardState(config=config, emitter=emitter)
        self.machine = ProvisionStateMachine(self.state, self._on_step_changed)

        self._runner = WorkerTaskRunner(self)
        self._worker = None

        self._fastboot_process: QProcess | None = None
        self._fastboot_output = bytearray()
        self._fastboot_timed_out = False
        self._fastboot_timer = QTimer(self)
        self._fastboot_timer.setSingleShot(True)
        self._fastboot_timer.setInterval(10_000)
        self._fastboot_timer.timeout.connect(self._on_fastboot_timeout)

        self._download_process: QProcess | None = None
        self._download_cancelled = False

        self._flash_cancel_requested = False

        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.setInterval(2000)
        self._kill_timer.timeout.connect(self._force_kill_download_process)

    @property
    def is_busy(self) -> bool:
        return (
            self._worker is not None
            or self._fastboot_process is not None
            or self._download_process is not None
        )

    def _on_step_changed(self, step: int) -> None:
        self.step_changed.emit(step)

    def cancel_current_task(self) -> None:
        if self._download_process is not None:
            self._cancel_download()
        elif isinstance(self._worker, FlashWorker):
            self._flash_cancel_requested = True
            self._worker.request_cancel()

    # --- Fastboot ---

    def start_fastboot_check(self) -> bool:
        if self.is_busy:
            return False

        self._fastboot_output.clear()
        self._fastboot_timed_out = False

        process = QProcess(self)
        self._fastboot_process = process
        process.setProgram(FASTBOOT_PROGRAM)
        process.setArguments(["devices"])

        process.readyReadStandardOutput.connect(self._read_fastboot_output)
        process.readyReadStandardError.connect(self._read_fastboot_output)
        process.finished.connect(
            lambda code, status, p=process: self._on_fastboot_finished(p, code)
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_fastboot_error(p, error)
        )

        self.fastboot_started.emit()
        self.busy_changed.emit(True)
        self._fastboot_timer.start()
        process.start()
        return True

    def _read_fastboot_output(self) -> None:
        if self._fastboot_process is None:
            return
        data = bytes(self._fastboot_process.readAll())
        self._fastboot_output.extend(data)
        self.fastboot_output.emit(data)

    def _on_fastboot_finished(self, process: QProcess, ret: int) -> None:
        if process != self._fastboot_process:
            process.deleteLater()
            return
        self._fastboot_timer.stop()
        self._read_fastboot_output()
        self._fastboot_process = None
        process.deleteLater()

        if self._fastboot_timed_out:
            self.fastboot_finished.emit(False, "fastboot devices timed out.")
        elif ret != 0:
            self.fastboot_finished.emit(
                False, f"fastboot check failed (exit code {ret})."
            )
        else:
            self.fastboot_finished.emit(True, "fastboot check successful.")
        self.busy_changed.emit(False)

    def _on_fastboot_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process != self._fastboot_process:
            return
        self._fastboot_timer.stop()
        self._fastboot_process = None
        process.deleteLater()

        if error == QProcess.ProcessError.FailedToStart:
            self.fastboot_finished.emit(False, f"Could not run {FASTBOOT_PROGRAM}.")
        else:
            self.fastboot_finished.emit(False, "fastboot process crashed.")
        self.busy_changed.emit(False)

    def _on_fastboot_timeout(self) -> None:
        self._fastboot_timed_out = True
        if self._fastboot_process:
            self._fastboot_process.terminate()

    def stop_fastboot_check(self) -> None:
        self._fastboot_timer.stop()
        if self._fastboot_process:
            self._fastboot_process.kill()
            self._fastboot_process = None
            self.busy_changed.emit(False)

    # --- Download ---

    def start_download(self) -> bool:
        if self.is_busy:
            return False

        self.machine.download_ok = False
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

        if self._download_cancelled:
            self.machine.download_recoverable = True
            self.download_finished.emit(False, _("Download cancelled."))
        elif code != 0:
            self.machine.download_recoverable = True
            self.download_finished.emit(
                False, _("Download failed (exit code {code}).", code=code)
            )
        else:
            self.machine.download_ok = True
            self.download_finished.emit(True, _("Download successful."))
        self.busy_changed.emit(False)

    def _on_download_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process != self._download_process:
            return
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

    def _cancel_download(self) -> None:
        process = self._download_process
        if process is None or self._download_cancelled:
            return
        self._download_cancelled = True
        pid = process.processId()
        import signal as os_signal

        if pid > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(pid, os_signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
        else:
            process.terminate()
        self._kill_timer.start()

    def _force_kill_download_process(self) -> None:
        if (
            self._download_process is not None
            and self._download_process.state() != QProcess.ProcessState.NotRunning
        ):
            self._download_process.kill()

    # --- Storage Discovery ---

    def start_storage_discovery(self) -> None:
        if self.is_busy:
            return
        self.storage_discovery_started.emit()
        self.busy_changed.emit(True)
        self._worker = StorageDiscoveryWorker()
        self._worker.finished.connect(self._on_storage_finished)
        self._worker.failed.connect(self._on_storage_failed)
        self._runner.run_worker(self._worker)

    def _on_storage_finished(self, disks) -> None:
        self._worker = None
        self.storage_discovery_finished.emit(disks)
        self.busy_changed.emit(False)

    def _on_storage_failed(self, error: str) -> None:
        self._worker = None
        self.storage_discovery_failed.emit(error)
        self.busy_changed.emit(False)

    # --- Flash ---

    def start_flash(self, device_node, versions_directory) -> None:
        if self.is_busy:
            return
        self._flash_cancel_requested = False
        self.machine.flash_recoverable = False
        self.flash_started.emit()
        self.busy_changed.emit(True)
        self._worker = FlashWorker(
            self.state.config, self.state.prepared, device_node, versions_directory
        )
        self._worker.finished.connect(self._on_flash_finished)
        self._worker.failed.connect(self._on_flash_failed)
        self._runner.run_worker(self._worker)

    def _on_flash_finished(self, result) -> None:
        self._worker = None
        self.flash_finished.emit(result)
        self.busy_changed.emit(False)

    def _on_flash_failed(self, error: str) -> None:
        self._worker = None
        self.machine.flash_recoverable = not self._flash_cancel_requested
        self.flash_failed.emit(error)
        self.busy_changed.emit(False)

    # --- Telemetry ---

    def start_telemetry_setup(self, activation_link: Path, mode: str) -> None:
        if self.is_busy:
            return
        self.telemetry_started.emit()
        self.busy_changed.emit(True)
        self._worker = TelemetrySetupWorker(activation_link, mode)
        self._worker.finished.connect(self._on_telemetry_finished)
        self._worker.failed.connect(self._on_telemetry_failed)
        self._runner.run_worker(self._worker)

    def _on_telemetry_finished(self) -> None:
        self._worker = None
        self.telemetry_finished.emit(True, "")
        self.busy_changed.emit(False)

    def _on_telemetry_failed(self, error: str) -> None:
        self._worker = None
        self.telemetry_failed.emit(False, error)
        self.busy_changed.emit(False)
