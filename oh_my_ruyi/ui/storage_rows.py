"""Build one storage-target row for the provisioning storage page."""

from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass
from typing import Protocol

from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStyle,
    QVBoxLayout,
    QWidget,
)

from ..i18n import _


class DiskChoice(Protocol):
    display_name: str
    path: str
    mounted: bool
    fingerprint: str | None


Callback = Callable[..., object]


@dataclass(slots=True)
class StorageRowWidgets:
    wrapper: QWidget
    edit: QComboBox
    warning: QLabel
    confirmation: QCheckBox


def build_storage_row(
    *,
    part: str,
    description: str,
    disks: Iterable[DiskChoice],
    style: QStyle,
    mounted_role: int,
    fingerprint_role: int,
    refresh_buttons: Callback,
    on_target_changed: Callback,
    browse_storage: Callback,
) -> StorageRowWidgets:
    """Create a target selector and its mounted-device confirmation controls."""

    label = QLabel(f"{description} ({part})")
    edit = QComboBox()
    edit.setEditable(True)
    edit.setAccessibleName(_("Target disk for {description}", description=description))
    label.setBuddy(edit)
    edit.lineEdit().setPlaceholderText("/dev/...")
    for disk in disks:
        edit.addItem(disk.display_name, disk.path)
        index = edit.count() - 1
        edit.setItemData(index, disk.mounted, mounted_role)
        edit.setItemData(index, disk.fingerprint, fingerprint_role)

    warning = QLabel(_("The selected disk or one of its partitions is mounted."))
    warning.setProperty("statusKind", "error")
    warning.setVisible(False)
    confirmation = QCheckBox(_("I understand flashing may overwrite mounted data."))
    confirmation.setVisible(False)
    confirmation.toggled.connect(refresh_buttons)
    edit.currentTextChanged.connect(
        lambda _text, e=edit, w=warning, c=confirmation: on_target_changed(e, w, c)
    )

    browse = QPushButton()
    browse.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DialogOpenButton))
    browse_text = _(
        "Choose target disk or image file for {description}",
        description=description,
    )
    browse.setToolTip(browse_text)
    browse.setAccessibleName(browse_text)
    browse.clicked.connect(lambda _=False, e=edit: browse_storage(e))

    row = QHBoxLayout()
    row.addWidget(label, 2)
    row.addWidget(edit, 3)
    row.addWidget(browse)
    wrapper = QWidget()
    wrapper_layout = QVBoxLayout(wrapper)
    wrapper_layout.setContentsMargins(0, 0, 0, 0)
    wrapper_layout.addLayout(row)
    wrapper_layout.addWidget(warning)
    wrapper_layout.addWidget(confirmation)
    return StorageRowWidgets(wrapper, edit, warning, confirmation)


__all__ = ["StorageRowWidgets", "build_storage_row"]
