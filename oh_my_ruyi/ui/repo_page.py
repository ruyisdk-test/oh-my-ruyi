"""Build the repository-management panels."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .common import configure_table


Callback = Callable[..., object]


@dataclass(slots=True)
class PresetPanelWidgets:
    panel: QWidget
    table: QTableWidget
    add_button: QPushButton


@dataclass(slots=True)
class ConfiguredPanelWidgets:
    panel: QWidget
    table: QTableWidget
    refresh_button: QPushButton
    edit_button: QPushButton
    remove_button: QPushButton
    toggle_button: QPushButton
    update_button: QPushButton


def build_preset_panel(
    *,
    refresh_buttons: Callback,
    add_selected: Callback,
) -> PresetPanelWidgets:
    """Construct the preset repository panel and its intent signals."""

    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 6, 0)
    layout.addWidget(QLabel("<b>Preset repositories</b>"))
    content = QHBoxLayout()
    table = QTableWidget(0, 2)
    configure_table(table, ["ID", "Name"], stretch_column=1)
    table.setAccessibleName("Preset repositories")
    table.itemSelectionChanged.connect(refresh_buttons)
    content.addWidget(table, 1)
    buttons = QVBoxLayout()
    buttons.addStretch()
    add_button = QPushButton("Add")
    add_button.clicked.connect(add_selected)
    buttons.addWidget(add_button)
    buttons.addStretch()
    content.addLayout(buttons)
    layout.addLayout(content, 1)
    return PresetPanelWidgets(panel, table, add_button)


def build_configured_panel(
    *,
    refresh_buttons: Callback,
    reload: Callback,
    edit_selected: Callback,
    remove_selected: Callback,
    toggle_selected: Callback,
    update_selected: Callback,
) -> ConfiguredPanelWidgets:
    """Construct the configured repository panel and its intent signals."""

    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(6, 0, 0, 0)
    layout.addWidget(QLabel("<b>Configured repositories</b>"))
    content = QHBoxLayout()
    table = QTableWidget(0, 6)
    configure_table(
        table,
        ["ID", "Name", "Source", "Branch", "Priority", "State"],
        stretch_column=2,
    )
    table.setAccessibleName("Configured repositories")
    table.itemSelectionChanged.connect(refresh_buttons)
    content.addWidget(table, 1)
    buttons = QVBoxLayout()
    buttons.addStretch()
    refresh_button = QPushButton("Refresh")
    edit_button = QPushButton("Edit")
    remove_button = QPushButton("Remove")
    toggle_button = QPushButton("Enable")
    update_button = QPushButton("Update")
    refresh_button.clicked.connect(reload)
    edit_button.clicked.connect(edit_selected)
    remove_button.clicked.connect(remove_selected)
    toggle_button.clicked.connect(toggle_selected)
    update_button.clicked.connect(update_selected)
    for button in (
        refresh_button,
        edit_button,
        remove_button,
        toggle_button,
        update_button,
    ):
        buttons.addWidget(button)
    buttons.addStretch()
    content.addLayout(buttons)
    layout.addLayout(content, 1)
    return ConfiguredPanelWidgets(
        panel,
        table,
        refresh_button,
        edit_button,
        remove_button,
        toggle_button,
        update_button,
    )


__all__ = [
    "ConfiguredPanelWidgets",
    "PresetPanelWidgets",
    "build_configured_panel",
    "build_preset_panel",
]
