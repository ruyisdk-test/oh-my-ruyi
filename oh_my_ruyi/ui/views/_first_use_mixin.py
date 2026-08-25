"""First-use setup flow orchestration.

Mixed into ProvisionMainWindow to keep the main window
module small.
"""

from __future__ import annotations

from __future__ import annotations
from PySide6.QtCore import (
    QTimer,
)
from ...infra import (
    repo_manager,
    version_manager,
)
from .first_use import FirstUseDialog
from ...i18n import _
from ...workers import (
    VersionDownloadWorker,
)


class FirstUseMixin:
    def _open_first_use_setup(self) -> None:
        if not self._first_use_active or self._first_use_dialog is not None:
            return
        dialog = FirstUseDialog(self)
        self._first_use_dialog = dialog
        dialog.action_requested.connect(self._run_first_use_action)
        dialog.skip_requested.connect(self._skip_first_use_download)
        dialog.exit_requested.connect(self._exit_first_use_setup)
        dialog.finished.connect(
            lambda _result, d=dialog: self._clear_first_use_dialog(d)
        )
        dialog.show()
        dialog.raise_()
        dialog.activateWindow()
        if self._first_use_catalog_error is not None:
            self._first_use_action = "refresh"
            dialog.set_stage(
                0,
                _(
                    "Could not load compatible ruyi release information: {message}",
                    message=self._first_use_catalog_error,
                ),
                action="Retry",
                skip="Continue without download",
                kind="error",
            )
        elif self._pm_catalog_releases:
            self._first_use_catalog_ready()

    def _clear_first_use_dialog(self, dialog: FirstUseDialog) -> None:
        if self._first_use_dialog is dialog:
            self._first_use_dialog = None
        dialog.deleteLater()

    def _exit_first_use_setup(self) -> None:
        if not self._first_use_active:
            return
        self._first_use_active = False
        self._first_use_action = ""
        operation = self._first_use_operation
        if operation == "download":
            dialog = self._pm_download_dialog
            if dialog is not None:
                dialog.reject()
            elif isinstance(self._pm_worker, VersionDownloadWorker):
                self._pm_worker.request_cancel()
        elif operation == "repository":
            self._repo_manager_tab.cancel_current_update()
        if self._first_use_activated:
            QTimer.singleShot(0, self._maybe_start_pm_telemetry)

    def _run_first_use_action(self) -> None:
        if not self._first_use_active:
            return
        action = self._first_use_action
        if action == "refresh":
            self._first_use_catalog_pending = True
            self._refresh_pm_catalog()
        elif action == "download":
            self._start_first_use_download()
        elif action == "activate":
            self._start_first_use_activation()
        elif action == "repository":
            self._choose_first_use_repository()
        elif action == "finish":
            self._finish_first_use_setup()

    def _skip_first_use_download(self) -> None:
        if not self._first_use_active or self._first_use_operation:
            return
        self._first_use_release = None
        self._first_use_binary = None
        self._start_first_use_repository_step()

    def _first_use_catalog_ready(self) -> None:
        dialog = self._first_use_dialog
        if not self._first_use_active or dialog is None:
            return
        if self._pm_externally_managed:
            self._first_use_action = ""
            dialog.set_stage(
                0,
                _(
                    "This system delegates ruyi version management to the system "
                    "package manager, so automatic setup is unavailable."
                ),
                skip="Continue without download",
                kind="error",
            )
            return
        releases = list(self._pm_catalog_releases)
        if not releases:
            self._first_use_action = "refresh"
            dialog.set_stage(
                0,
                _("No compatible ruyi release is available for this computer."),
                action="Retry",
                skip="Continue without download",
                kind="error",
            )
            return
        stable = [
            release for release in releases if release.channel.casefold() == "stable"
        ]
        candidates = stable or releases
        self._first_use_release = max(
            candidates,
            key=lambda release: version_manager.version_sort_key(release.version),
        )
        self._first_use_action = "download"
        dialog.set_stage(
            0,
            _(
                "Download ruyi {version} ({channel}) and activate it at {path}?",
                version=self._first_use_release.version,
                channel=self._first_use_release.channel,
                path=self._pm_activation_link,
            ),
            action="Download and activate",
            skip="Skip download",
        )

    def _start_first_use_download(self) -> None:
        release = self._first_use_release
        dialog = self._first_use_dialog
        if release is None or dialog is None or self._pm_worker is not None:
            return
        self._first_use_operation = "download"
        self._first_use_action = ""
        self._first_use_binary = None
        self._open_pm_download_dialog(release)
        if self._pm_download_dialog is None:
            self._first_use_operation = ""
            self._first_use_action = "download"
            dialog.set_stage(
                0,
                _("Could not open the ruyi download dialog."),
                action="Download and activate",
                skip="Skip download",
                kind="error",
            )
        else:
            dialog.set_stage(
                0,
                _("Select a download URL in the download dialog."),
                busy=True,
            )

    def _start_first_use_activation(self) -> None:
        path = self._first_use_binary
        dialog = self._first_use_dialog
        if path is None or not path.is_file() or dialog is None:
            return
        self._first_use_action = ""
        self._first_use_operation = "activate"
        dialog.set_stage(
            1,
            _("Activating the downloaded ruyi command..."),
            busy=True,
        )
        installed = version_manager.inspect_installed_version(path)
        if not self._start_pm_activation(installed):
            self._first_use_operation = ""
            self._first_use_action = "activate"
            dialog.set_stage(
                1,
                _("Ruyi activation was cancelled."),
                action="Retry activation",
                kind="warning",
            )

    def _start_first_use_repository_step(self) -> None:
        if not self._first_use_active:
            self._first_use_operation = ""
            return
        dialog = self._first_use_dialog
        if dialog is None:
            return
        self._first_use_operation = "repository"
        self._first_use_action = ""
        self._tabs.setCurrentWidget(self._repo_manager_tab)
        dialog.set_stage(
            2,
            _("Choose the mirror used by the default ruyisdk repository."),
        )
        QTimer.singleShot(0, self._choose_first_use_repository)

    def _choose_first_use_repository(self) -> None:
        dialog = self._first_use_dialog
        if (
            not self._first_use_active
            or dialog is None
            or self._repo_manager_tab.is_busy
        ):
            return
        self._first_use_action = ""
        dialog.set_stage(
            2,
            _("Choose a mirror in the repository source dialog."),
            busy=True,
        )
        if self._repo_manager_tab.choose_default_source_and_update():
            dialog.set_stage(
                2,
                _("Updating the selected ruyisdk mirror..."),
                busy=True,
            )
            return
        self._first_use_action = "repository"
        dialog.set_stage(
            2,
            _("Mirror selection was cancelled. Choose a mirror to continue."),
            action="Choose mirror",
            kind="warning",
        )

    def _on_first_use_repo_update_finished(
        self,
        repo_id: str,
        success: bool,
        message: str,
    ) -> None:
        if (
            not self._first_use_active
            or self._first_use_operation != "repository"
            or repo_id != repo_manager.DEFAULT_REPO_ID
        ):
            return
        dialog = self._first_use_dialog
        if dialog is None:
            return
        if not success:
            self._first_use_action = "repository"
            dialog.set_stage(
                2,
                _("Repository update failed: {message}", message=message),
                action="Choose mirror",
                kind="error",
            )
            return
        self._first_use_operation = ""
        self._first_use_action = "finish"
        self._tabs.setCurrentWidget(self._about_tab)
        dialog.set_stage(
            3,
            _("First-use setup is complete. Review the result on the About page."),
            action="Finish",
            kind="success",
        )

    def _finish_first_use_setup(self) -> None:
        run_telemetry_setup = self._first_use_activated
        self._first_use_active = False
        self._first_use_action = ""
        self._first_use_operation = ""
        dialog = self._first_use_dialog
        if dialog is not None:
            dialog.accept()
        if run_telemetry_setup:
            QTimer.singleShot(0, self._maybe_start_pm_telemetry)

    def _cleanup_empty_first_use_data_directory(self) -> None:
        """Do not let a cancelled first download suppress setup on the next run."""
        if self._first_use_data_directory != self._pm_versions_directory.parent:
            return
        try:
            self._pm_versions_directory.rmdir()
            self._first_use_data_directory.rmdir()
        except OSError:
            pass
