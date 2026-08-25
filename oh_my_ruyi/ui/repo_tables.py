"""Repository table rendering for the repository management tab."""

from __future__ import annotations

from collections.abc import Iterable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from .. import repo_manager
from ..i18n import _


def populate_repository_tables(
    preset_table: QTableWidget,
    configured_table: QTableWidget,
    presets: Iterable[repo_manager.RepoPreset],
    repositories: Iterable[repo_manager.ConfiguredRepo],
    *,
    data_role: Qt.ItemDataRole,
) -> None:
    """Render repository presets and configured entries in display order."""
    configured_items = tuple(repositories)
    configured_ids = {repo.id for repo in configured_items}
    preset_table.setRowCount(0)
    for preset in presets:
        row = preset_table.rowCount()
        preset_table.insertRow(row)
        for column, value in enumerate((preset.id, preset.name)):
            item = QTableWidgetItem(value)
            if column == 0:
                item.setData(data_role, preset)
            tooltip = value
            if preset.id in configured_ids:
                tooltip += "\n" + _("Already present in the local configuration.")
            item.setToolTip(tooltip)
            preset_table.setItem(row, column, item)

    configured_table.setRowCount(0)
    for repo in configured_items:
        row = configured_table.rowCount()
        configured_table.insertRow(row)
        values = (
            repo.id,
            repo.name,
            repo_manager.source_label(repo),
            repo.branch or "",
            str(repo.priority),
            _("Active" if repo.active else "Disabled"),
        )
        for column, value in enumerate(values):
            item = QTableWidgetItem(value)
            item.setToolTip(value)
            if column == 0:
                item.setData(data_role, repo)
            configured_table.setItem(row, column, item)
        if repo.is_default:
            for column in range(configured_table.columnCount()):
                configured_table.item(row, column).setToolTip(
                    _(
                        "{value}\nThe default ruyisdk repository cannot be removed.",
                        value=values[column],
                    )
                )


__all__ = ["populate_repository_tables"]
