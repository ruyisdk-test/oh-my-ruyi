"""Device provisioning wizard pages and actions.

Mixed into ProvisionMainWindow to keep the main window
module small.
"""

from __future__ import annotations

from __future__ import annotations
import os
import platform
import signal
from pathlib import Path
from PySide6.QtCore import (
    QDir,
    QProcess,
    Qt,
)
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFrame,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)
from ...infra import (
    os_storage,
    repo_manager,
    ruyi_adapter,
)
from ...i18n import _
from ..widgets.rich_output import (
    RichTextView,
    rich_to_html,
    strip_terminal_controls,
)
from ...workers import (
    FlashWorker,
    RepoInitWorker,
    StorageDiscoveryWorker,
)
from ._common import (
    FASTBOOT_PROGRAM,
    STORAGE_FINGERPRINT_ROLE,
    STORAGE_MOUNTED_ROLE,
    _message_box,
)


class ProvisionWizardMixin:
    def _refresh_about_tab(self) -> None:
        if self._config_loader is not None:
            try:
                with self._logger.terminal_target("welcome"):
                    self.state.config = self._config_loader()
            except BaseException:  # noqa: BLE001 - keep About readable
                pass
        self._about_tab.refresh(self.state.config)

    def _on_repo_configuration_changed(self, repo_id: str) -> None:
        if self._config_loader is not None:
            try:
                with self._logger.terminal_target("welcome"):
                    self.state.config = self._config_loader()
            except BaseException as exc:  # noqa: BLE001
                self._repo_manager_tab._set_status(
                    "Repository changed, but configuration reload failed.",
                    "error",
                    details=str(exc),
                )
                return
        if repo_id == repo_manager.DEFAULT_REPO_ID:
            self._reset_provision_for_repo_change()
        self._refresh_buttons()

    def _on_managed_repo_updated(self, repo_id: str) -> None:
        if repo_id != repo_manager.DEFAULT_REPO_ID or self._worker is not None:
            return
        first_use_update = (
            self._first_use_active and self._first_use_operation == "repository"
        )
        self._reset_provision_for_repo_change()
        if self._config_loader is not None:
            try:
                with self._logger.terminal_target("welcome"):
                    self.state.config = self._config_loader()
            except BaseException as exc:  # noqa: BLE001
                self._repo_manager_tab._set_status(
                    "Repository updated, but configuration reload failed.",
                    "error",
                    details=str(exc),
                )
                return
        if first_use_update:
            return
        self._start_repo_init()

    def _reset_provision_for_repo_change(self) -> None:
        self.state.mr = None
        self.state.reset_from_category()
        self._machine.versions_visited = False
        self._machine.download_ok = False
        self._machine.download_recoverable = False
        self._machine.flash_recoverable = False
        self._device_list.clear()
        self._device_details.clear()
        self._device_details.hide()
        if self._repo_manager_tab.default_repo_active:
            welcome_message = _(
                "The default repository configuration changed. Update it before "
                "provisioning a device."
            )
            device_message = _(
                "The default repository configuration changed. Update metadata to "
                "reload devices."
            )
        else:
            welcome_message = _(
                "The ruyisdk repository is disabled. Enable it in Repo Management "
                "to load device metadata."
            )
            device_message = _(
                "The ruyisdk repository is disabled. Enable it in Repo Management "
                "before provisioning a device."
            )
        self._welcome_status.setText(welcome_message)
        self._set_status_kind(self._welcome_status, "warning")
        self._device_status.setText(device_message)
        self._set_status_kind(self._device_status, "warning")
        self._refresh_summary()
        self._set_step(self._machine.STEP_WELCOME)

    def _on_repo_manager_busy_changed(self, _busy: bool) -> None:
        self._refresh_buttons()
        self._refresh_pm_buttons()

    def _on_provision_repo_update_finished(self, success: bool, message: str) -> None:
        if not success:
            disabled_message = _(
                "Enable the ruyisdk repository in Repo Management to load device metadata."
            )
            disabled = message == disabled_message
            self._welcome_status.setText(
                message
                if disabled
                else _("Repository update failed. See Repo Management output.")
            )
            self._welcome_status.setToolTip(message)
            self._set_status_kind(self._welcome_status, "warning")
            self._refresh_buttons()
            return
        if self._config_loader is not None:
            try:
                with self._logger.terminal_target("welcome"):
                    self.state.config = self._config_loader()
            except BaseException as exc:  # noqa: BLE001
                self._welcome_status.setText(
                    _("Repository updated, but configuration reload failed.")
                )
                self._welcome_status.setToolTip(str(exc))
                self._set_status_kind(self._welcome_status, "error")
                self._refresh_buttons()
                return
        self._start_repo_init()

    def _build_pages(self) -> None:
        self._welcome_status = QLabel("Preparing the RuyiSDK metadata repository...")
        self._welcome_status.setWordWrap(True)
        self._welcome_status.setProperty("statusKind", "warning")
        self._add_page(
            "RuyiSDK Device Provisioning",
            [
                QLabel(
                    "This screen walks through the same flow as `ruyi device provision`. "
                    "The left side shows the whole process; the right side keeps your "
                    "choices visible while showing the current step."
                ),
                self._welcome_status,
            ],
        )

        self._device_list = QListWidget()
        self._device_list.setAccessibleName("Devices")
        self._device_list.currentRowChanged.connect(self._refresh_buttons)
        self._device_list.itemDoubleClicked.connect(self._activate_current_step)
        self._device_status = QLabel("")
        self._device_status.setWordWrap(True)
        self._device_status.setProperty("statusKind", "warning")
        self._device_details = self._make_log_view()
        self._device_details.setMaximumHeight(180)
        self._device_details.hide()
        self._update_repo_btn = QPushButton("Update metadata")
        self._update_repo_btn.clicked.connect(self._start_repo_sync)
        self._add_page(
            "Pick your device",
            [
                self._device_status,
                self._update_repo_btn,
                self._device_list,
                self._device_details,
            ],
        )

        self._variant_list = QListWidget()
        self._variant_list.setAccessibleName("Device variants")
        self._variant_list.currentRowChanged.connect(self._refresh_buttons)
        self._variant_list.itemDoubleClicked.connect(self._activate_current_step)
        self._add_page("Pick the device variant", [self._variant_list])

        self._combo_list = QListWidget()
        self._combo_list.setAccessibleName("System images")
        self._combo_list.currentRowChanged.connect(self._refresh_buttons)
        self._combo_list.itemDoubleClicked.connect(self._activate_current_step)
        self._add_page("Pick the system image", [self._combo_list])

        self._versions_box = QWidget()
        self._versions_layout = QVBoxLayout(self._versions_box)
        self._versions_layout.setContentsMargins(0, 0, 0, 0)
        self._versions_status = QLabel("")
        self._versions_status.setWordWrap(True)
        self._add_page(
            "Customize package versions",
            [
                QLabel(
                    "By default, ruyi installs the latest version of each package. "
                    "When other versions are available, choose them here."
                ),
                self._versions_status,
                self._versions_box,
            ],
        )

        self._packages_list = QListWidget()
        self._packages_list.setAccessibleName("Packages to install")
        self._packages_list.itemDoubleClicked.connect(self._activate_current_step)
        self._add_page(
            "Confirm packages",
            [
                QLabel("The following packages will be downloaded and installed:"),
                self._packages_list,
            ],
        )

        self._download_status = QLabel("Download has not started.")
        self._download_log = self._make_log_view()
        self._cancel_download_btn = QPushButton("Cancel download")
        self._cancel_download_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
        )
        self._cancel_download_btn.clicked.connect(self._cancel_download)
        self._resume_download_btn = QPushButton("Resume download")
        self._resume_download_btn.clicked.connect(self._resume_download)
        self._reselect_versions_btn = QPushButton("Reselect versions")
        self._reselect_versions_btn.clicked.connect(self._reselect_versions)
        self._restart_btn = QPushButton("Start over")
        self._restart_btn.clicked.connect(self._restart_flow)
        self._download_recovery_row = QWidget()
        recovery_layout = QHBoxLayout(self._download_recovery_row)
        recovery_layout.setContentsMargins(0, 0, 0, 0)
        recovery_layout.addWidget(self._resume_download_btn)
        recovery_layout.addWidget(self._reselect_versions_btn)
        recovery_layout.addWidget(self._restart_btn)
        self._add_page(
            "Download and install packages",
            [
                self._download_status,
                self._cancel_download_btn,
                self._download_recovery_row,
                self._download_log,
            ],
        )

        self._storage_box = QWidget()
        self._storage_layout = QVBoxLayout(self._storage_box)
        self._storage_layout.setContentsMargins(0, 0, 0, 0)
        self._storage_error = QLabel("")
        self._storage_error.setWordWrap(True)
        self._storage_error.setProperty("statusKind", "warning")
        self._refresh_storage_btn = QPushButton("Refresh disks")
        self._refresh_storage_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._refresh_storage_btn.setToolTip("Scan for newly connected storage devices")
        self._refresh_storage_btn.clicked.connect(self._refresh_storage_disks)
        self._add_page(
            "Provide storage paths",
            [
                QLabel(os_storage.storage_platform_hint()),
                self._refresh_storage_btn,
                self._storage_box,
                self._storage_error,
            ],
        )

        self._review_steps = self._make_log_view()
        self._review_steps.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
        self._review_steps.setReadOnly(True)
        self._review_missing = QLabel("")
        self._review_missing.setWordWrap(True)
        self._review_missing.setProperty("statusKind", "error")
        self._fastboot_ok = False
        self._fastboot_status = QLabel("")
        self._fastboot_status.setWordWrap(True)
        self._fastboot_log = self._make_log_view()
        self._fastboot_log.setMaximumHeight(130)
        self._fastboot_log.hide()
        self._check_fastboot_btn = QPushButton("Check fastboot devices")
        self._check_fastboot_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._check_fastboot_btn.clicked.connect(self._check_fastboot_devices)
        self._proceed_cb = QCheckBox("Proceed with flashing.")
        self._proceed_cb.toggled.connect(self._refresh_buttons)
        self._add_page(
            "Review flashing actions",
            [
                self._review_steps,
                self._review_missing,
                self._fastboot_status,
                self._fastboot_log,
                self._check_fastboot_btn,
                self._proceed_cb,
            ],
        )

        self._flash_status = QLabel("Flash has not started.")
        self._interrupt_flash_btn = QPushButton("Interrupt flash")
        self._interrupt_flash_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserStop)
        )
        self._interrupt_flash_btn.clicked.connect(self._interrupt_flash)
        self._retry_flash_btn = QPushButton("Retry flash")
        self._retry_flash_btn.clicked.connect(self._retry_flash)
        self._review_flash_btn = QPushButton("Review settings")
        self._review_flash_btn.clicked.connect(self._review_flash_settings)
        self._restart_flash_btn = QPushButton("Start over")
        self._restart_flash_btn.clicked.connect(self._restart_flow)
        self._flash_recovery_row = QWidget()
        flash_recovery_layout = QHBoxLayout(self._flash_recovery_row)
        flash_recovery_layout.setContentsMargins(0, 0, 0, 0)
        flash_recovery_layout.addWidget(self._retry_flash_btn)
        flash_recovery_layout.addWidget(self._review_flash_btn)
        flash_recovery_layout.addWidget(self._restart_flash_btn)
        self._flash_log = self._make_log_view()
        self._add_page(
            "Flash device",
            [
                self._flash_status,
                self._interrupt_flash_btn,
                self._flash_recovery_row,
                self._flash_log,
            ],
        )

        self._done_label = QLabel("")
        self._done_label.setWordWrap(True)
        self._postinst_label = QLabel("")
        self._postinst_label.setWordWrap(True)
        self._postinst_label.setFrameShape(QFrame.Shape.Box)
        self._postinst_label.setObjectName("postInstallMessage")
        self._add_page("Done", [self._done_label, self._postinst_label])

    def _add_page(self, title: str, widgets: list[QWidget]) -> None:
        page = QWidget()
        layout = QVBoxLayout(page)
        title_label = QLabel(f"<b>{title}</b>")
        title_label.setObjectName("pageTitle")
        title_label.setWordWrap(True)
        page.setAccessibleName(title)
        layout.addWidget(title_label)
        has_expanding_widget = False
        for widget in widgets:
            if isinstance(widget, QLabel):
                widget.setWordWrap(True)
            expands_vertically = widget.sizePolicy().verticalPolicy() in {
                QSizePolicy.Policy.Expanding,
                QSizePolicy.Policy.MinimumExpanding,
            }
            layout.addWidget(widget, 1 if expands_vertically else 0)
            has_expanding_widget = has_expanding_widget or expands_vertically
        if not has_expanding_widget:
            layout.addStretch()
        self._stack.addWidget(page)

    def _make_log_view(self) -> RichTextView:
        view = RichTextView()
        font = view.font()
        font.setFamily("Monospace")
        view.setFont(font)
        return view

    def _start_repo_init(self) -> None:
        if self._repo_manager_tab.is_busy or self._worker is not None:
            return
        self._logger.set_terminal_target("welcome")
        self._next_btn.setEnabled(False)
        self._worker = RepoInitWorker(self.state.config)
        self._worker.finished.connect(self._on_repo_ready)
        self._worker.failed.connect(self._on_worker_failed)
        self._runner.run_worker(self._worker)
        self._refresh_buttons()

    def _start_repo_sync(self) -> None:
        if self._repo_manager_tab.is_busy or self.repo_controller.is_busy:
            return
        assert self.state.mr is not None
        self._logger.set_terminal_target("device")
        self._device_status.setText(_("Updating metadata repositories..."))
        self._device_list.clear()
        self._device_details.clear()
        self._device_details.show()

        self.repo_controller.sync_finished.connect(self._on_repo_synced)
        self.repo_controller.sync_failed.connect(self._on_worker_failed)
        self.repo_controller.start_repo_sync(self.state.config, self.state.mr)
        self._refresh_buttons()

    def _start_download(self) -> None:
        assert self.state.mr is not None
        self._download_log.clear()
        self._logger.set_terminal_target("download")
        self._download_status.setText(_("Downloading and installing packages..."))
        self._download_status.setToolTip("")
        self._set_step(self._machine.STEP_DOWNLOAD)

        self.provision_controller.start_download()
        self._refresh_buttons()

    def _on_download_output_data(self, data: bytes) -> None:
        if strip_terminal_controls(data).strip():
            self._download_status.setText(_("Downloading and installing packages..."))

    def _on_download_finished_controller(self, success: bool, message: str) -> None:
        self._download_status.setText(message)
        if not success:
            self._machine.download_ok = False
            self._machine.download_recoverable = True
            self._set_status_kind(self._download_status, "error")
            self._refresh_buttons()
            return

        try:
            assert self.state.mr is not None
            self.state.prepared = ruyi_adapter.prepare_provision(
                self.state.config,
                self.state.mr,
                self.state.pkg_atoms,
            )
        except Exception as exc:  # noqa: BLE001 - surface preparation errors inline
            self._download_log.append_plain_status(
                _("Preparing flash failed: {error}", error=exc)
            )
            self._download_status.setText(_("Preparing flash failed. See output."))
            self._download_status.setToolTip("")
            self._machine.download_ok = False
            self._machine.download_recoverable = True
            self._set_status_kind(self._download_status, "error")
        else:
            self._download_status.setText(_("Download complete."))
            self._download_status.setToolTip("")
            self._machine.download_ok = True
            self._machine.download_recoverable = False
            self._set_status_kind(self._download_status, "success")
        self._refresh_buttons()
        if self._machine.download_ok:
            self._advance_after_download()

    def _start_flash(self) -> None:
        assert self.state.prepared is not None
        storage_error = self._flash_storage_error()
        if storage_error is not None:
            self._populate_storage()
            self._storage_error.setText(storage_error)
            self._set_step(self._machine.STEP_STORAGE)
            return
        self._machine.flash_recoverable = False
        self._flash_cancel_requested = False
        self._flash_log.clear()
        self._logger.set_terminal_target("flash")
        self._flash_status.setText(_("Flashing the device..."))
        self._set_step(self._machine.STEP_FLASH)
        self._worker = FlashWorker(
            self.state.config,
            self.state.prepared,
            self.state.host_blkdev_map,
            self.state.host_blkdev_fingerprints,
            {
                part
                for part, confirmation in self._storage_mount_confirmations.items()
                if confirmation.isChecked()
            },
        )
        self._worker.finished.connect(self._on_flash_finished)
        self._worker.cancelled.connect(self._on_flash_cancelled)
        self._worker.failed.connect(self._on_worker_failed)
        self._worker.yes_no_requested.connect(
            self._on_flash_yes_no_requested, Qt.ConnectionType.BlockingQueuedConnection
        )
        self._worker.password_requested.connect(
            self._on_flash_password_requested,
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        self._worker.process_output.connect(self._on_flash_process_output)
        self._runner.run_worker(self._worker)
        self._refresh_buttons()

    def _check_fastboot_devices(self) -> None:
        self._stop_fastboot_check()
        self._fastboot_ok = False
        self._fastboot_output.clear()
        self._fastboot_log.clear()
        self._fastboot_log.show()
        self._logger.set_terminal_target("fastboot")
        self._fastboot_timed_out = False
        self._set_status_kind(self._fastboot_status, None)
        self._fastboot_status.setText(_("Checking fastboot devices..."))
        self._fastboot_status.setToolTip("")
        self._check_fastboot_btn.setEnabled(False)

        process = QProcess(self)
        self._fastboot_process = process
        process.setProgram(FASTBOOT_PROGRAM)
        process.setArguments(["devices"])
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda p=process: self._on_fastboot_output(p)
        )
        process.finished.connect(
            lambda ret, _status, p=process: self._on_fastboot_finished(p, ret)
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_fastboot_error(p, error)
        )
        process.start()
        self._fastboot_timer.start()
        self._refresh_buttons()

    def _on_fastboot_output(self, process: QProcess) -> None:
        if process != self._fastboot_process:
            return
        data = bytes(process.readAllStandardOutput())
        self._fastboot_output.extend(data)
        self._fastboot_log.feed_bytes(data)

    def _on_fastboot_finished(self, process: QProcess, ret: int) -> None:
        if process != self._fastboot_process:
            process.deleteLater()
            return
        self._on_fastboot_output(process)
        stdout = strip_terminal_controls(
            bytes(self._fastboot_output).decode(errors="replace")
        ).strip()
        output = stdout
        if self._fastboot_timed_out:
            self._complete_fastboot_check(process, False, "fastboot devices timed out.")
        elif ret != 0:
            self._complete_fastboot_check(
                process,
                False,
                f"fastboot check failed (exit code {ret}). See output.",
            )
        elif not output:
            self._complete_fastboot_check(process, False, "No fastboot devices found.")
        else:
            self._complete_fastboot_check(
                process,
                True,
                "Fastboot device check completed.",
            )

    def _on_fastboot_error(
        self,
        process: QProcess,
        error: QProcess.ProcessError,
    ) -> None:
        if process != self._fastboot_process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._complete_fastboot_check(
                process,
                False,
                "fastboot command was not found.",
            )

    def _on_fastboot_timeout(self) -> None:
        process = self._fastboot_process
        if process is None:
            return
        self._fastboot_timed_out = True
        process.kill()

    def _complete_fastboot_check(
        self,
        process: QProcess,
        ok: bool,
        message: str,
    ) -> None:
        if process != self._fastboot_process:
            return
        self._fastboot_timer.stop()
        self._on_fastboot_output(process)
        self._fastboot_log.feed_bytes(b"", final=True)
        self._fastboot_process = None
        process.deleteLater()
        self._fastboot_ok = ok
        message = _(message)
        self._fastboot_status.setText(message)
        self._fastboot_status.setToolTip("" if ok else message)
        self._set_status_kind(self._fastboot_status, "success" if ok else "error")
        self._check_fastboot_btn.setEnabled(True)
        self._refresh_buttons()

    def _stop_fastboot_check(self) -> None:
        self._fastboot_timer.stop()
        process = self._fastboot_process
        self._fastboot_process = None
        if process is None:
            return
        process.blockSignals(True)
        if process.state() != QProcess.ProcessState.NotRunning:
            process.terminate()
            if not process.waitForFinished(1000):
                process.kill()
                process.waitForFinished(1000)
        process.deleteLater()
        self._check_fastboot_btn.setEnabled(True)

    def _cancel_download(self) -> None:
        if not self.provision_controller.is_busy:
            return
        self._download_status.setText(_("Cancelling download..."))
        self._download_status.setToolTip("")
        self.provision_controller.cancel_current_task()
        self._refresh_buttons()

    def _resume_download(self) -> None:
        if not self.state.pkg_atoms:
            return
        self._start_download()

    def _reselect_versions(self) -> None:
        self.state.prepared = None
        self.state.host_blkdev_map = {}
        self.state.host_blkdev_fingerprints = {}
        self._machine.download_ok = False
        self._machine.download_recoverable = False
        if (
            self._machine.versions_visited
            and self.state.mr is not None
            and self.state.combo is not None
        ):
            self.state.pkg_atoms = ruyi_adapter.combo_package_atoms(
                self.state.combo.entity
            )
            self._populate_versions()
            self._set_step(self._machine.STEP_VERSIONS)
        else:
            self._populate_packages()
            self._set_step(self._machine.STEP_PACKAGES)

    def _restart_flow(self) -> None:
        self._machine.download_ok = False
        self._machine.download_recoverable = False
        self._machine.flash_recoverable = False
        self._machine.versions_visited = False
        self.state.reset_from_category()
        self._populate_devices()
        self._set_step(self._machine.STEP_DEVICE)

    def _terminate_download_process(self) -> None:
        proc = self._download_process
        if proc is None:
            return
        pid = proc.processId()
        if pid > 0 and platform.system() != "Windows":
            try:
                os.killpg(pid, signal.SIGTERM)
            except ProcessLookupError:
                pass
            except PermissionError:
                os.kill(pid, signal.SIGTERM)
        proc.terminate()
        if not proc.waitForFinished(3000):
            if pid > 0 and platform.system() != "Windows":
                try:
                    os.killpg(pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass
                except PermissionError:
                    os.kill(pid, signal.SIGKILL)
            proc.kill()

    def _on_repo_ready(self, mr) -> None:
        self.state.mr = mr
        self._welcome_status.setText(_("RuyiSDK metadata repository is ready."))
        self._set_status_kind(self._welcome_status, "success")
        self._cleanup_thread()
        self._populate_devices()
        self._set_step(self._machine.STEP_DEVICE)

    def _on_repo_synced(self, mr) -> None:
        self.state.mr = mr
        self._cleanup_thread()
        self._populate_devices()
        self._set_step(self._machine.STEP_DEVICE)

    def _on_download_output(self) -> None:
        if self._download_process is None:
            return
        self._download_log.feed_bytes(
            bytes(self._download_process.readAllStandardOutput())
        )

    def _on_download_process_error(self, error) -> None:
        self._download_status.setText(
            _("Download process error: {name}.", name=error.name)
        )
        self._machine.download_ok = False
        self._machine.download_recoverable = True
        if (
            error == QProcess.ProcessError.FailedToStart
            and self._download_process is not None
        ):
            self._download_process.deleteLater()
            self._download_process = None
        self._refresh_step_items()
        self._refresh_buttons()

    def _on_download_process_finished(self, ret: int, _status) -> None:
        if self._download_process is not None:
            self._download_log.feed_bytes(
                bytes(self._download_process.readAllStandardOutput()),
                final=True,
            )
            self._download_process.deleteLater()
            self._download_process = None
        if self._download_cancelled:
            self._download_status.setText(_("Download cancelled."))
            self._download_status.setToolTip("")
            self._machine.download_ok = False
            self._machine.download_recoverable = True
            self._refresh_buttons()
            return
        self._on_download_finished(ret)

    def _on_download_finished(self, ret: int) -> None:
        if ret != 0:
            self._download_status.setText(_("Download failed. See output."))
            self._download_status.setToolTip(_("Exit code: {code}", code=ret))
            self._machine.download_ok = False
            self._machine.download_recoverable = True
            self._refresh_buttons()
            return
        try:
            assert self.state.mr is not None
            self.state.prepared = ruyi_adapter.prepare_provision(
                self.state.config,
                self.state.mr,
                self.state.pkg_atoms,
            )
        except Exception as exc:  # noqa: BLE001
            self._download_log.append_plain_status(
                _("Preparing flash failed: {error}", error=exc)
            )
            self._download_status.setText(_("Preparing flash failed. See output."))
            self._download_status.setToolTip("")
            self._machine.download_ok = False
            self._machine.download_recoverable = True
        else:
            self._download_status.setText(_("Download complete."))
            self._download_status.setToolTip("")
            self._machine.download_ok = True
            self._machine.download_recoverable = False
        self._refresh_buttons()
        if self._machine.download_ok:
            self._advance_after_download()

    def _on_flash_finished(self, ret: int) -> None:
        self._flash_log.feed_bytes(b"", final=True)
        self._flash_cancel_requested = False
        self.state.flash_ret = ret
        self._machine.flash_recoverable = ret != 0
        self._flash_status.setText(
            _("Flash complete.")
            if ret == 0
            else _("Flash failed (exit code {code}).", code=ret)
        )
        self._cleanup_thread()
        if ret == 0:
            self._populate_done()
            self._set_step(self._machine.STEP_DONE)
        else:
            self._refresh_step_items()
            self._refresh_buttons()

    def _on_flash_cancelled(self) -> None:
        self._flash_log.feed_bytes(b"", final=True)
        self._flash_cancel_requested = False
        self.state.flash_ret = None
        self._machine.flash_recoverable = True
        self._flash_status.setText(_("Flash interrupted."))
        self._cleanup_thread()
        self._refresh_step_items()
        self._refresh_buttons()

    def _on_worker_failed(self, msg: str) -> None:
        _message_box(QMessageBox.critical, self, "Operation failed", msg)
        if self._machine.current_step == self._machine.STEP_FLASH:
            self._flash_log.feed_bytes(b"", final=True)
        if self._machine.current_step == self._machine.STEP_DOWNLOAD:
            self._download_status.setText(_("Operation failed."))
            self._download_status.setToolTip("")
        elif self._machine.current_step == self._machine.STEP_FLASH:
            self._flash_cancel_requested = False
            self._flash_status.setText(_("Operation failed."))
            self._flash_status.setToolTip("")
            self._machine.flash_recoverable = True
        elif self._machine.current_step == self._machine.STEP_DEVICE:
            self._device_status.setText(_("Metadata operation failed."))
            self._device_status.setToolTip("")
        else:
            self._welcome_status.setText(_("Repository operation failed."))
            self._welcome_status.setToolTip("")
        self._cleanup_thread()
        self._refresh_buttons()

    def _on_flash_yes_no_requested(
        self, prompt: str, default: bool, response: dict
    ) -> None:
        box = QMessageBox(self)
        box.setIcon(QMessageBox.Icon.Question)
        box.setWindowTitle(_("Flashing needs confirmation"))
        box.setTextFormat(Qt.TextFormat.RichText)
        box.setText(rich_to_html(prompt, end=""))
        buttons = QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No
        box.setStandardButtons(buttons)
        box.setDefaultButton(
            QMessageBox.StandardButton.Yes if default else QMessageBox.StandardButton.No
        )
        ret = box.exec()
        response["answer"] = ret == QMessageBox.StandardButton.Yes

    def _on_flash_password_requested(self, prompt: str, response: dict) -> None:
        password, ok = QInputDialog.getText(
            self,
            _("sudo password required"),
            _(prompt),
            QLineEdit.EchoMode.Password,
        )
        response["password"] = password if ok else None

    def _on_flash_process_output(self, data: bytes) -> None:
        self._flash_log.feed_bytes(data)

    def _interrupt_flash(self) -> None:
        worker = self._worker
        if not isinstance(worker, FlashWorker) or self._flash_cancel_requested:
            return
        self._flash_cancel_requested = True
        self._flash_status.setText(_("Interrupting flash..."))
        worker.request_cancel()
        self._refresh_buttons()

    def _retry_flash(self) -> None:
        if self.state.prepared is None or self._is_busy():
            return
        self.state.flash_ret = None
        self._start_flash()

    def _review_flash_settings(self) -> None:
        if self.state.prepared is None or self._is_busy():
            return
        self.state.flash_ret = None
        self._machine.flash_recoverable = False
        if self.state.prepared.requested_host_blkdevs:
            self._populate_storage()
            self._set_step(self._machine.STEP_STORAGE)
        else:
            self._populate_review()
            self._set_step(self._machine.STEP_REVIEW)

    def _activate_current_step(self, _item=None) -> None:
        if self._is_busy() or not self._can_go_next():
            return
        self._go_next()

    def _advance_after_download(self) -> None:
        assert self.state.prepared is not None
        if self.state.prepared.requested_host_blkdevs:
            self._populate_storage()
            self._set_step(self._machine.STEP_STORAGE)
        else:
            self.state.host_blkdev_map = {}
            self.state.host_blkdev_fingerprints = {}
            self._populate_review()
            self._set_step(self._machine.STEP_REVIEW)

    def _can_go_next(self) -> bool:
        step = self._machine.current_step
        if step == self._machine.STEP_WELCOME:
            return self.state.mr is not None
        if step == self._machine.STEP_DEVICE:
            item = self._device_list.currentItem()
            if item is None:
                return False
            choice_id = item.data(Qt.ItemDataRole.UserRole)
            return choice_id in self._device_choices
        if step == self._machine.STEP_VARIANT:
            return self._variant_list.currentItem() is not None
        if step == self._machine.STEP_COMBO:
            return self._combo_list.currentItem() is not None
        if step == self._machine.STEP_VERSIONS:
            return True
        if step == self._machine.STEP_PACKAGES:
            return True
        if step == self._machine.STEP_DOWNLOAD:
            return self._machine.download_ok
        if step == self._machine.STEP_STORAGE:
            return self._storage_complete()
        if step == self._machine.STEP_REVIEW:
            return self._review_complete()
        if step == self._machine.STEP_FLASH:
            return self.state.flash_ret == 0
        return True

    def _go_next(self) -> None:
        step = self._machine.current_step
        if step == self._machine.STEP_WELCOME:
            self._set_step(self._machine.STEP_DEVICE)
        elif step == self._machine.STEP_DEVICE:
            self._choose_device()
            self._populate_variants()
            self._set_step(self._machine.STEP_VARIANT)
        elif step == self._machine.STEP_VARIANT:
            self._choose_variant()
            self._populate_combos()
            self._set_step(self._machine.STEP_COMBO)
        elif step == self._machine.STEP_COMBO:
            self._choose_combo()
            if ruyi_adapter.is_package_version_customization_possible(
                self.state.config,
                self.state.mr,
                self.state.pkg_atoms,
            ):
                self._populate_versions()
                self._machine.versions_visited = True
                self._set_step(self._machine.STEP_VERSIONS)
            else:
                self._populate_packages()
                self._set_step(self._machine.STEP_PACKAGES)
        elif step == self._machine.STEP_VERSIONS:
            self._commit_versions()
            self._populate_packages()
            self._set_step(self._machine.STEP_PACKAGES)
        elif step == self._machine.STEP_PACKAGES:
            if not self.state.pkg_atoms:
                self._populate_done()
                self._set_step(self._machine.STEP_DONE)
            else:
                self._start_download()
        elif step == self._machine.STEP_DOWNLOAD:
            self._advance_after_download()
        elif step == self._machine.STEP_STORAGE:
            if self._commit_storage():
                self._populate_review()
                self._set_step(self._machine.STEP_REVIEW)
        elif step == self._machine.STEP_REVIEW:
            self._start_flash()
        elif step == self._machine.STEP_FLASH:
            self._populate_done()
            self._set_step(self._machine.STEP_DONE)
        elif step == self._machine.STEP_DONE:
            self.close()

    def _go_back(self) -> None:
        step = self._machine.current_step
        if step == self._machine.STEP_DEVICE:
            prev = self._machine.STEP_WELCOME
        elif step == self._machine.STEP_VARIANT:
            prev = self._machine.STEP_DEVICE
        elif step == self._machine.STEP_COMBO:
            prev = self._machine.STEP_VARIANT
        elif step == self._machine.STEP_VERSIONS:
            prev = self._machine.STEP_COMBO
        elif step == self._machine.STEP_PACKAGES:
            prev = (
                self._machine.STEP_VERSIONS
                if self._machine.versions_visited
                else self._machine.STEP_COMBO
            )
        elif step == self._machine.STEP_STORAGE:
            prev = self._machine.STEP_DOWNLOAD
        elif step == self._machine.STEP_REVIEW:
            if self.state.prepared and self.state.prepared.requested_host_blkdevs:
                prev = self._machine.STEP_STORAGE
            else:
                prev = self._machine.STEP_DOWNLOAD
        elif step == self._machine.STEP_DONE:
            if self.state.flash_ret is not None:
                prev = self._machine.STEP_FLASH
            elif self.state.pkg_atoms and self.state.prepared is not None:
                self._populate_review()
                prev = self._machine.STEP_REVIEW
            else:
                prev = self._machine.STEP_PACKAGES
        else:
            prev = None
        if prev is not None:
            self._set_step(prev)

    def _populate_devices(self) -> None:
        assert self.state.mr is not None
        devices = ruyi_adapter.list_devices(self.state.mr)
        self._device_choices = {d.id: d for d in devices}
        self._device_list.clear()
        self._device_status.setText("")
        if not self._device_details.toPlainText().strip():
            self._device_details.hide()
        self._update_repo_btn.setVisible(not devices)
        for d in devices:
            item = QListWidgetItem(d.display_name)
            item.setData(Qt.ItemDataRole.UserRole, d.id)
            self._device_list.addItem(item)
        if not devices:
            entity_types = ruyi_adapter.list_entity_types(self.state.mr)
            types_text = ", ".join(entity_types) if entity_types else _("(none)")
            repo_entries = []
            for entry in self.state.config.repo_entries:
                if entry.id != ruyi_adapter.PROVISION_REPO_ID:
                    continue
                source = entry.local_path or entry.remote or _("(no source)")
                repo_entries.append(f"{entry.id}: {source}")
            repos_text = (
                "\n".join(f" * {entry}" for entry in repo_entries)
                or f" * {_('(none)')}"
            )

            workspace_ruyinews = (
                Path(__file__).resolve().parents[2]
                / "ruyisdk-ruyisdk-website"
                / "news"
                / "ruyinews"
            )
            local_hint = ""
            if (workspace_ruyinews / "entities" / "device").is_dir():
                local_hint = _(
                    "\n\nA local metadata tree with device data was detected at:\n"
                    "{path}\n\nTo make the CLI and GUI use it, configure ruyi's "
                    "repo.local to this absolute path.",
                    path=workspace_ruyinews,
                )
            details = _(
                "The current ruyi metadata repository does not contain device "
                "provisioning entities (`device`, `device-variant`, `image-combo`). "
                "This GUI follows `ruyi device provision`, so it cannot continue "
                "without those entities.\n\n"
                "Available entity types: {types}.\n\nConfigured repositories:\n"
                "{repositories}{local_hint}",
                types=types_text,
                repositories=repos_text,
                local_hint=local_hint,
            )
            self._device_status.setText(
                _("No device provisioning data is available. See repository details.")
            )
            self._device_status.setToolTip("")
            self._device_details.append_plain_status(details)
            self._device_details.show()
            item = QListWidgetItem(
                _("No device provisioning data is available in this repository.")
            )
            item.setFlags(Qt.ItemFlag.NoItemFlags)
            self._device_list.addItem(item)
        elif self._device_list.count() > 0:
            self._device_list.setCurrentRow(0)

    def _choose_device(self) -> None:
        item = self._device_list.currentItem()
        assert item is not None
        choice_id = item.data(Qt.ItemDataRole.UserRole)
        self.state.device = self._device_choices[choice_id]
        self.state.variant = None
        self.state.combo = None
        self.state.pkg_atoms = []

    def _populate_variants(self) -> None:
        assert self.state.mr is not None and self.state.device is not None
        variants = ruyi_adapter.list_variants(self.state.mr, self.state.device.entity)
        self._variant_choices = {v.id: v for v in variants}
        self._variant_list.clear()
        for v in variants:
            item = QListWidgetItem(v.display_name)
            item.setData(Qt.ItemDataRole.UserRole, v.id)
            self._variant_list.addItem(item)

    def _choose_variant(self) -> None:
        item = self._variant_list.currentItem()
        assert item is not None
        self.state.variant = self._variant_choices[item.data(Qt.ItemDataRole.UserRole)]
        self.state.combo = None
        self.state.pkg_atoms = []

    def _populate_combos(self) -> None:
        assert self.state.mr is not None and self.state.variant is not None
        combos = ruyi_adapter.list_combos(self.state.mr, self.state.variant.entity)
        self._combo_choices = {c.id: c for c in combos}
        self._combo_list.clear()
        for c in combos:
            item = QListWidgetItem(c.display_name)
            item.setData(Qt.ItemDataRole.UserRole, c.id)
            self._combo_list.addItem(item)

    def _choose_combo(self) -> None:
        item = self._combo_list.currentItem()
        assert item is not None
        self.state.combo = self._combo_choices[item.data(Qt.ItemDataRole.UserRole)]
        self.state.pkg_atoms = ruyi_adapter.combo_package_atoms(self.state.combo.entity)

    def _populate_versions(self) -> None:
        assert self.state.mr is not None
        while self._versions_layout.count():
            item = self._versions_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._version_combos.clear()
        selections = ruyi_adapter.list_package_version_selections(
            self.state.config,
            self.state.mr,
            self.state.pkg_atoms,
        )
        self._versions_status.setText(
            _(
                "This mirrors the TUI's package version customization step. "
                "Leave the default selection to install the latest version."
            )
        )
        for sel in selections:
            label = QLabel(sel.package_name)
            combo = QComboBox()
            combo.setAccessibleName(
                _("Version for {package}", package=sel.package_name)
            )
            label.setBuddy(combo)
            for option in sel.options:
                combo.addItem(option.display_name, option.atom)
            combo.setEnabled(sel.locked_reason is None and len(sel.options) > 1)
            if sel.locked_reason:
                label.setText(
                    _(
                        "{package} ({reason})",
                        package=sel.package_name,
                        reason=sel.locked_reason,
                    )
                )
            row = QHBoxLayout()
            row.addWidget(label, 2)
            row.addWidget(combo, 3)
            wrapper = QWidget()
            wrapper.setLayout(row)
            self._versions_layout.addWidget(wrapper)
            self._version_combos.append(combo)
        self._versions_layout.addStretch()

    def _commit_versions(self) -> None:
        if not self._version_combos:
            return
        self.state.pkg_atoms = [
            combo.currentData(Qt.ItemDataRole.UserRole)
            for combo in self._version_combos
        ]

    def _populate_packages(self) -> None:
        self._packages_list.clear()
        if self.state.pkg_atoms:
            for atom in self.state.pkg_atoms:
                self._packages_list.addItem(atom)
        else:
            self._packages_list.addItem(
                _(
                    "No packages. The selected image only contains a post-install message."
                )
            )

    def _populate_storage(
        self,
        disks: list[os_storage.BlockDeviceChoice] | None = None,
        selected_paths: dict[str, str] | None = None,
    ) -> None:
        assert self.state.prepared is not None
        if selected_paths is None:
            selected_paths = dict(self.state.host_blkdev_map)
        while self._storage_layout.count():
            item = self._storage_layout.takeAt(0)
            widget = item.widget()
            if widget is not None:
                widget.deleteLater()
        self._storage_inputs.clear()
        self._storage_mount_warnings.clear()
        self._storage_mount_confirmations.clear()
        self._storage_error.setText("")
        discover_async = disks is None and os_storage.validation_is_slow()
        if disks is None:
            disks = [] if discover_async else os_storage.list_disks()
        for part in self.state.prepared.requested_host_blkdevs:
            previous_path = selected_paths.get(part)
            desc = ruyi_adapter.part_description(part)
            label = QLabel(f"{desc} ({part})")
            edit = QComboBox()
            edit.setEditable(True)
            edit.setAccessibleName(_("Target disk for {description}", description=desc))
            label.setBuddy(edit)
            edit.lineEdit().setPlaceholderText("/dev/...")
            for disk in disks:
                edit.addItem(disk.display_name, disk.path)
                index = edit.count() - 1
                edit.setItemData(index, disk.mounted, STORAGE_MOUNTED_ROLE)
                edit.setItemData(
                    index,
                    disk.fingerprint,
                    STORAGE_FINGERPRINT_ROLE,
                )
            warning = QLabel(
                _("The selected disk or one of its partitions is mounted.")
            )
            warning.setProperty("statusKind", "error")
            warning.setVisible(False)
            confirm = QCheckBox(_("I understand flashing may overwrite mounted data."))
            confirm.setVisible(False)
            confirm.toggled.connect(self._refresh_buttons)
            edit.currentTextChanged.connect(
                lambda _text, e=edit, w=warning, c=confirm: (
                    self._on_storage_target_changed(e, w, c)
                )
            )
            browse = QPushButton()
            browse.setIcon(
                self.style().standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton)
            )
            browse_text = _(
                "Choose target disk or image file for {description}",
                description=desc,
            )
            browse.setToolTip(browse_text)
            browse.setAccessibleName(browse_text)
            browse.clicked.connect(lambda _=False, e=edit: self._browse_storage(e))
            row = QHBoxLayout()
            row.addWidget(label, 2)
            row.addWidget(edit, 3)
            row.addWidget(browse)
            wrapper = QWidget()
            wrapper_layout = QVBoxLayout(wrapper)
            wrapper_layout.setContentsMargins(0, 0, 0, 0)
            wrapper_layout.addLayout(row)
            wrapper_layout.addWidget(warning)
            wrapper_layout.addWidget(confirm)
            self._storage_layout.addWidget(wrapper)
            self._storage_inputs[part] = edit
            self._storage_mount_warnings[part] = warning
            self._storage_mount_confirmations[part] = confirm
            if previous_path:
                idx = edit.findData(previous_path)
                if idx < 0:
                    edit.addItem(previous_path, previous_path)
                    idx = edit.count() - 1
                edit.setCurrentIndex(idx)
            else:
                edit.setCurrentIndex(-1)
                edit.lineEdit().clear()
            self._refresh_storage_mount_warning(edit, warning, confirm)
        self._storage_layout.addStretch()
        if discover_async:
            self._start_storage_discovery(selected_paths)
        else:
            self._storage_box.setEnabled(True)

    def _refresh_storage_disks(self) -> None:
        if self.state.prepared is None or self._is_busy():
            return
        selected_paths = {
            part: path
            for part, edit in self._storage_inputs.items()
            if (path := self._storage_path(edit))
        }
        self._start_storage_discovery(selected_paths)

    def _start_storage_discovery(
        self,
        selected_paths: dict[str, str] | None = None,
    ) -> None:
        self._storage_discovery_paths = dict(selected_paths or {})
        self._storage_box.setEnabled(False)
        self._storage_error.setText(_("Detecting disks..."))
        self._worker = StorageDiscoveryWorker()
        self._worker.finished.connect(self._on_storage_disks_ready)
        self._worker.failed.connect(self._on_storage_discovery_failed)
        self._runner.run_worker(self._worker)
        self._refresh_buttons()

    def _on_storage_disks_ready(self, disks: list) -> None:
        selected_paths = self._storage_discovery_paths
        self._storage_discovery_paths = {}
        self._cleanup_thread()
        self._populate_storage(list(disks), selected_paths)
        self._refresh_buttons()

    def _on_storage_discovery_failed(self, message: str) -> None:
        self._storage_discovery_paths = {}
        self._cleanup_thread()
        self._storage_box.setEnabled(True)
        self._storage_error.setText(
            _(
                "Automatic disk detection failed: {message}. Use the file chooser to select a target.",
                message=message,
            )
        )
        self._refresh_buttons()

    def _browse_storage(self, edit: QComboBox) -> None:
        dialog = QFileDialog(
            self,
            _("Select disk or image file"),
            os_storage.DEFAULT_DEVICE_ROOT,
        )
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog, True)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile)
        dialog.setNameFilter(_("All entries (*)"))
        dialog.setFilter(
            QDir.Filter.AllEntries
            | QDir.Filter.System
            | QDir.Filter.Hidden
            | QDir.Filter.NoDotAndDotDot
        )
        if dialog.exec() != QFileDialog.DialogCode.Accepted:
            return
        selected = dialog.selectedFiles()
        path = selected[0].strip() if selected else ""
        if not path:
            return
        idx = edit.findData(path)
        if idx < 0:
            idx = edit.findText(path)
        if idx < 0:
            edit.addItem(path, path)
            idx = edit.count() - 1
        edit.setCurrentIndex(idx)
        self._refresh_storage_controls()

    def _storage_path(self, edit: QComboBox) -> str:
        data = edit.currentData(Qt.ItemDataRole.UserRole)
        if data and edit.currentText() == edit.itemText(edit.currentIndex()):
            return str(data).strip()
        return edit.currentText().strip()

    def _refresh_storage_mount_warning(
        self, edit: QComboBox, warning: QLabel, confirm: QCheckBox
    ) -> None:
        path = self._storage_path(edit)
        mounted_data = self._storage_item_data(edit, STORAGE_MOUNTED_ROLE)
        if mounted_data is not None:
            mounted = bool(mounted_data)
        elif path and os.path.exists(path) and os_storage.is_native_disk_path(path):
            mounted = (
                True
                if os_storage.validation_is_slow()
                else os_storage.is_disk_or_child_mounted(path)
            )
        else:
            mounted = bool(
                path
                and os.path.exists(path)
                and os_storage.is_disk_or_child_mounted(path)
            )
        if not mounted:
            confirm.setChecked(False)
        warning.setVisible(mounted)
        confirm.setVisible(mounted)
        confirm.setEnabled(mounted)
        self._refresh_buttons()

    def _on_storage_target_changed(
        self, edit: QComboBox, warning: QLabel, confirm: QCheckBox
    ) -> None:
        confirm.setChecked(False)
        self._refresh_storage_mount_warning(edit, warning, confirm)

    def _storage_item_data(self, edit: QComboBox, role: int) -> object | None:
        index = edit.currentIndex()
        if index < 0 or edit.currentText() != edit.itemText(index):
            return None
        return edit.itemData(index, role)

    def _refresh_storage_controls(self) -> None:
        for part, edit in self._storage_inputs.items():
            self._refresh_storage_mount_warning(
                edit,
                self._storage_mount_warnings[part],
                self._storage_mount_confirmations[part],
            )

    def _storage_complete(self) -> bool:
        for part, edit in self._storage_inputs.items():
            path = self._storage_path(edit)
            if not path or not os.path.exists(path):
                return False
            if (
                self._storage_mount_warnings[part].isVisible()
                and not self._storage_mount_confirmations[part].isChecked()
            ):
                return False
        return True

    def _commit_storage(self) -> bool:
        host_blkdev_map = {}
        fingerprints: dict[str, str] = {}
        for part, edit in self._storage_inputs.items():
            path = self._storage_path(edit)
            if not os.path.exists(path):
                self._storage_error.setText(_("'{path}' does not exist.", path=path))
                return False
            if (
                self._storage_mount_warnings[part].isVisible()
                and not self._storage_mount_confirmations[part].isChecked()
            ):
                self._storage_error.setText(
                    _(
                        "'{path}' is mounted. Confirm the mounted-device warning before continuing.",
                        path=path,
                    )
                )
                return False
            fingerprint_data = self._storage_item_data(
                edit,
                STORAGE_FINGERPRINT_ROLE,
            )
            fingerprint = (
                str(fingerprint_data)
                if fingerprint_data
                else os_storage.device_fingerprint(path)
            )
            if fingerprint is None:
                self._storage_error.setText(
                    _(
                        "Could not verify the identity of '{path}'. Select the target again.",
                        path=path,
                    )
                )
                return False
            host_blkdev_map[part] = path
            fingerprints[part] = fingerprint
        self.state.host_blkdev_map = host_blkdev_map
        self.state.host_blkdev_fingerprints = fingerprints
        self._refresh_summary()
        return True

    def _flash_storage_error(self) -> str | None:
        if self.state.prepared is None:
            return _("Flash preparation is incomplete.")
        for part in self.state.prepared.requested_host_blkdevs:
            path = self.state.host_blkdev_map.get(part, "").strip()
            if not path or not os.path.exists(path):
                return _(
                    "The selected target for {part} is no longer available. Select it again.",
                    part=part,
                )
            expected_fingerprint = self.state.host_blkdev_fingerprints.get(part)
            if os_storage.validation_is_slow():
                if expected_fingerprint is None:
                    return _(
                        "The identity of '{path}' was not recorded. Select it again.",
                        path=path,
                    )
                continue
            current_fingerprint = os_storage.device_fingerprint(path)
            if (
                expected_fingerprint is None
                or current_fingerprint is None
                or current_fingerprint != expected_fingerprint
            ):
                return _(
                    "The device at '{path}' has changed since review. Select and confirm the target again.",
                    path=path,
                )
            confirmation = self._storage_mount_confirmations.get(part)
            if os_storage.is_disk_or_child_mounted(path) and (
                confirmation is None or not confirmation.isChecked()
            ):
                return _(
                    "'{path}' is now mounted. Review the target and confirm the "
                    "mounted-device warning before flashing.",
                    path=path,
                )
        return None

    def _populate_review(self) -> None:
        assert self.state.prepared is not None
        steps = ruyi_adapter.compute_pretend_steps(
            self.state.prepared, self.state.host_blkdev_map
        )
        self._review_steps.clear()
        for step in steps:
            self._review_steps.append_rich(f" * {step}")
        missing = ruyi_adapter.missing_cmds(self.state.prepared)
        self._review_missing.setText(
            _("Missing required commands: {commands}.", commands=", ".join(missing))
            if missing
            else ""
        )
        needs_fastboot = ruyi_adapter.needs_fastboot_confirmation(self.state.prepared)
        self._fastboot_ok = not needs_fastboot
        self._fastboot_status.setVisible(needs_fastboot)
        self._check_fastboot_btn.setVisible(needs_fastboot)
        if needs_fastboot:
            self._fastboot_status.setText(_("Checking fastboot devices..."))
            self._set_status_kind(self._fastboot_status, None)
            self._check_fastboot_devices()
        else:
            self._fastboot_status.setText("")
        self._proceed_cb.setChecked(False)

    def _review_complete(self) -> bool:
        assert self.state.prepared is not None
        if ruyi_adapter.missing_cmds(self.state.prepared):
            return False
        if (
            ruyi_adapter.needs_fastboot_confirmation(self.state.prepared)
            and not self._fastboot_ok
        ):
            return False
        return self._proceed_cb.isChecked()

    def _populate_done(self) -> None:
        if self.state.flash_ret is None and not self.state.pkg_atoms:
            self._done_label.setText(
                _("No flashing was required. See the message below for next steps.")
            )
            self._set_status_kind(self._done_label, "success")
        elif self.state.flash_ret == 0:
            self._done_label.setText(
                _("It seems the flashing has finished without errors. Happy hacking!")
            )
            self._set_status_kind(self._done_label, "success")
        else:
            self._done_label.setText(
                _(
                    "Flashing failed (exit code {code}). Check the device right now.",
                    code=self.state.flash_ret,
                )
            )
            self._set_status_kind(self._done_label, "error")

        msg = ""
        if self.state.combo is not None and self.state.mr is not None:
            msg = (
                ruyi_adapter.get_postinst_msg(
                    self.state.mr,
                    self.state.combo.entity,
                    self.state.config.lang_code,
                )
                or ""
            )
        self.state.postinst_msg = msg or None
        self._postinst_label.setText(msg)
        self._postinst_label.setVisible(bool(msg))
