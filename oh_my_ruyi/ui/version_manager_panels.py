"""Build the standalone ruyi version-management page."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QFrame,
    QLabel,
    QPushButton,
    QSplitter,
    QStyle,
    QTableWidget,
    QVBoxLayout,
    QWidget,
)

from .common import configure_table


Callback = Callable[..., object]


@dataclass(slots=True)
class VersionManagerPanelWidgets:
    """Controls updated by the version-management coordinator."""

    tab: QWidget
    splitter: QSplitter
    available_table: QTableWidget
    refresh_btn: QPushButton
    download_btn: QPushButton
    remove_url_btn: QPushButton
    add_url_btn: QPushButton
    status: QLabel
    installed_table: QTableWidget
    local_refresh_btn: QPushButton
    delete_btn: QPushButton
    toggle_activation_btn: QPushButton
    browse_btn: QPushButton
    path_status: QLabel


def _make_status_label(text: str = "") -> QLabel:
    label = QLabel(text)
    label.setObjectName("versionStatus")
    label.setFrameShape(QFrame.Shape.NoFrame)
    label.setWordWrap(True)
    label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
    return label


def _build_available_panel(
    *,
    style: QStyle,
    refresh_pm_buttons: Callback,
    refresh_pm_catalog: Callback,
    download_selected: Callback,
    remove_selected_url: Callback,
    add_url: Callback,
) -> tuple[QWidget, dict[str, object]]:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(0, 0, 6, 0)
    layout.addWidget(QLabel("<b>Available downloads</b>"))

    content = QHBoxLayout()
    available_table = QTableWidget(0, 4)
    configure_table(
        available_table,
        ["Version", "Channel", "Architecture", "Released"],
        stretch_column=0,
        sorting=True,
    )
    available_table.setObjectName("availableVersionTable")
    available_table.setAccessibleName("Available ruyi versions")
    available_table.itemSelectionChanged.connect(refresh_pm_buttons)
    content.addWidget(available_table, 1)

    buttons = QVBoxLayout()
    buttons.addStretch()
    refresh_btn = QPushButton("Refresh")
    download_btn = QPushButton("Download")
    remove_url_btn = QPushButton("Remove")
    add_url_btn = QPushButton("Add URL")
    refresh_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload))
    refresh_btn.clicked.connect(refresh_pm_catalog)
    download_btn.clicked.connect(download_selected)
    remove_url_btn.clicked.connect(remove_selected_url)
    add_url_btn.clicked.connect(add_url)
    for button in (refresh_btn, download_btn, remove_url_btn, add_url_btn):
        buttons.addWidget(button)
    buttons.addStretch()
    content.addLayout(buttons)
    layout.addLayout(content, 1)

    status = _make_status_label("Showing versions already downloaded on this computer.")
    layout.addWidget(status)
    return panel, {
        "available_table": available_table,
        "refresh_btn": refresh_btn,
        "download_btn": download_btn,
        "remove_url_btn": remove_url_btn,
        "add_url_btn": add_url_btn,
        "status": status,
    }


def _build_installed_panel(
    *,
    style: QStyle,
    refresh_pm_buttons: Callback,
    refresh_local_versions: Callback,
    delete_selected: Callback,
    toggle_activation: Callback,
    browse_selected: Callback,
) -> tuple[QWidget, dict[str, object]]:
    panel = QWidget()
    layout = QVBoxLayout(panel)
    layout.setContentsMargins(6, 0, 0, 0)
    layout.addWidget(QLabel("<b>Downloaded versions</b>"))

    content = QHBoxLayout()
    installed_table = QTableWidget(0, 5)
    configure_table(
        installed_table,
        ["Version", "Channel", "State", "Size", "Note"],
        stretch_column=0,
        sorting=True,
    )
    installed_table.setObjectName("installedVersionTable")
    installed_table.setAccessibleName("Downloaded ruyi versions")
    installed_table.itemSelectionChanged.connect(refresh_pm_buttons)
    content.addWidget(installed_table, 1)

    buttons = QVBoxLayout()
    buttons.addStretch()
    local_refresh_btn = QPushButton("Refresh")
    delete_btn = QPushButton("Delete")
    toggle_activation_btn = QPushButton("Activate")
    browse_btn = QPushButton("Browse")
    local_refresh_btn.setIcon(
        style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
    )
    local_refresh_btn.setToolTip("Rescan downloaded ruyi binaries from the file system")
    browse_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_DirOpenIcon))
    browse_btn.setToolTip("Open the folder containing the selected downloaded binary")
    local_refresh_btn.clicked.connect(refresh_local_versions)
    delete_btn.clicked.connect(delete_selected)
    toggle_activation_btn.clicked.connect(toggle_activation)
    browse_btn.clicked.connect(browse_selected)
    for button in (local_refresh_btn, delete_btn, toggle_activation_btn, browse_btn):
        buttons.addWidget(button)
    buttons.addStretch()
    content.addLayout(buttons)
    layout.addLayout(content, 1)

    path_status = _make_status_label()
    layout.addWidget(path_status)
    return panel, {
        "installed_table": installed_table,
        "local_refresh_btn": local_refresh_btn,
        "delete_btn": delete_btn,
        "toggle_activation_btn": toggle_activation_btn,
        "browse_btn": browse_btn,
        "path_status": path_status,
    }


def build_version_manager_tab(
    *,
    style: QStyle,
    refresh_pm_buttons: Callback,
    refresh_pm_catalog: Callback,
    download_selected: Callback,
    remove_selected_url: Callback,
    add_url: Callback,
    refresh_local_versions: Callback,
    delete_selected: Callback,
    toggle_activation: Callback,
    browse_selected: Callback,
    align_status_heights: Callback,
) -> VersionManagerPanelWidgets:
    """Construct the version page and return its coordinator-owned controls."""

    tab = QWidget()
    layout = QVBoxLayout(tab)
    layout.setContentsMargins(16, 16, 16, 16)
    layout.setSpacing(10)

    title = QLabel("<b>Ruyi Package Manager Versions</b>")
    title.setObjectName("pageTitle")
    layout.addWidget(title)
    description = QLabel(
        "Download standalone ruyi releases into your home directory and choose "
        "which version /usr/local/bin/ruyi activates."
    )
    description.setWordWrap(True)
    layout.addWidget(description)

    splitter = QSplitter(Qt.Orientation.Horizontal)
    splitter.setChildrenCollapsible(False)
    available_panel, available = _build_available_panel(
        style=style,
        refresh_pm_buttons=refresh_pm_buttons,
        refresh_pm_catalog=refresh_pm_catalog,
        download_selected=download_selected,
        remove_selected_url=remove_selected_url,
        add_url=add_url,
    )
    installed_panel, installed = _build_installed_panel(
        style=style,
        refresh_pm_buttons=refresh_pm_buttons,
        refresh_local_versions=refresh_local_versions,
        delete_selected=delete_selected,
        toggle_activation=toggle_activation,
        browse_selected=browse_selected,
    )
    splitter.addWidget(available_panel)
    splitter.addWidget(installed_panel)
    splitter.setStretchFactor(0, 1)
    splitter.setStretchFactor(1, 1)
    splitter.splitterMoved.connect(align_status_heights)
    layout.addWidget(splitter, 1)

    return VersionManagerPanelWidgets(
        tab=tab,
        splitter=splitter,
        **available,
        **installed,
    )


__all__ = ["VersionManagerPanelWidgets", "build_version_manager_tab"]
