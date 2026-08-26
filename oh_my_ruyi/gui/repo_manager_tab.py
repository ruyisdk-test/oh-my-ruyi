"""Qt repository management backed by ruyi's imported Python APIs."""

from __future__ import annotations

import os
import signal
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import QProcess, QProcessEnvironment, QTimer, Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QLabel,
    QMessageBox,
    QSplitter,
    QVBoxLayout,
    QWidget,
)

from ..services import repo_manager
from ..runtime.i18n import _, translate_widget_tree
from ..runtime.rich_output import strip_terminal_controls
from ..processes.environment import configure_ruyi_qprocess_environment
from ..ui.repo_dialogs import RepoSourceDialog, RepoUpdateDialog
from ..ui.repo_page import build_configured_panel, build_preset_panel
from ..ui.repo_tables import populate_repository_tables

_REPO_ROLE = Qt.ItemDataRole.UserRole

_RepoSourceDialog = RepoSourceDialog
_RepoUpdateDialog = RepoUpdateDialog


class RepoManagementTab(QWidget):
    """Manage user-local repositories without invoking a managed ruyi binary."""

    configuration_changed = Signal(str)
    repository_updated = Signal(str)
    repository_update_finished = Signal(str, bool, str)
    busy_changed = Signal(bool)
    provision_update_finished = Signal(bool, str)

    def __init__(
        self,
        *,
        config_path: Path | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self._config_path = (
            repo_manager.user_config_path()
            if config_path is None
            else Path(config_path)
        )
        self._repos: tuple[repo_manager.ConfiguredRepo, ...] = ()
        self._process: QProcess | None = None
        self._news_process: QProcess | None = None
        self._updating_repo_id: str | None = None
        self._update_success_message = ""
        self._close_update_dialog_on_success = False
        self._provision_update = False
        self._provision_update_succeeded = False
        self._cancel_requested = False
        self._process_output = bytearray()
        self._external_busy = False
        self._update_dialog: _RepoUpdateDialog | None = None
        self._kill_timer = QTimer(self)
        self._kill_timer.setSingleShot(True)
        self._kill_timer.setInterval(1500)
        self._kill_timer.timeout.connect(self._force_kill_process)
        self._build_ui()
        translate_widget_tree(self)
        self.reload()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(10)
        title = QLabel("<b>Ruyi Repository Management</b>")
        title.setObjectName("pageTitle")
        root.addWidget(title)
        description = QLabel(
            "Choose a preset repository on the left to add it to the local configuration. "
            "The right side shows repositories in their configuration order."
        )
        description.setWordWrap(True)
        root.addWidget(description)

        self.splitter = QSplitter(Qt.Orientation.Horizontal)
        self.splitter.setChildrenCollapsible(False)
        self.splitter.addWidget(self._build_presets_panel())
        self.splitter.addWidget(self._build_configured_panel())
        self.splitter.setStretchFactor(0, 1)
        self.splitter.setStretchFactor(1, 2)
        self.splitter.setSizes([320, 640])
        root.addWidget(self.splitter, 1)
        self.status = QLabel("")
        self.status.setObjectName("repoStatus")
        self.status.setWordWrap(True)
        root.addWidget(self.status)

    def _build_presets_panel(self) -> QWidget:
        widgets = build_preset_panel(
            refresh_buttons=self._refresh_buttons,
            add_selected=self._add_selected_preset,
        )
        self.preset_table = widgets.table
        self.add_button = widgets.add_button
        return widgets.panel

    def _build_configured_panel(self) -> QWidget:
        widgets = build_configured_panel(
            refresh_buttons=self._refresh_buttons,
            reload=self.reload,
            edit_selected=self._edit_selected,
            remove_selected=self._remove_selected,
            toggle_selected=self._toggle_selected,
            update_selected=self._update_selected,
        )
        self.configured_table = widgets.table
        self.refresh_button = widgets.refresh_button
        self.edit_button = widgets.edit_button
        self.remove_button = widgets.remove_button
        self.toggle_button = widgets.toggle_button
        self.update_button = widgets.update_button
        return widgets.panel

    @property
    def is_busy(self) -> bool:
        return self._process is not None or self._news_process is not None

    @property
    def can_cancel(self) -> bool:
        return self.is_busy

    @property
    def default_repo_active(self) -> bool:
        return any(repo.is_default and repo.active for repo in self._repos)

    @property
    def provision_update_succeeded(self) -> bool:
        return self._provision_update_succeeded

    @property
    def can_start_provision_update(self) -> bool:
        return not (
            self._provision_update_succeeded or self.is_busy or self._external_busy
        )

    def set_external_busy(self, busy: bool) -> None:
        self._external_busy = busy
        self._refresh_buttons()

    def start_provision_update(self) -> None:
        """Update the active default repository before provisioning starts."""
        if not self.can_start_provision_update:
            return
        default = next((repo for repo in self._repos if repo.is_default), None)
        if default is None or not default.active:
            self.provision_update_finished.emit(
                False,
                _(
                    "Enable the ruyisdk repository in Repo Management to load device metadata."
                ),
            )
            return
        self._provision_update = True
        self._start_update(
            default.id,
            _("RuyiSDK metadata repository is ready."),
        )

    def choose_default_source_and_update(self) -> bool:
        """Prompt for the default mirror and update it through the normal path."""
        if self.is_busy or self._external_busy:
            return False
        default = next((repo for repo in self._repos if repo.is_default), None)
        if default is None:
            return False
        configured = default.configured_source or repo_manager.RepoSource()
        dialog = _RepoSourceDialog(
            _("Choose RuyiSDK mirror"),
            remote=default.remote or "",
            local=configured.local or "",
            branch=default.branch or "",
            priority=0,
            source_options=repo_manager.DEFAULT_REPO_SOURCES,
            name_enabled=False,
            priority_enabled=False,
            parent=self,
        )
        dialog.help_label.setText(
            _(
                "Choose a RuyiSDK mirror preset or enter a custom remote URL. The "
                "selected repository will be enabled and updated."
            )
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return False
        source, _priority, _name = dialog.values()

        def apply_source() -> None:
            repo_manager.edit_default_repo(self._config_path, default, source)
            if not default.active:
                repo_manager.set_enabled(self._config_path, default, True)

        if not self._apply_mutation(
            default.id,
            _("Updated the default repository configuration."),
            apply_source,
        ):
            return False
        return self._start_update(
            default.id,
            _("Updated {repo_id}.", repo_id=default.id),
            close_dialog_on_success=True,
        )

    def cancel_current_update(self) -> None:
        """Cancel an active repository update using the existing process path."""
        self._cancel_process()

    def reload(self) -> None:
        if self.is_busy:
            return
        try:
            self._repos = repo_manager.read_configured_repos(self._config_path)
        except repo_manager.RepoManagerError as exc:
            self._repos = ()
            self._set_status(
                _("Failed to read repository configuration."),
                "error",
                details=str(exc),
            )
        else:
            self._populate_tables()
            self._set_status(_("Repository configuration loaded."), None)
        self._refresh_buttons()

    def _populate_tables(self) -> None:
        populate_repository_tables(
            self.preset_table,
            self.configured_table,
            repo_manager.PRESET_REPOS,
            self._repos,
            data_role=_REPO_ROLE,
        )

    def _selected_preset(self) -> repo_manager.RepoPreset | None:
        row = self.preset_table.currentRow()
        item = self.preset_table.item(row, 0) if row >= 0 else None
        value = item.data(_REPO_ROLE) if item is not None else None
        return value if isinstance(value, repo_manager.RepoPreset) else None

    def _selected_repo(self) -> repo_manager.ConfiguredRepo | None:
        row = self.configured_table.currentRow()
        item = self.configured_table.item(row, 0) if row >= 0 else None
        value = item.data(_REPO_ROLE) if item is not None else None
        return value if isinstance(value, repo_manager.ConfiguredRepo) else None

    def _refresh_buttons(self) -> None:
        busy = self.is_busy or self._external_busy
        preset = self._selected_preset()
        repo = self._selected_repo()
        configured_ids = {item.id for item in self._repos}
        self.preset_table.setEnabled(not busy)
        self.configured_table.setEnabled(not busy)
        self.add_button.setEnabled(
            not busy and preset is not None and preset.id not in configured_ids
        )
        self.refresh_button.setEnabled(not busy)
        self.edit_button.setEnabled(not busy and repo is not None)
        self.remove_button.setEnabled(
            not busy and repo is not None and not repo.is_default
        )
        self.toggle_button.setEnabled(not busy and repo is not None)
        self.toggle_button.setText(
            _("Disable" if repo is not None and repo.active else "Enable")
        )
        self.update_button.setEnabled(not busy and repo is not None and repo.active)

    def _add_selected_preset(self) -> None:
        preset = self._selected_preset()
        if preset is None or self.is_busy or self._external_busy:
            return
        source = preset.sources[0] if preset.sources else repo_manager.RepoSource()
        dialog = _RepoSourceDialog(
            _("Add {name}", name=preset.name),
            name=preset.name,
            remote=source.remote or "",
            local=source.local or "",
            branch=source.branch or "",
            priority=10,
            source_options=preset.sources,
            name_enabled=False,
            parent=self,
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        selected, priority, _name = dialog.values()
        assert priority is not None
        self._apply_mutation(
            preset.id,
            _(
                "Added {repo_id} as a disabled repository.",
                repo_id=preset.id,
            ),
            lambda: repo_manager.add_repo(
                self._config_path, preset, selected, priority
            ),
        )

    def _edit_selected(self) -> None:
        repo = self._selected_repo()
        if repo is None or self.is_busy or self._external_busy:
            return
        if repo.is_default:
            configured = repo.configured_source or repo_manager.RepoSource()
            dialog = _RepoSourceDialog(
                _("Edit ruyisdk repository"),
                remote=configured.remote or "",
                local=configured.local or "",
                branch=configured.branch or "",
                priority=0,
                source_options=repo_manager.DEFAULT_REPO_SOURCES,
                name_enabled=False,
                priority_enabled=False,
                allow_empty_source=True,
                parent=self,
            )
            dialog.help_label.setText(
                _(
                    "Empty fields remove user overrides. Ruyi then uses its built-in remote "
                    "and main branch; local is optional. ID, name, and priority are fixed."
                )
            )
            dialog.remote_edit.setPlaceholderText(repo.remote or "")
            dialog.branch_edit.setPlaceholderText(repo.branch or "")
            if dialog.exec() != QDialog.DialogCode.Accepted:
                return
            source, _priority, _name = dialog.values()
            if not self._apply_mutation(
                repo.id,
                _("Updated the default repository configuration."),
                lambda: repo_manager.edit_default_repo(self._config_path, repo, source),
                require_change=True,
            ):
                return
            if repo.active:
                self._start_update(
                    repo.id,
                    _("Updated {repo_id}.", repo_id=repo.id),
                )
            return

        configured = repo.configured_source or repo_manager.RepoSource(
            repo.remote,
            repo.local,
            repo.branch,
        )
        dialog = _RepoSourceDialog(
            _("Edit {repo_id}", repo_id=repo.id),
            name=repo.name,
            remote=configured.remote or "",
            local=configured.local or "",
            branch=configured.branch or "",
            priority=repo.priority,
            source_options=tuple(
                option
                for preset in repo_manager.PRESET_REPOS
                if preset.id == repo.id
                for option in preset.sources
            ),
            name_enabled=False,
            parent=self,
        )
        dialog.help_label.setText(
            _(
                "ID and name come from the preset. Remote, local path, branch, and "
                "priority are stored through ruyi's configuration API. Local path is "
                "read-only."
            )
        )
        if dialog.exec() != QDialog.DialogCode.Accepted:
            return
        _source, priority, _name = dialog.values()
        assert priority is not None
        if priority == repo.priority and _source == configured:
            return
        if not self._apply_mutation(
            repo.id,
            _("Updated {repo_id}.", repo_id=repo.id),
            lambda: repo_manager.edit_repo(self._config_path, repo, _source, priority),
        ):
            return
        if repo.active:
            self._start_update(
                repo.id,
                _("Updated {repo_id}.", repo_id=repo.id),
            )

    def _remove_selected(self) -> None:
        repo = self._selected_repo()
        if repo is None or repo.is_default or self.is_busy or self._external_busy:
            return
        answer = QMessageBox.question(
            self,
            _("Remove repository"),
            _(
                "Remove '{repo_id}' from the local ruyi configuration? Cached data will be kept.",
                repo_id=repo.id,
            ),
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )
        if answer != QMessageBox.StandardButton.Yes:
            return
        self._apply_mutation(
            repo.id,
            _("Removed {repo_id}.", repo_id=repo.id),
            lambda: repo_manager.remove_repo(self._config_path, repo),
        )

    def _toggle_selected(self) -> None:
        repo = self._selected_repo()
        if repo is None or self.is_busy or self._external_busy:
            return
        enabled = not repo.active
        if not self._apply_mutation(
            repo.id,
            _(
                "Enabled {repo_id}." if enabled else "Disabled {repo_id}.",
                repo_id=repo.id,
            ),
            lambda: repo_manager.set_enabled(self._config_path, repo, enabled),
        ):
            return
        if enabled:
            self._start_update(
                repo.id,
                _("Enabled and updated {repo_id}.", repo_id=repo.id),
            )

    def _update_selected(self) -> None:
        repo = self._selected_repo()
        if repo is None or not repo.active or self.is_busy or self._external_busy:
            return
        self._start_update(repo.id, _("Updated {repo_id}.", repo_id=repo.id))

    def _apply_mutation(
        self,
        repo_id: str,
        success_message: str,
        operation: Callable[[], object],
        *,
        require_change: bool = False,
    ) -> bool:
        try:
            result = operation()
        except repo_manager.RepoManagerError as exc:
            self._set_status(_("Repository operation failed."), "error")
            QMessageBox.critical(
                self,
                _("Repository operation failed"),
                _(str(exc)),
            )
            return False
        if require_change and result is False:
            return False
        if repo_id == repo_manager.DEFAULT_REPO_ID:
            self._provision_update_succeeded = False
        self.reload()
        self.configuration_changed.emit(repo_id)
        self._set_status(success_message, None)
        return True

    def _start_update(
        self,
        repo_id: str,
        success_message: str,
        *,
        close_dialog_on_success: bool = False,
    ) -> bool:
        if self.is_busy or self._external_busy:
            return False
        self._updating_repo_id = repo_id
        self._update_success_message = success_message
        self._close_update_dialog_on_success = close_dialog_on_success
        self._cancel_requested = False
        self._process_output.clear()
        dialog = _RepoUpdateDialog(repo_id, self)
        self._update_dialog = dialog
        dialog.cancel_requested.connect(self._cancel_process)
        dialog.read_news_requested.connect(
            lambda d=dialog: self._start_news_action(d, "read")
        )
        dialog.mark_all_news_read_requested.connect(
            lambda d=dialog: self._start_news_action(d, "mark")
        )

        process = QProcess(self)
        self._process = process
        process.setProgram(sys.executable)
        process.setArguments(
            [
                "-m",
                "oh_my_ruyi.repo_update_child",
                os.fspath(self._config_path),
                repo_id,
            ]
        )
        env = QProcessEnvironment.systemEnvironment()
        configure_ruyi_qprocess_environment(env, unbuffered=True, telemetry_optout=True)
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(self._read_process_output)
        process.finished.connect(
            lambda code, status, p=process: self._on_process_finished(p, code, status)
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_process_error(p, error)
        )
        self._set_status(
            _("Updating repository {repo_id}...", repo_id=repo_id),
            None,
        )
        self.busy_changed.emit(True)
        self._refresh_buttons()
        process.start()
        dialog.open()
        return True

    def _read_process_output(self) -> None:
        if self._process is None:
            return
        data = bytes(self._process.readAllStandardOutput())
        self._process_output.extend(data)
        if self._update_dialog is not None:
            self._update_dialog.append_output_bytes(data)

    def _on_process_finished(self, process: QProcess, code: int, _status) -> None:
        if process is not self._process:
            return
        self._kill_timer.stop()
        self._read_process_output()
        self._process = None
        process.deleteLater()
        if self._cancel_requested:
            self._finish_update(False, _("Repository update cancelled."))
            return
        if code != 0:
            output = strip_terminal_controls(
                bytes(self._process_output).decode(errors="replace")
            ).strip()
            self._finish_update(
                False,
                _("Repository update failed (exit code {code}).", code=code),
                details=output or None,
            )
            return
        self._finish_update(True, self._update_success_message)

    def _on_process_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process is not self._process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._finish_update(
                False,
                _("Failed to start the repository update process."),
            )
        # Terminating an update reports Crashed before finished. The finished
        # handler owns cancellation classification and final output collection.

    def _cancel_process(self) -> None:
        process = self._process
        if process is None or self._cancel_requested:
            return
        self._cancel_requested = True
        if self._update_dialog is not None:
            self._update_dialog.cancel_button.setEnabled(False)
        pid = process.processId()
        if pid > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGTERM)
            except (ProcessLookupError, PermissionError):
                process.terminate()
        else:
            process.terminate()
        self._kill_timer.start()

    def _force_kill_process(self) -> None:
        process = self._process
        if process is None:
            return
        pid = process.processId()
        if pid > 0 and hasattr(os, "killpg"):
            try:
                os.killpg(pid, signal.SIGKILL)
            except (ProcessLookupError, PermissionError):
                pass
        process.kill()

    def _finish_update(
        self,
        success: bool,
        message: str,
        *,
        details: str | None = None,
    ) -> None:
        self._kill_timer.stop()
        process = self._process
        self._process = None
        if process is not None:
            process.deleteLater()
        repo_id = self._updating_repo_id
        provision_update = self._provision_update
        close_dialog_on_success = self._close_update_dialog_on_success
        self._updating_repo_id = None
        self._provision_update = False
        self._close_update_dialog_on_success = False
        self._cancel_requested = False
        self._process_output.clear()
        dialog = self._update_dialog
        self._update_dialog = None
        self.busy_changed.emit(False)
        self._refresh_buttons()
        self._set_status(
            message,
            None if success else "error",
            details=details if dialog is None else None,
        )
        if dialog is not None:
            dialog.append_output_bytes(b"", final=True)
            if details and not dialog.log.toPlainText().strip():
                dialog.log.append_plain_status(details)
            dialog.complete(success)
            if success and close_dialog_on_success:
                dialog.accept()
        if success and (repo_id == repo_manager.DEFAULT_REPO_ID or provision_update):
            self._provision_update_succeeded = True
        if success and repo_id is not None and not provision_update:
            self.repository_updated.emit(repo_id)
        if repo_id is not None and not provision_update:
            self.repository_update_finished.emit(repo_id, success, message)
        if provision_update:
            self.provision_update_finished.emit(success, message)

    def _start_news_action(self, dialog: _RepoUpdateDialog, action: str) -> None:
        if self._news_process is not None:
            return
        process = QProcess(self)
        self._news_process = process
        process.setProgram(sys.executable)
        process.setArguments(
            [
                "-m",
                "oh_my_ruyi.repo_news_child",
                os.fspath(self._config_path),
                action,
            ]
        )
        env = QProcessEnvironment.systemEnvironment()
        configure_ruyi_qprocess_environment(env, unbuffered=True, telemetry_optout=True)
        process.setProcessEnvironment(env)
        process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
        process.readyReadStandardOutput.connect(
            lambda p=process, d=dialog: self._read_news_output(p, d)
        )
        process.finished.connect(
            lambda code, status, p=process, d=dialog: self._on_news_finished(
                p, d, action, code, status
            )
        )
        process.errorOccurred.connect(
            lambda error, p=process, d=dialog: self._on_news_error(p, d, error)
        )
        dialog.append_output(
            f"\n{_('Reading unread news...')}\n"
            if action == "read"
            else f"\n{_('Marking all news as read...')}\n"
        )
        self.busy_changed.emit(True)
        self._refresh_buttons()
        process.start()

    @staticmethod
    def _read_news_output(process: QProcess, dialog: _RepoUpdateDialog) -> None:
        dialog.append_output_bytes(bytes(process.readAllStandardOutput()))

    def _on_news_finished(
        self,
        process: QProcess,
        dialog: _RepoUpdateDialog,
        action: str,
        code: int,
        _status,
    ) -> None:
        if process is not self._news_process:
            return
        self._read_news_output(process, dialog)
        dialog.append_output_bytes(b"", final=True)
        self._news_process = None
        process.deleteLater()
        if code == 0:
            dialog.append_output(
                f"\n{_('News read and marked as read.')}\n"
                if action == "read"
                else f"\n{_('All news marked as read.')}\n"
            )
        else:
            dialog.append_output(
                f"\n{_('News operation failed with exit code {code}.', code=code)}\n"
            )
        dialog.finish_news_action()
        self.busy_changed.emit(False)
        self._refresh_buttons()

    def _on_news_error(
        self,
        process: QProcess,
        dialog: _RepoUpdateDialog,
        error: QProcess.ProcessError,
    ) -> None:
        if process is not self._news_process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            dialog.append_output(f"\n{_('Failed to start the news operation.')}\n")
            self._news_process = None
            process.deleteLater()
            dialog.finish_news_action()
            self.busy_changed.emit(False)
            self._refresh_buttons()

    def _set_status(
        self,
        text: str,
        kind: str | None,
        *,
        details: str | None = None,
    ) -> None:
        self.status.setText(text)
        self.status.setText(_(self.status.text()))
        self.status.setToolTip(_(details) if details else "")
        self.status.setProperty("statusKind", kind or "")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.status.update()


__all__ = ["RepoManagementTab"]
