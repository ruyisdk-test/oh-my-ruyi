"""Table population helpers for the package-manager version view."""

from __future__ import annotations

from collections.abc import Callable, Iterable

from PySide6.QtCore import Qt
from PySide6.QtGui import QBrush
from PySide6.QtWidgets import QTableWidget, QTableWidgetItem

from .. import version_manager
from ..core.formatting import format_bytes
from ..i18n import _
from .common import VersionTableItem


def set_row_foreground(table: QTableWidget, row: int, foreground: QBrush) -> None:
    """Apply one foreground brush to every populated cell in a table row."""
    for column in range(table.columnCount()):
        item = table.item(row, column)
        if item is not None:
            item.setForeground(foreground)


def populate_available_versions_table(
    table: QTableWidget,
    releases: Iterable[version_manager.RuyiRelease],
    selected_url: str | None,
    *,
    highlight_release: version_manager.RuyiRelease | None = None,
    highlight_foreground: QBrush | None = None,
) -> None:
    """Render release metadata while preserving a selected download URL."""
    release_items = list(releases)
    table.blockSignals(True)
    table.setSortingEnabled(False)
    table.setRowCount(len(release_items))
    for row, release in enumerate(release_items):
        version_item = VersionTableItem(release.version)
        version_item.setData(Qt.ItemDataRole.UserRole, release)
        table.setItem(row, 0, version_item)
        table.setItem(row, 1, QTableWidgetItem(_(release.channel)))
        architecture = (
            version_manager.normalize_architecture(release.architecture)
            or release.architecture
        )
        table.setItem(row, 2, QTableWidgetItem(architecture))
        table.setItem(row, 3, QTableWidgetItem(release.release_date[:10]))
        if release is highlight_release and highlight_foreground is not None:
            set_row_foreground(table, row, highlight_foreground)
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    table.clearSelection()
    if selected_url is not None:
        for row in range(table.rowCount()):
            item = table.item(row, 0)
            release = item.data(Qt.ItemDataRole.UserRole)
            if (
                isinstance(release, version_manager.RuyiRelease)
                and release.download_urls[0] == selected_url
            ):
                table.selectRow(row)
                break
    table.blockSignals(False)


def populate_installed_versions_table(
    table: QTableWidget,
    installed: Iterable[version_manager.InstalledVersion],
    active: version_manager.ActivationState,
    selected_version: str | None,
    catalog_releases: Iterable[version_manager.RuyiRelease],
    *,
    latest_version: str | None = None,
    latest_channel: str | None = None,
    active_is_latest: bool | None = None,
    outdated_foreground: QBrush | None = None,
    latest_foreground: QBrush | None = None,
    size_formatter: Callable[[int], str] = format_bytes,
) -> None:
    """Render local binaries, activation state, and catalog freshness notes."""
    installed_items = list(installed)
    latest_versions = {release.version for release in catalog_releases}
    table.blockSignals(True)
    table.setSortingEnabled(False)
    table.setRowCount(len(installed_items))
    for row, item in enumerate(installed_items):
        version_item = VersionTableItem(item.version)
        version_item.setData(Qt.ItemDataRole.UserRole, item)
        table.setItem(row, 0, version_item)
        is_active = active.managed and active.target == item.path.resolve(strict=False)
        is_latest = (
            latest_version is not None
            and latest_channel is not None
            and item.channel.casefold() == latest_channel.casefold()
            and version_manager.version_sort_key(item.version)
            == version_manager.version_sort_key(latest_version)
        )
        table.setItem(row, 1, QTableWidgetItem(_(item.channel)))
        activate_item = QTableWidgetItem(_("Activate") if is_active else "")
        if is_active and active_is_latest is False and outdated_foreground is not None:
            activate_item.setForeground(outdated_foreground)
        table.setItem(row, 2, activate_item)
        table.setItem(row, 3, QTableWidgetItem(size_formatter(item.size)))
        table.setItem(
            row,
            4,
            QTableWidgetItem(_("Latest") if item.version in latest_versions else ""),
        )
        if is_latest and not is_active and latest_foreground is not None:
            set_row_foreground(table, row, latest_foreground)
    table.setSortingEnabled(True)
    table.sortItems(0, Qt.SortOrder.DescendingOrder)
    table.clearSelection()
    if selected_version is not None:
        for row in range(table.rowCount()):
            item = table.item(row, 0).data(Qt.ItemDataRole.UserRole)
            if (
                isinstance(item, version_manager.InstalledVersion)
                and item.version == selected_version
            ):
                table.selectRow(row)
                break
    table.blockSignals(False)


__all__ = [
    "populate_available_versions_table",
    "populate_installed_versions_table",
    "set_row_foreground",
]
