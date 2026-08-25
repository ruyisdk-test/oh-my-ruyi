"""Small presentation helpers shared by top-level Qt views."""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QTableWidgetItem

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


__all__ = [
    "FASTBOOT_PROGRAM",
    "STORAGE_FINGERPRINT_ROLE",
    "STORAGE_MOUNTED_ROLE",
    "VersionTableItem",
    "message_box",
]
