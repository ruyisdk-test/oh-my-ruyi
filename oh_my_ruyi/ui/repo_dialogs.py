"""Reusable dialogs for repository configuration and update output."""

from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from ..services import repo_manager
from ..runtime.i18n import _, translate_widget_tree
from ..runtime.rich_output import RichTextView


class RepoUpdateDialog(QDialog):
    """Show imported ruyi update output and request cancellation."""

    cancel_requested = Signal()
    read_news_requested = Signal()
    mark_all_news_read_requested = Signal()

    def __init__(self, repo_id: str, parent=None) -> None:
        super().__init__(parent)
        self.setAttribute(Qt.WidgetAttribute.WA_DeleteOnClose)
        self.setWindowTitle(_("Repository update"))
        self.resize(760, 440)
        self._news_actions_started = False
        self._news_action_running = False
        self._update_finished = False
        layout = QVBoxLayout(self)
        layout.addWidget(
            QLabel(
                _(
                    "Running: {command}",
                    command=f"ruyi update --repo {repo_id}",
                )
            )
        )
        self.log = RichTextView()
        layout.addWidget(self.log, 1)
        news_row = QHBoxLayout()
        self.read_news_button = QPushButton("Read unread news")
        self.mark_all_news_read_button = QPushButton("Mark all news as read")
        self.read_news_button.setAccessibleName("Read unread news")
        self.mark_all_news_read_button.setAccessibleName("Mark all news as read")
        self.read_news_button.clicked.connect(self._request_read_news)
        self.mark_all_news_read_button.clicked.connect(self._request_mark_all_news_read)
        self.read_news_button.setEnabled(False)
        self.mark_all_news_read_button.setEnabled(False)
        news_row.addWidget(self.read_news_button)
        news_row.addWidget(self.mark_all_news_read_button)
        news_row.addStretch()
        layout.addLayout(news_row)
        self.cancel_button = QPushButton("Cancel")
        self.cancel_button.clicked.connect(self.reject)
        row = QHBoxLayout()
        row.addStretch()
        row.addWidget(self.cancel_button)
        layout.addLayout(row)
        translate_widget_tree(self)

    def _request_read_news(self) -> None:
        if self._news_actions_started:
            return
        self._news_actions_started = True
        self._news_action_running = True
        self.read_news_button.setEnabled(False)
        self.mark_all_news_read_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.read_news_requested.emit()

    def _request_mark_all_news_read(self) -> None:
        if self._news_actions_started:
            return
        self._news_actions_started = True
        self._news_action_running = True
        self.read_news_button.setEnabled(False)
        self.mark_all_news_read_button.setEnabled(False)
        self.cancel_button.setEnabled(False)
        self.mark_all_news_read_requested.emit()

    def enable_news_actions(self) -> None:
        if not self._news_actions_started:
            self.read_news_button.setEnabled(True)
            self.mark_all_news_read_button.setEnabled(True)

    def finish_news_action(self) -> None:
        self._news_action_running = False
        self.cancel_button.setEnabled(True)

    def append_output(self, text: str, *, final: bool = False) -> None:
        self.log.feed_text(text, final=final)

    def append_output_bytes(self, data: bytes, *, final: bool = False) -> None:
        self.log.feed_bytes(data, final=final)

    def complete(self, success: bool) -> None:
        self._update_finished = True
        self.cancel_button.setText(_("Close"))
        self.cancel_button.setEnabled(True)
        self.cancel_button.clicked.disconnect()
        self.cancel_button.clicked.connect(self.accept)
        self.setWindowTitle(
            _("Repository update complete" if success else "Repository update failed")
        )
        self.enable_news_actions()

    def reject(self) -> None:  # noqa: D401
        if self._news_action_running:
            return
        if not self._update_finished:
            self.cancel_requested.emit()
            return
        super().reject()


class RepoSourceDialog(QDialog):
    """Edit repository fields supported by ruyi's repository implementation."""

    def __init__(
        self,
        title: str,
        *,
        name: str = "",
        remote: str = "",
        local: str = "",
        branch: str = "",
        priority: int = 10,
        source_options: tuple[repo_manager.RepoSource, ...] = (),
        name_enabled: bool = True,
        source_enabled: bool = True,
        priority_enabled: bool = True,
        allow_empty_source: bool = False,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle(_(title))
        self.resize(560, 300)
        layout = QVBoxLayout(self)
        form = QFormLayout()
        self._allow_empty_source = allow_empty_source
        self._custom_source_enabled = source_enabled
        self._custom_remote = remote
        self._custom_branch = branch
        self._source_index = -1
        self.name_edit = QLineEdit(name)
        self.remote_edit = QLineEdit(remote)
        self.local_edit = QLineEdit(local)
        self.branch_edit = QLineEdit(branch)
        self.priority_edit = QLineEdit(str(priority))
        self.priority_edit.setPlaceholderText(_("Integer"))
        self.name_edit.setEnabled(name_enabled)
        self.local_edit.setEnabled(False)
        self.priority_edit.setEnabled(priority_enabled)
        form.addRow(_("Name"), self.name_edit)
        self.source_combo = QComboBox()
        initial_source = repo_manager.RepoSource(
            remote or None,
            local or None,
            branch or None,
        )
        selected_index: int | None = None
        for index, option in enumerate(source_options):
            label = repo_manager.source_label(option)
            if option.branch:
                label += f" [{option.branch}]"
            self.source_combo.addItem(
                label or _("Preset {number}", number=index + 1),
                option,
            )
            if repo_manager.source_matches_preset(initial_source, option):
                selected_index = index
        custom_index = self.source_combo.count()
        self.source_combo.addItem(_("Custom"), None)
        self.source_combo.currentIndexChanged.connect(self._select_source_option)
        self.source_combo.setCurrentIndex(
            custom_index if selected_index is None else selected_index
        )
        self._select_source_option(self.source_combo.currentIndex())
        form.addRow(_("Source preset"), self.source_combo)
        form.addRow(_("Remote URL"), self.remote_edit)
        form.addRow(_("Local path"), self.local_edit)
        form.addRow(_("Branch"), self.branch_edit)
        form.addRow(_("Priority"), self.priority_edit)
        layout.addLayout(form)
        self.help_label = QLabel(
            _(
                "Use a remote URL, an absolute local path, or both. Repository ID and "
                "name come from the preset list for additional repositories."
            )
        )
        self.help_label.setWordWrap(True)
        layout.addWidget(self.help_label)
        buttons = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)
        translate_widget_tree(self)

    def _select_source_option(self, index: int) -> None:
        if (
            self._source_index >= 0
            and self.source_combo.itemData(self._source_index) is None
        ):
            self._custom_remote = self.remote_edit.text()
            self._custom_branch = self.branch_edit.text()
        option = self.source_combo.itemData(index)
        is_preset = isinstance(option, repo_manager.RepoSource)
        if is_preset:
            self.remote_edit.setText(option.remote or "")
            self.branch_edit.setText(option.branch or "")
        else:
            self.remote_edit.setText(self._custom_remote)
            self.branch_edit.setText(self._custom_branch)
        self.remote_edit.setEnabled(self._custom_source_enabled and not is_preset)
        self.branch_edit.setEnabled(self._custom_source_enabled and not is_preset)
        self._source_index = index

    def values(self) -> tuple[repo_manager.RepoSource, int | None, str]:
        try:
            priority = int(self.priority_edit.text().strip())
        except ValueError:
            priority = None
        return (
            repo_manager.RepoSource(
                self.remote_edit.text().strip() or None,
                self.local_edit.text().strip() or None,
                self.branch_edit.text().strip() or None,
            ),
            priority,
            self.name_edit.text().strip(),
        )

    def accept(self) -> None:  # noqa: D401
        source, priority, _name = self.values()
        if priority is None:
            QMessageBox.warning(
                self,
                _("Invalid priority"),
                _("Priority must be an integer."),
            )
            return
        if (
            source.remote is None
            and source.local is None
            and not self._allow_empty_source
        ):
            QMessageBox.warning(
                self,
                _("Missing source"),
                _("Enter a remote URL or local path."),
            )
            return
        if source.local is not None and not Path(source.local).is_absolute():
            QMessageBox.warning(
                self,
                _("Invalid local path"),
                _("Local path must be absolute."),
            )
            return
        super().accept()


__all__ = ["RepoSourceDialog", "RepoUpdateDialog"]
