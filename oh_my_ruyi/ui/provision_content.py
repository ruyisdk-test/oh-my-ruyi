"""Reusable content renderers for provisioning selection pages."""

from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QVBoxLayout,
    QWidget,
)

from ..i18n import _


class Choice(Protocol):
    id: str
    display_name: str


class VersionOption(Protocol):
    display_name: str
    atom: str


class VersionSelection(Protocol):
    package_name: str
    options: tuple[VersionOption, ...]
    locked_reason: str | None


def populate_choice_list(
    list_widget: QListWidget,
    choices: Iterable[Choice],
) -> dict[str, Choice]:
    """Render id/display-name entities and return the lookup used on selection."""

    choice_items = list(choices)
    choice_by_id = {choice.id: choice for choice in choice_items}
    list_widget.clear()
    for choice in choice_items:
        item = QListWidgetItem(choice.display_name)
        item.setData(Qt.ItemDataRole.UserRole, choice.id)
        list_widget.addItem(item)
    return choice_by_id


def clear_layout_widgets(layout: QVBoxLayout) -> None:
    """Remove and schedule deletion of widgets in a dynamic vertical layout."""

    while layout.count():
        item = layout.takeAt(0)
        widget = item.widget()
        if widget is not None:
            widget.deleteLater()


def build_version_selection_rows(
    layout: QVBoxLayout,
    selections: Iterable[VersionSelection],
) -> list[QComboBox]:
    """Render package version controls and return their combo boxes in order."""

    combos: list[QComboBox] = []
    for selection in selections:
        label = QLabel(selection.package_name)
        combo = QComboBox()
        combo.setAccessibleName(
            _("Version for {package}", package=selection.package_name)
        )
        label.setBuddy(combo)
        for option in selection.options:
            combo.addItem(option.display_name, option.atom)
        combo.setEnabled(selection.locked_reason is None and len(selection.options) > 1)
        if selection.locked_reason:
            label.setText(
                _(
                    "{package} ({reason})",
                    package=selection.package_name,
                    reason=selection.locked_reason,
                )
            )
        row = QHBoxLayout()
        row.addWidget(label, 2)
        row.addWidget(combo, 3)
        wrapper = QWidget()
        wrapper.setLayout(row)
        layout.addWidget(wrapper)
        combos.append(combo)
    layout.addStretch()
    return combos


def populate_package_list(
    list_widget: QListWidget, package_atoms: Iterable[str]
) -> None:
    """Render package atoms or the post-install-only placeholder."""

    atoms = list(package_atoms)
    list_widget.clear()
    if atoms:
        for atom in atoms:
            list_widget.addItem(atom)
    else:
        list_widget.addItem(
            _("No packages. The selected image only contains a post-install message.")
        )


__all__ = [
    "build_version_selection_rows",
    "clear_layout_widgets",
    "populate_choice_list",
    "populate_package_list",
]
