"""Shared helpers and constants for the main-window views."""

from __future__ import annotations

from PySide6.QtCore import Qt

from ...i18n import _


FASTBOOT_PROGRAM = "fastboot"
STORAGE_MOUNTED_ROLE = Qt.ItemDataRole.UserRole.value + 1
STORAGE_FINGERPRINT_ROLE = Qt.ItemDataRole.UserRole.value + 2


def _message_box(method, parent, title: str, message: str, *args):
    return method(parent, _(title), _(message), *args)
