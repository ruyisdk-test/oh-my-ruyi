"""Version management and first-install telemetry UI.

Mixed into ProvisionMainWindow to keep the main window
module small.
"""

from __future__ import annotations

from __future__ import annotations
import os
import platform
import shutil
from pathlib import Path
from PySide6.QtCore import (
    QProcess,
    QTimer,
    Qt,
    QUrl,
)
from PySide6.QtGui import QBrush, QColor, QDesktopServices
from PySide6.QtWidgets import (
    QAbstractItemView,
    QFrame,
    QHeaderView,
    QHBoxLayout,
    QInputDialog,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSizePolicy,
    QSplitter,
    QStyle,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)
from ...infra import (
    version_manager,
)
from ...i18n import _
from ..widgets.rich_output import (
    strip_terminal_controls,
)
from .version_dialogs import (
    VersionDownloadDialog as _VersionDownloadDialog,
    VersionTableItem as _VersionTableItem,
)
from ...workers import (
    TelemetrySetupWorker,
    VersionActivationWorker,
    VersionCatalogWorker,
    VersionDeactivationWorker,
    VersionDeleteWorker,
    VersionDownloadWorker,
)
from ._common import _message_box


class VersionManagementMixin:
    def _build_version_manager_tab(self) -> QWidget:
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        title = QLabel("<b>Ruyi Package Manager Versions</b>")
        title.setObjectName("pageTitle")
        layout.addWidget(title)
        description = QLabel(
            "Download standalone ruyi releases into your home directory and choose "
            "which version /usr/local/bin/ruyi activates."
        )
        description.setWordWrap(True)
        layout.addWidget(description)

        self._pm_splitter = QSplitter(Qt.Orientation.Horizontal)
        self._pm_splitter.setChildrenCollapsible(False)
        self._pm_splitter.addWidget(self._build_available_versions_panel())
        self._pm_splitter.addWidget(self._build_installed_versions_panel())
        self._pm_splitter.setStretchFactor(0, 1)
        self._pm_splitter.setStretchFactor(1, 1)
        self._pm_splitter.splitterMoved.connect(self._align_pm_status_heights)
        layout.addWidget(self._pm_splitter, 1)

        self._refresh_pm_versions()
        return tab

    def _build_available_versions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(0, 0, 6, 0)
        layout.addWidget(QLabel("<b>Available downloads</b>"))

        content = QHBoxLayout()
        self._pm_available_table = QTableWidget(0, 4)
        self._configure_pm_table(
            self._pm_available_table,
            ["Version", "Channel", "Architecture", "Released"],
            stretch_column=0,
        )
        self._pm_available_table.setObjectName("availableVersionTable")
        self._pm_available_table.setAccessibleName("Available ruyi versions")
        self._pm_available_table.itemSelectionChanged.connect(self._refresh_pm_buttons)
        content.addWidget(self._pm_available_table, 1)

        buttons = QVBoxLayout()
        buttons.addStretch()
        self._pm_refresh_btn = QPushButton("Refresh")
        self._pm_download_btn = QPushButton("Download")
        self._pm_remove_url_btn = QPushButton("Remove")
        self._pm_add_url_btn = QPushButton("Add URL")
        self._pm_refresh_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._pm_refresh_btn.clicked.connect(self._refresh_pm_catalog)
        self._pm_download_btn.clicked.connect(self._download_selected_pm_version)
        self._pm_remove_url_btn.clicked.connect(self._remove_selected_pm_download_url)
        buttons.addWidget(self._pm_refresh_btn)
        buttons.addWidget(self._pm_download_btn)
        buttons.addWidget(self._pm_remove_url_btn)
        buttons.addWidget(self._pm_add_url_btn)
        buttons.addStretch()
        self._pm_add_url_btn.clicked.connect(self._add_pm_download_url)
        content.addLayout(buttons)
        layout.addLayout(content, 1)

        self._pm_status = self._make_pm_status_label(
            "Showing versions already downloaded on this computer."
        )
        layout.addWidget(self._pm_status)
        return panel

    def _build_installed_versions_panel(self) -> QWidget:
        panel = QWidget()
        layout = QVBoxLayout(panel)
        layout.setContentsMargins(6, 0, 0, 0)
        layout.addWidget(QLabel("<b>Downloaded versions</b>"))

        content = QHBoxLayout()
        self._pm_installed_table = QTableWidget(0, 5)
        self._configure_pm_table(
            self._pm_installed_table,
            ["Version", "Channel", "State", "Size", "Note"],
            stretch_column=0,
        )
        self._pm_installed_table.setObjectName("installedVersionTable")
        self._pm_installed_table.setAccessibleName("Downloaded ruyi versions")
        self._pm_installed_table.itemSelectionChanged.connect(self._refresh_pm_buttons)
        content.addWidget(self._pm_installed_table, 1)

        buttons = QVBoxLayout()
        buttons.addStretch()
        self._pm_local_refresh_btn = QPushButton("Refresh")
        self._pm_delete_btn = QPushButton("Delete")
        self._pm_toggle_activation_btn = QPushButton("Activate")
        self._pm_browse_btn = QPushButton("Browse")
        self._pm_local_refresh_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
        )
        self._pm_local_refresh_btn.setToolTip(
            "Rescan downloaded ruyi binaries from the file system"
        )
        self._pm_browse_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon)
        )
        self._pm_browse_btn.setToolTip(
            "Open the folder containing the selected downloaded binary"
        )
        self._pm_local_refresh_btn.clicked.connect(self._refresh_pm_local_versions)
        self._pm_delete_btn.clicked.connect(self._delete_selected_pm_version)
        self._pm_toggle_activation_btn.clicked.connect(
            self._toggle_selected_pm_version_activation
        )
        self._pm_browse_btn.clicked.connect(self._browse_selected_pm_version)
        buttons.addWidget(self._pm_local_refresh_btn)
        buttons.addWidget(self._pm_delete_btn)
        buttons.addWidget(self._pm_toggle_activation_btn)
        buttons.addWidget(self._pm_browse_btn)
        buttons.addStretch()
        content.addLayout(buttons)
        layout.addLayout(content, 1)

        self._pm_path_status = self._make_pm_status_label()
        layout.addWidget(self._pm_path_status)
        return panel

    @staticmethod
    def _make_pm_status_label(text: str = "") -> QLabel:
        label = QLabel(text)
        label.setObjectName("versionStatus")
        label.setFrameShape(QFrame.Shape.NoFrame)
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        return label

    @staticmethod
    def _configure_pm_table(
        table: QTableWidget,
        headers: list[str],
        *,
        stretch_column: int,
    ) -> None:
        table.setHorizontalHeaderLabels(headers)
        table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
        table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
        table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        table.setAlternatingRowColors(True)
        table.setSortingEnabled(True)
        table.verticalHeader().setVisible(False)
        table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.ResizeToContents
        )
        table.horizontalHeader().setSectionResizeMode(
            stretch_column,
            QHeaderView.ResizeMode.Stretch,
        )

    def _refresh_pm_catalog(self) -> None:
        if self._pm_worker is not None or self._repo_manager_tab.is_busy:
            return
        self._pm_operation = "refresh"
        self._logger.set_terminal_target("pm")
        self._pm_status.setText(_("Checking the latest ruyi releases..."))
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = VersionCatalogWorker()
        self._pm_worker.finished.connect(self._on_pm_catalog_ready)
        self._pm_worker.failed.connect(self._on_pm_worker_failed)
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()

    def _download_selected_pm_version(self) -> None:
        release = self._selected_pm_release()
        if release is not None:
            self._open_pm_download_dialog(release)

    def _open_pm_download_dialog(
        self,
        release: version_manager.RuyiRelease,
    ) -> None:
        if (
            self._pm_worker is not None
            or self._pm_externally_managed
            or self._pm_download_dialog is not None
        ):
            return
        dialog = _VersionDownloadDialog(release, self)
        self._pm_download_dialog = dialog
        dialog.download_requested.connect(
            lambda url, r=release, d=dialog: self._start_pm_download(r, url, d)
        )
        dialog.cancel_requested.connect(lambda d=dialog: self._cancel_pm_download(d))
        dialog.finished.connect(
            lambda _result, d=dialog: self._clear_pm_download_dialog(d)
        )
        dialog.open()

    def _start_pm_download(
        self,
        release: version_manager.RuyiRelease,
        download_url: str,
        dialog: _VersionDownloadDialog,
    ) -> None:
        if (
            dialog is not self._pm_download_dialog
            or self._pm_worker is not None
            or self._pm_externally_managed
        ):
            return
        self._pm_operation = "download"
        self._logger.set_terminal_target("pm")
        self._pm_status.setText(
            _("Downloading ruyi {version}...", version=release.version)
        )
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = VersionDownloadWorker(
            release,
            self._pm_versions_directory,
            download_url,
        )
        self._pm_worker.progress.connect(dialog.update_progress)
        self._pm_worker.finished.connect(self._on_pm_download_finished)
        self._pm_worker.cancelled.connect(self._on_pm_download_cancelled)
        self._pm_worker.failed.connect(self._on_pm_download_failed)
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()

    def _clear_pm_download_dialog(self, dialog: _VersionDownloadDialog) -> None:
        if self._pm_download_dialog is dialog and self._pm_worker is None:
            self._pm_download_dialog = None
            if (
                self._first_use_active
                and self._first_use_operation == "download"
                and self._first_use_binary is None
            ):
                self._first_use_operation = ""
                self._first_use_action = "download"
                self._cleanup_empty_first_use_data_directory()
                setup_dialog = self._first_use_dialog
                if setup_dialog is not None:
                    setup_dialog.set_stage(
                        0,
                        _("The ruyi download dialog was closed."),
                        action="Download and activate",
                        skip="Skip download",
                        kind="warning",
                    )

    def _cancel_pm_download(self, dialog: _VersionDownloadDialog) -> None:
        if dialog is not self._pm_download_dialog:
            return
        worker = self._pm_worker
        if isinstance(worker, VersionDownloadWorker):
            worker.request_cancel()
            self._pm_status.setText(_("Cancelling download..."))
            self._set_status_kind(self._pm_status, None)
            self._pm_download_dialog = None

    def _refresh_pm_local_versions(self) -> None:
        if self._pm_worker is not None:
            return
        self._refresh_pm_versions()

    def _remove_selected_pm_download_url(self) -> None:
        if self._pm_worker is not None or self._pm_externally_managed:
            return
        release = self._selected_pm_release()
        custom_release = next(
            (item for item in self._pm_custom_releases if item is release),
            None,
        )
        if custom_release is None:
            return
        self._pm_custom_releases.remove(custom_release)
        self._pm_status.setText(
            _(
                "Removed transient download URL for ruyi {version}.",
                version=custom_release.version,
            )
        )
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions()

    def _add_pm_download_url(self) -> None:
        if self._pm_worker is not None:
            return
        url, ok = QInputDialog.getText(
            self,
            _("Add ruyi download URL"),
            _("URL ending in ruyi-<semver version>.<arch>:"),
        )
        if not ok or not url.strip():
            return
        try:
            release = version_manager.release_from_url(url)
        except version_manager.VersionManagerError as exc:
            _message_box(QMessageBox.warning, self, "Invalid ruyi URL", str(exc))
            return
        if not version_manager.architecture_is_compatible(release.architecture):
            _message_box(
                QMessageBox.warning,
                self,
                "Incompatible ruyi architecture",
                _(
                    "The URL provides a {architecture} binary, but this computer uses {host}.",
                    architecture=release.architecture,
                    host=version_manager.host_architecture(),
                ),
            )
            return
        all_releases = [*self._pm_catalog_releases, *self._pm_custom_releases]
        if any(
            item.download_urls[0] == release.download_urls[0] for item in all_releases
        ):
            self._pm_status.setText(_("That download URL is already in the table."))
            self._set_status_kind(self._pm_status, "warning")
        else:
            self._pm_custom_releases.append(release)
            self._pm_status.setText(
                _(
                    "Added transient download URL for ruyi {version}.",
                    version=release.version,
                )
            )
            self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions(select_available_url=release.download_urls[0])

    def _activate_selected_pm_version(self) -> None:
        installed = self._selected_pm_installed_version()
        if installed is None or self._pm_worker is not None:
            return

        self._start_pm_activation(installed)

    def _start_pm_activation(
        self,
        installed: version_manager.InstalledVersion,
    ) -> bool:
        if self._pm_worker is not None:
            return False
        binary = installed.path

        state = version_manager.read_activation_state(
            self._pm_activation_link,
            self._pm_versions_directory,
        )
        backup_unmanaged = state.exists and not state.managed
        if backup_unmanaged:
            existing = (
                _("a symbolic link to {target}", target=state.target)
                if state.is_symlink
                else _("an existing file")
            )
            answer = _message_box(
                QMessageBox.question,
                self,
                "Replace existing ruyi command?",
                _(
                    "{path} is {existing} and is not managed by Oh My Ruyi.\n\n"
                    "If you continue, it will be preserved as a .bak backup before "
                    "the selected version is activated.",
                    path=self._pm_activation_link,
                    existing=existing,
                ),
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if answer != QMessageBox.StandardButton.Yes:
                return False

        self._pm_operation = "activate"
        self._logger.set_terminal_target("pm")
        self._pm_status.setText(
            _("Activating ruyi {version}...", version=installed.version)
        )
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = VersionActivationWorker(
            binary,
            self._pm_versions_directory,
            self._pm_activation_link,
            backup_unmanaged=backup_unmanaged,
        )
        self._pm_worker.finished.connect(self._on_pm_activation_finished)
        self._pm_worker.failed.connect(self._on_pm_worker_failed)
        self._pm_worker.password_requested.connect(
            self._on_pm_password_requested,
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()
        return True

    def _toggle_selected_pm_version_activation(self) -> None:
        installed = self._selected_pm_installed_version()
        if installed is None or self._pm_worker is not None:
            return
        active = version_manager.read_activation_state(
            self._pm_activation_link,
            self._pm_versions_directory,
        )
        if active.managed and active.target == installed.path.resolve(strict=False):
            self._deactivate_selected_pm_version()
        else:
            self._activate_selected_pm_version()

    def _delete_selected_pm_version(self) -> None:
        installed = self._selected_pm_installed_version()
        if installed is None or self._pm_worker is not None:
            return
        answer = _message_box(
            QMessageBox.question,
            self,
            "Delete downloaded ruyi?",
            _(
                "Delete ruyi {version} from {path}?",
                version=installed.version,
                path=installed.path,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pm_operation = "delete"
        self._logger.set_terminal_target("pm")
        self._pm_status.setText(
            _("Deleting ruyi {version}...", version=installed.version)
        )
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = VersionDeleteWorker(
            installed.path,
            self._pm_versions_directory,
            self._pm_activation_link,
        )
        self._pm_worker.finished.connect(self._on_pm_delete_finished)
        self._pm_worker.failed.connect(self._on_pm_worker_failed)
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()

    def _deactivate_selected_pm_version(self) -> None:
        if self._pm_worker is not None:
            return
        installed = self._selected_pm_installed_version()
        if installed is None:
            return
        state = version_manager.read_activation_state(
            self._pm_activation_link,
            self._pm_versions_directory,
        )
        if not state.managed or state.target != installed.path.resolve(strict=False):
            return
        answer = _message_box(
            QMessageBox.question,
            self,
            "Deactivate ruyi?",
            _(
                "Remove the managed link {path}?\n\nDownloaded versions and existing "
                "backups will not be removed.",
                path=self._pm_activation_link,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._pm_operation = "deactivate"
        self._logger.set_terminal_target("pm")
        self._pm_status.setText(
            _("Deactivating ruyi {version}...", version=state.version)
        )
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = VersionDeactivationWorker(
            self._pm_versions_directory,
            self._pm_activation_link,
        )
        self._pm_worker.finished.connect(self._on_pm_deactivation_finished)
        self._pm_worker.failed.connect(self._on_pm_worker_failed)
        self._pm_worker.password_requested.connect(
            self._on_pm_password_requested,
            Qt.ConnectionType.BlockingQueuedConnection,
        )
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()

    def _browse_selected_pm_version(self) -> None:
        installed = self._selected_pm_installed_version()
        if installed is None or self._pm_worker is not None:
            return
        if not self._reveal_pm_file(installed.path):
            _message_box(
                QMessageBox.warning,
                self,
                "Could not browse downloaded ruyi",
                _(
                    "Could not show {path} in the file manager.",
                    path=installed.path,
                ),
            )

    @staticmethod
    def _reveal_pm_file(path: Path) -> bool:
        """Show a downloaded binary in the platform's file manager."""
        path = Path(path)
        system = platform.system()
        if system == "Windows":
            started, _ = QProcess.startDetached(
                "explorer.exe",
                [f"/select,{os.fspath(path)}"],
            )
            if started:
                return True
        elif system == "Darwin":
            started, _ = QProcess.startDetached(
                "open",
                ["-R", os.fspath(path)],
            )
            if started:
                return True
        else:
            for program in ("dolphin", "nautilus"):
                if shutil.which(program) is None:
                    continue
                started, _ = QProcess.startDetached(
                    program,
                    ["--select", os.fspath(path)],
                )
                if started:
                    return True

        return QDesktopServices.openUrl(QUrl.fromLocalFile(os.fspath(path.parent)))

    def _on_pm_catalog_ready(self, catalog: version_manager.ReleaseCatalog) -> None:
        self._pm_catalog_releases = list(catalog.releases)
        self._first_use_catalog_error = None
        self._first_use_catalog_pending = False
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Release information loaded."))
        self._pm_status.setToolTip(catalog.source_url)
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions()
        self._first_use_catalog_ready()
        self._run_pending_pm_first_run_check()

    def _on_pm_download_finished(self, path: Path) -> None:
        first_use_download = self._first_use_operation == "download"
        version = path.name.removeprefix("ruyi-")
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Downloaded ruyi {version}.", version=version))
        self._pm_status.setToolTip(os.fspath(path))
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions(select_installed_version=version)
        if first_use_download:
            self._first_use_binary = path
        dialog = self._pm_download_dialog
        if dialog is not None:
            dialog.complete()
            self._pm_download_dialog = None
        if first_use_download:
            self._first_use_operation = ""
            if self._first_use_active:
                self._start_first_use_activation()

    def _on_pm_download_failed(self, msg: str) -> None:
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Download failed. See the download dialog."))
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, "error")
        self._refresh_pm_versions()
        dialog = self._pm_download_dialog
        if dialog is not None:
            dialog.show_failure(msg)

    def _on_pm_download_cancelled(self) -> None:
        first_use_download = self._first_use_operation == "download"
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Download cancelled."))
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, None)
        self._refresh_pm_versions()
        dialog = self._pm_download_dialog
        if dialog is not None:
            dialog.complete_cancellation()
            self._pm_download_dialog = None
        if first_use_download:
            self._first_use_operation = ""
            self._cleanup_empty_first_use_data_directory()
            setup_dialog = self._first_use_dialog
            if self._first_use_active and setup_dialog is not None:
                self._first_use_action = "download"
                setup_dialog.set_stage(
                    0,
                    _("The ruyi download was cancelled."),
                    action="Download and activate",
                    skip="Skip download",
                    kind="warning",
                )

    def _on_pm_activation_finished(
        self,
        result: version_manager.ActivationResult,
    ) -> None:
        first_use_activation = self._first_use_operation == "activate"
        self._cleanup_pm_thread()
        self._pm_status.setText(
            _("Activated ruyi {version}.", version=result.state.version)
        )
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions(select_installed_version=result.state.version)
        if first_use_activation:
            self._first_use_operation = ""
            self._first_use_activated = True
            if self._first_use_active:
                self._start_first_use_repository_step()
            else:
                QTimer.singleShot(0, self._maybe_start_pm_telemetry)
            return
        self._maybe_start_pm_telemetry()

    def _on_pm_delete_finished(
        self,
        installed: version_manager.InstalledVersion,
    ) -> None:
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Deleted ruyi {version}.", version=installed.version))
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions()

    def _on_pm_deactivation_finished(
        self,
        _state: version_manager.ActivationState,
    ) -> None:
        self._cleanup_pm_thread()
        self._pm_status.setText(_("Deactivated the managed ruyi command."))
        self._pm_status.setToolTip(os.fspath(self._pm_activation_link))
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions()

    def _on_pm_telemetry_finished(
        self,
        result: version_manager.TelemetrySetupResult,
    ) -> None:
        self._cleanup_pm_thread()
        self._pm_error_output = ""
        self._pm_status.setText(_("Telemetry mode: {status}", status=_(result.status)))
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, "success")
        self._refresh_pm_versions()

    def _on_pm_worker_failed(self, msg: str) -> None:
        operation = self._pm_operation
        first_use_operation = self._first_use_operation
        first_use_catalog = operation == "refresh" and self._first_use_catalog_pending
        self._cleanup_pm_thread()
        if first_use_catalog:
            self._first_use_catalog_pending = False
        if first_use_operation == "activate":
            self._first_use_operation = ""
        details = "\n\n".join(
            part for part in (self._pm_error_output.strip(), msg.strip()) if part
        )
        self._pm_error_output = ""
        self._pm_status.setText(_("Operation failed. See the error dialog."))
        self._pm_status.setToolTip("")
        self._set_status_kind(self._pm_status, "error")
        self._refresh_pm_versions()
        dialog = self._first_use_dialog
        if self._first_use_active and dialog is not None:
            if first_use_catalog:
                self._first_use_catalog_error = details
                self._first_use_action = "refresh"
                dialog.set_stage(
                    0,
                    _(
                        "Could not load compatible ruyi release information: {message}",
                        message=details,
                    ),
                    action="Retry",
                    skip="Continue without download",
                    kind="error",
                )
                return
            if first_use_operation == "activate":
                self._first_use_action = "activate"
                dialog.set_stage(
                    1,
                    _("Ruyi activation failed: {message}", message=details),
                    action="Retry activation",
                    kind="error",
                )
                return
        if self._first_use_active and first_use_catalog:
            self._first_use_catalog_error = details
            return
        if first_use_catalog:
            return
        if first_use_operation == "activate":
            return
        _message_box(QMessageBox.critical, self, "Operation failed", details)
        if operation == "refresh":
            self._run_pending_pm_first_run_check()

    def _on_pm_password_requested(self, prompt: str, response: dict) -> None:
        password, ok = QInputDialog.getText(
            self,
            _("sudo password required"),
            _(prompt),
            QLineEdit.EchoMode.Password,
        )
        response["password"] = password if ok else None

    def _run_pending_pm_first_run_check(self) -> None:
        if not self._pm_first_run_check_pending:
            return
        self._pm_first_run_check_pending = False
        self._maybe_start_pm_telemetry()

    def _maybe_start_pm_telemetry(self) -> None:
        if self._pm_telemetry_installation.exists() or self._pm_worker is not None:
            return
        state = version_manager.read_activation_state(
            self._pm_activation_link,
            self._pm_versions_directory,
        )
        if not state.managed or not self._pm_activation_link.is_file():
            return

        mode = self._ask_for_pm_telemetry_mode()
        self._pm_operation = "telemetry"
        self._logger.set_terminal_target("pm")
        self._pm_error_output = ""
        self._pm_status.setText(_("Saving telemetry preference and checking status..."))
        self._set_status_kind(self._pm_status, None)
        self._pm_worker = TelemetrySetupWorker(self._pm_activation_link, mode)
        self._pm_worker.finished.connect(self._on_pm_telemetry_finished)
        self._pm_worker.failed.connect(self._on_pm_worker_failed)
        self._pm_worker.process_output.connect(self._on_pm_telemetry_output)
        self._pm_runner.run_worker(self._pm_worker)
        self._refresh_pm_buttons()

    def _on_pm_telemetry_output(self, text: str) -> None:
        self._pm_error_output += strip_terminal_controls(text)

    def _ask_for_pm_telemetry_mode(self) -> version_manager.TelemetryMode:
        upload = _message_box(
            QMessageBox.question,
            self,
            "Ruyi telemetry",
            "This appears to be the first ruyi installation. RuyiSDK sends a "
            "one-time anonymous installation report and keeps additional usage data "
            "on this computer by default. With your permission, non-tracking usage "
            "data will also be uploaded periodically to RuyiSDK team-managed servers "
            "in the Chinese mainland.\n\nAllow periodic telemetry uploads?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if upload == QMessageBox.StandardButton.Yes:
            return "consent"

        opt_out = _message_box(
            QMessageBox.question,
            self,
            "Ruyi telemetry",
            "Do you want to opt out of telemetry collection entirely? Choose No "
            "to keep telemetry data locally without uploading it.",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        return "optout" if opt_out == QMessageBox.StandardButton.Yes else "local"

    def _cleanup_pm_thread(self) -> None:
        self._pm_runner.safe_stop_all()
        self._pm_worker = None
        self._pm_operation = ""

    def _selected_pm_release(self) -> version_manager.RuyiRelease | None:
        row = self._pm_available_table.currentRow()
        item = self._pm_available_table.item(row, 0) if row >= 0 else None
        release = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return release if isinstance(release, version_manager.RuyiRelease) else None

    def _selected_pm_installed_version(
        self,
    ) -> version_manager.InstalledVersion | None:
        row = self._pm_installed_table.currentRow()
        item = self._pm_installed_table.item(row, 0) if row >= 0 else None
        installed = item.data(Qt.ItemDataRole.UserRole) if item is not None else None
        return (
            installed
            if isinstance(installed, version_manager.InstalledVersion)
            else None
        )

    def _refresh_pm_versions(
        self,
        *,
        select_available_url: str | None = None,
        select_installed_version: str | None = None,
    ) -> None:
        self._pm_externally_managed = self._pm_config_externally_managed or (
            version_manager.is_ruyi_externally_managed(self._pm_system_config)
        )
        selected_release = self._selected_pm_release()
        previous_available_url = select_available_url or (
            selected_release.download_urls[0] if selected_release is not None else None
        )
        selected_installed = self._selected_pm_installed_version()
        previous_installed_version = select_installed_version or (
            selected_installed.version if selected_installed is not None else None
        )
        try:
            installed = version_manager.list_installed_versions(
                self._pm_versions_directory
            )
            installed = tuple(
                item
                for item in installed
                if item.architecture == "unknown"
                or version_manager.architecture_is_compatible(item.architecture)
            )
            active = version_manager.read_activation_state(
                self._pm_activation_link,
                self._pm_versions_directory,
            )
        except OSError as exc:
            self._pm_status.setText(
                "Failed to inspect installed versions. See the error dialog."
            )
            self._pm_status.setToolTip("")
            self._set_status_kind(self._pm_status, "error")
            _message_box(
                QMessageBox.critical,
                self,
                "Version inspection failed",
                str(exc),
            )
            installed = ()
            active = version_manager.ActivationState(
                self._pm_activation_link,
                False,
                False,
                False,
                None,
                None,
            )

        latest_release = self._latest_pm_release_for_active(active)
        latest_downloaded = latest_release is not None and any(
            item.channel.casefold() == latest_release.channel.casefold()
            and version_manager.version_sort_key(item.version)
            == version_manager.version_sort_key(latest_release.version)
            for item in installed
        )
        active_is_latest: bool | None = None
        if latest_release is not None and active.managed and active.version is not None:
            active_is_latest = version_manager.version_sort_key(
                active.version
            ) == version_manager.version_sort_key(latest_release.version)
        self._populate_pm_available_table(
            previous_available_url,
            highlight_release=(
                latest_release
                if latest_release is not None and not latest_downloaded
                else None
            ),
        )
        self._populate_pm_installed_table(
            installed,
            active,
            previous_installed_version,
            latest_version=(latest_release.version if latest_release else None),
            latest_channel=(latest_release.channel if latest_release else None),
            active_is_latest=active_is_latest,
        )
        self._refresh_pm_path_status(active)
        self._refresh_pm_buttons()

    def _latest_pm_release_for_active(
        self,
        active: version_manager.ActivationState,
    ) -> version_manager.RuyiRelease | None:
        if not active.managed or active.version is None:
            return None
        channel = version_manager.version_channel(active.version)
        if channel not in {"stable", "testing"}:
            return None
        candidates = [
            release
            for release in self._pm_catalog_releases
            if release.channel.casefold() == channel
        ]
        return max(
            candidates,
            key=lambda item: version_manager.version_sort_key(item.version),
            default=None,
        )

    def _pm_foreground(self, kind: str) -> QBrush:
        return QBrush(QColor(self._theme_colors()[kind]))

    def _populate_pm_available_table(
        self,
        selected_url: str | None,
        *,
        highlight_release: version_manager.RuyiRelease | None = None,
    ) -> None:
        table = self._pm_available_table
        releases = [*self._pm_catalog_releases, *self._pm_custom_releases]
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(len(releases))
        for row, release in enumerate(releases):
            version_item = _VersionTableItem(release.version)
            version_item.setData(Qt.ItemDataRole.UserRole, release)
            table.setItem(row, 0, version_item)
            table.setItem(row, 1, QTableWidgetItem(_(release.channel)))
            architecture = (
                version_manager.normalize_architecture(release.architecture)
                or release.architecture
            )
            table.setItem(row, 2, QTableWidgetItem(architecture))
            table.setItem(row, 3, QTableWidgetItem(release.release_date[:10]))
            if release is highlight_release:
                self._set_pm_row_foreground(table, row, "success")
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.SortOrder.DescendingOrder)
        table.clearSelection()
        if selected_url is not None:
            for row in range(table.rowCount()):
                item = table.item(row, 0)
                release = item.data(Qt.ItemDataRole.UserRole)
                if (
                    isinstance(release, version_manager.RuyiRelease)
                    and release.download_urls[0] == selected_url
                ):
                    table.selectRow(row)
                    break
        table.blockSignals(False)

    def _populate_pm_installed_table(
        self,
        installed: tuple[version_manager.InstalledVersion, ...],
        active: version_manager.ActivationState,
        selected_version: str | None,
        latest_version: str | None = None,
        latest_channel: str | None = None,
        active_is_latest: bool | None = None,
    ) -> None:
        table = self._pm_installed_table
        table.blockSignals(True)
        table.setSortingEnabled(False)
        table.setRowCount(len(installed))
        latest_versions = {release.version for release in self._pm_catalog_releases}
        for row, item in enumerate(installed):
            version_item = _VersionTableItem(item.version)
            version_item.setData(Qt.ItemDataRole.UserRole, item)
            table.setItem(row, 0, version_item)
            is_active = active.managed and active.target == item.path.resolve(
                strict=False
            )
            is_latest = (
                latest_version is not None
                and latest_channel is not None
                and item.channel.casefold() == latest_channel.casefold()
                and version_manager.version_sort_key(item.version)
                == version_manager.version_sort_key(latest_version)
            )
            table.setItem(row, 1, QTableWidgetItem(_(item.channel)))
            activate_item = QTableWidgetItem(_("Activate") if is_active else "")
            if is_active and active_is_latest is False:
                activate_item.setForeground(self._pm_foreground("error"))
            table.setItem(row, 2, activate_item)
            table.setItem(row, 3, QTableWidgetItem(self._format_file_size(item.size)))
            table.setItem(
                row,
                4,
                QTableWidgetItem(
                    _("Latest") if item.version in latest_versions else ""
                ),
            )
            if is_latest and not is_active:
                self._set_pm_row_foreground(table, row, "success")
        table.setSortingEnabled(True)
        table.sortItems(0, Qt.SortOrder.DescendingOrder)
        table.clearSelection()
        if selected_version is not None:
            for row in range(table.rowCount()):
                item = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
                if (
                    isinstance(item, version_manager.InstalledVersion)
                    and item.version == selected_version
                ):
                    table.selectRow(row)
                    break
        table.blockSignals(False)

    def _set_pm_row_foreground(
        self,
        table: QTableWidget,
        row: int,
        kind: str,
    ) -> None:
        foreground = self._pm_foreground(kind)
        for column in range(table.columnCount()):
            item = table.item(row, column)
            if item is not None:
                item.setForeground(foreground)

    @staticmethod
    def _format_file_size(size: int) -> str:
        value = float(size)
        for unit in ("B", "KiB", "MiB", "GiB"):
            if value < 1024 or unit == "GiB":
                return f"{int(value)} {unit}" if unit == "B" else f"{value:.1f} {unit}"
            value /= 1024
        raise AssertionError("unreachable")

    def _align_pm_status_heights(self) -> None:
        labels = (self._pm_status, self._pm_path_status)
        required_heights = []
        for label in labels:
            label.setMinimumHeight(0)
            label.setMaximumHeight(16777215)
            label.updateGeometry()
            required = label.heightForWidth(max(1, label.width()))
            required_heights.append(
                required if required >= 0 else label.sizeHint().height()
            )
        height = max(required_heights)
        for label in labels:
            label.setFixedHeight(height)

    def _refresh_pm_path_status(
        self,
        active: version_manager.ActivationState,
    ) -> None:
        if self._pm_externally_managed:
            self._pm_path_status.setText(
                _(
                    "Version management issue: this system's ruyi package manager is "
                    "configured to have its version managed by the system package manager."
                )
            )
            self._set_status_kind(self._pm_path_status, "error")
            return
        path_state = version_manager.read_path_state(
            self._pm_versions_directory,
            link=self._pm_activation_link,
        )
        if path_state.correct:
            self._pm_path_status.setText(
                _(
                    "PATH ready: ruyi resolves to the managed command at {path}.",
                    path=self._pm_activation_link,
                )
            )
            self._set_status_kind(self._pm_path_status, None)
        elif path_state.command is None:
            if active.managed:
                message = _(
                    "PATH issue: no executable named ruyi was found. Add {path} to PATH.",
                    path=self._pm_activation_link.parent,
                )
            else:
                message = _("PATH issue: no executable named ruyi was found.")
            self._pm_path_status.setText(message)
            self._set_status_kind(self._pm_path_status, "error")
        elif active.managed:
            self._pm_path_status.setText(
                _(
                    "PATH issue: ruyi resolves first to {command}, which is ahead of "
                    "the managed command at {path}.",
                    command=path_state.command,
                    path=self._pm_activation_link,
                )
            )
            self._set_status_kind(self._pm_path_status, "error")
        else:
            self._pm_path_status.setText(
                _(
                    "PATH issue: ruyi resolves to {command}, but no Oh My Ruyi-managed "
                    "version is active.",
                    command=path_state.command,
                )
            )
            self._set_status_kind(self._pm_path_status, "error")

    def _refresh_pm_buttons(self) -> None:
        repo_tab = getattr(self, "_repo_manager_tab", None)
        if repo_tab is not None:
            repo_tab.set_external_busy(
                self._worker is not None
                or self._pm_worker is not None
                or self._download_process is not None
                or self._fastboot_process is not None
            )
        repo_busy = bool(repo_tab is not None and self._repo_manager_tab.is_busy)
        busy = self._pm_worker is not None or repo_busy
        controls_enabled = not busy and not self._pm_externally_managed
        release = self._selected_pm_release()
        installed = self._selected_pm_installed_version()
        try:
            active = version_manager.read_activation_state(
                self._pm_activation_link,
                self._pm_versions_directory,
            )
        except OSError:
            active = version_manager.ActivationState(
                self._pm_activation_link,
                False,
                False,
                False,
                None,
                None,
            )
        release_is_installed = (
            version_manager.binary_path(
                release.version,
                self._pm_versions_directory,
            ).is_file()
            if release is not None
            else False
        )
        selected_is_active = (
            installed is not None
            and active.managed
            and active.target == installed.path.resolve(strict=False)
        )
        self._pm_available_table.setEnabled(controls_enabled)
        self._pm_installed_table.setEnabled(controls_enabled)
        self._pm_refresh_btn.setEnabled(controls_enabled)
        self._pm_local_refresh_btn.setEnabled(controls_enabled)
        self._pm_add_url_btn.setEnabled(controls_enabled)
        self._pm_remove_url_btn.setEnabled(
            controls_enabled
            and release is not None
            and any(item is release for item in self._pm_custom_releases)
        )
        self._pm_download_btn.setEnabled(
            controls_enabled and release is not None and not release_is_installed
        )
        self._pm_delete_btn.setEnabled(
            controls_enabled and installed is not None and not selected_is_active
        )
        self._pm_toggle_activation_btn.setText(
            _("Deactivate" if selected_is_active else "Activate")
        )
        self._pm_toggle_activation_btn.setEnabled(
            controls_enabled and installed is not None
        )
        self._pm_browse_btn.setEnabled(controls_enabled and installed is not None)
