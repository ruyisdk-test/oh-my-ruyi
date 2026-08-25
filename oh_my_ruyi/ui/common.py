"""Small presentation helpers shared by top-level Qt views."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QAbstractItemView,
    QHeaderView,
    QTableWidget,
    QTableWidgetItem,
)

from .. import version_manager
from ..i18n import _

FASTBOOT_PROGRAM = "fastboot"
STORAGE_MOUNTED_ROLE = Qt.ItemDataRole.UserRole.value + 1
STORAGE_FINGERPRINT_ROLE = Qt.ItemDataRole.UserRole.value + 2


def message_box(method, parent, title: str, message: str, *args):
    """Translate the title and message before invoking a QMessageBox method."""
    return method(parent, _(title), _(message), *args)


class VersionTableItem(QTableWidgetItem):
    """Sort version cells by semantic version components instead of text."""

    def __init__(self, version: str) -> None:
        super().__init__(version)
        self._sort_key = version_manager.version_sort_key(version)

    def __lt__(self, other: QTableWidgetItem) -> bool:
        if isinstance(other, VersionTableItem):
            return self._sort_key < other._sort_key
        return super().__lt__(other)


def configure_table(
    table: QTableWidget,
    headers: list[str],
    *,
    stretch_column: int,
    sorting: bool = False,
) -> None:
    """Apply the application's consistent table selection and header policy."""
    table.setHorizontalHeaderLabels(headers)
    table.setSelectionBehavior(QAbstractItemView.SelectionBehavior.SelectRows)
    table.setSelectionMode(QAbstractItemView.SelectionMode.SingleSelection)
    table.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
    table.setAlternatingRowColors(True)
    table.setSortingEnabled(sorting)
    table.verticalHeader().setVisible(False)
    table.horizontalHeader().setSectionResizeMode(
        QHeaderView.ResizeMode.ResizeToContents
    )
    table.horizontalHeader().setSectionResizeMode(
        stretch_column,
        QHeaderView.ResizeMode.Stretch,
    )


__all__ = [
    "FASTBOOT_PROGRAM",
    "STORAGE_FINGERPRINT_ROLE",
    "STORAGE_MOUNTED_ROLE",
    "VersionTableItem",
    "configure_table",
    "message_box",
]
