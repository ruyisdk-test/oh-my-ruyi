"""Version management tab UI."""

from __future__ import annotations

import os
import platform
import shutil
import threading
import time
import pytest
from PySide6.QtCore import QProcess, Qt
from PySide6.QtWidgets import QApplication, QInputDialog
from ruyi.config import GlobalConfig
from ruyi.utils.global_mode import EnvGlobalModeProvider
from oh_my_ruyi.infra import version_manager
from oh_my_ruyi.ui.views import main_window
from oh_my_ruyi.ui.views.main_window import ProvisionMainWindow
from oh_my_ruyi.ui.views.version_dialogs import (
    VersionDownloadDialog as _VersionDownloadDialog,
)
from oh_my_ruyi.ui.widgets.qt_logger import LogEmitter, QtRuyiLogger
from tests._helpers import (
    _binary_header_for_arch,
    _host_binary_header,
    _host_download_url,
)


def test_version_tables_separate_available_and_downloaded_versions(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.write_bytes(_host_binary_header())
    binary.chmod(0o755)
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(binary)
    monkeypatch.setenv("PATH", os.fspath(window._pm_activation_link.parent))
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.52.0-alpha.20260714",
            "testing",
            "2026-07-14T10:54:29Z",
            ("https://example.test/ruyi",),
            "x86_64",
        ),
        version_manager.RuyiRelease(
            "0.50.0",
            "stable",
            "2026-06-23T13:06:10Z",
            ("https://example.test/stable-ruyi",),
            "x86_64",
        ),
    ]

    window._refresh_pm_versions(select_installed_version="0.50.0")

    assert window._pm_available_table.columnCount() == 4
    assert window._pm_available_table.rowCount() == 2
    assert window._pm_available_table.item(0, 0).text() == "0.52.0-alpha.20260714"
    assert window._pm_available_table.item(1, 1).text() == "stable"
    assert window._pm_installed_table.columnCount() == 5
    assert window._pm_installed_table.rowCount() == 1
    assert window._pm_installed_table.item(0, 0).text() == "0.50.0"
    assert window._pm_installed_table.item(0, 1).text() == "stable"
    assert window._pm_installed_table.item(0, 2).text() == "Activate"
    assert window._pm_installed_table.item(0, 3).text() == "64 B"
    assert window._pm_installed_table.item(0, 4).text() == "Latest"
    assert window._pm_toggle_activation_btn.isEnabled()
    assert not window._pm_delete_btn.isEnabled()
    assert window._pm_toggle_activation_btn.text() == "Deactivate"
    assert "PATH ready" in window._pm_path_status.text()


@pytest.mark.parametrize(
    ("active_version", "api_channel", "api_latest", "api_older"),
    [
        ("0.50.0", "stable", "0.51.0", "0.50.0"),
        ("0.51.0-alpha.1", "testing", "0.52.0-alpha.1", "0.51.0-alpha.1"),
    ],
)
def test_active_version_color_compares_with_matching_api_channel(
    window: ProvisionMainWindow,
    monkeypatch,
    active_version: str,
    api_channel: str,
    api_latest: str,
    api_older: str,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    active = window._pm_versions_directory / f"ruyi-{active_version}"
    active.write_bytes(_host_binary_header())
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(active)
    monkeypatch.setenv("PATH", os.fspath(window._pm_activation_link.parent))
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            api_latest,
            api_channel,
            "2026-07-14T10:54:29Z",
            (f"https://api.example/ruyi-{api_latest}.amd64",),
            "x86_64",
        ),
        version_manager.RuyiRelease(
            api_older,
            api_channel,
            "2026-06-23T13:06:10Z",
            (f"https://api.example/ruyi-{api_older}.amd64",),
            "x86_64",
        ),
    ]

    window._refresh_pm_versions(select_installed_version=active_version)

    colors = window._theme_colors()
    row = window._pm_installed_table.currentRow()
    assert row >= 0
    activate_item = window._pm_installed_table.item(row, 2)
    assert activate_item.text() == "Activate"
    assert activate_item.foreground().color().name() == colors["error"]
    latest_row = next(
        row
        for row in range(window._pm_available_table.rowCount())
        if window._pm_available_table.item(row, 0).text() == api_latest
    )
    assert all(
        window._pm_available_table.item(latest_row, column).foreground().color().name()
        == colors["success"]
        for column in range(window._pm_available_table.columnCount())
    )


def test_active_latest_version_row_uses_default_foreground(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    latest = window._pm_versions_directory / "ruyi-0.51.0"
    latest.write_bytes(_host_binary_header())
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(latest)
    monkeypatch.setenv("PATH", os.fspath(window._pm_activation_link.parent))
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.51.0",
            "stable",
            "2026-07-14T10:54:29Z",
            ("https://api.example/ruyi-0.51.0.amd64",),
            "x86_64",
        )
    ]

    window._refresh_pm_versions(select_installed_version="0.51.0")

    row = window._pm_installed_table.currentRow()
    assert row >= 0
    assert all(
        window._pm_installed_table.item(row, column).foreground().style()
        == Qt.BrushStyle.NoBrush
        for column in range(window._pm_installed_table.columnCount())
    )


def test_latest_downloaded_version_is_green_only_in_right_table(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    active = window._pm_versions_directory / "ruyi-0.50.0"
    latest = window._pm_versions_directory / "ruyi-0.51.0"
    active.write_bytes(_host_binary_header())
    latest.write_bytes(_host_binary_header())
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(active)
    monkeypatch.setenv("PATH", os.fspath(window._pm_activation_link.parent))
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.51.0",
            "stable",
            "2026-07-14T10:54:29Z",
            ("https://api.example/ruyi-0.51.0.amd64",),
            "x86_64",
        )
    ]

    window._refresh_pm_versions(select_installed_version="0.50.0")

    colors = window._theme_colors()
    left_row = next(
        row
        for row in range(window._pm_available_table.rowCount())
        if window._pm_available_table.item(row, 0).text() == "0.51.0"
    )
    right_row = next(
        row
        for row in range(window._pm_installed_table.rowCount())
        if window._pm_installed_table.item(row, 0).text() == "0.51.0"
    )
    assert (
        window._pm_available_table.item(left_row, 0).foreground().color().name()
        != colors["success"]
    )
    assert all(
        window._pm_installed_table.item(right_row, column).foreground().color().name()
        == colors["success"]
        for column in range(window._pm_installed_table.columnCount())
    )


def test_external_system_management_keeps_tables_visible_but_disables_controls(
    qtbot,
    tmp_path,
) -> None:
    _app = QApplication.instance() or QApplication([])
    gm = EnvGlobalModeProvider({}, [])
    emitter = LogEmitter()
    logger = QtRuyiLogger(gm, emitter)
    config = GlobalConfig(gm, logger)
    system_config = tmp_path / "config.toml"
    system_config.write_text("[installation]\nexternally_managed = true\n")
    versions = tmp_path / "versions"
    versions.mkdir()
    (versions / "ruyi-0.50.0").write_bytes(_host_binary_header())
    telemetry_installation = tmp_path / "state" / "installation.json"
    telemetry_installation.parent.mkdir()
    telemetry_installation.write_text("{}")
    window = ProvisionMainWindow(
        config,
        logger,
        emitter,
        auto_start=False,
        versions_directory=versions,
        activation_link=tmp_path / "bin" / "ruyi",
        telemetry_installation=telemetry_installation,
        system_ruyi_config=system_config,
        repo_config_path=tmp_path / "config" / "ruyi" / "config.toml",
    )
    qtbot.addWidget(window)
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.50.0",
            "stable",
            "2026-06-23T13:06:10Z",
            ("https://example.test/ruyi",),
            "x86_64",
        )
    ]

    window._refresh_pm_versions()

    assert window._pm_available_table.rowCount() == 1
    assert window._pm_installed_table.rowCount() == 1
    assert not window._pm_available_table.isEnabled()
    assert not window._pm_installed_table.isEnabled()
    assert not window._pm_refresh_btn.isEnabled()
    assert not window._pm_download_btn.isEnabled()
    assert not window._pm_remove_url_btn.isEnabled()
    assert not window._pm_add_url_btn.isEnabled()
    assert not window._pm_local_refresh_btn.isEnabled()
    assert not window._pm_delete_btn.isEnabled()
    assert not window._pm_toggle_activation_btn.isEnabled()
    assert not window._pm_browse_btn.isEnabled()
    assert (
        window._pm_path_status.text()
        == "Version management issue: this system's ruyi package manager is "
        "configured to have its version managed by the system package manager."
    )
    assert window._pm_path_status.property("statusKind") == "error"


def test_loaded_ruyi_config_keeps_external_management_locked(
    qtbot,
    tmp_path,
) -> None:
    _app = QApplication.instance() or QApplication([])
    gm = EnvGlobalModeProvider({}, [])
    emitter = LogEmitter()
    logger = QtRuyiLogger(gm, emitter)
    config = GlobalConfig(gm, logger)
    config.is_installation_externally_managed = True
    system_config = tmp_path / "removed-config.toml"
    window = ProvisionMainWindow(
        config,
        logger,
        emitter,
        auto_start=False,
        versions_directory=tmp_path / "versions",
        activation_link=tmp_path / "bin" / "ruyi",
        telemetry_installation=tmp_path / "installation.json",
        system_ruyi_config=system_config,
        repo_config_path=tmp_path / "config" / "ruyi" / "config.toml",
    )
    qtbot.addWidget(window)

    window._refresh_pm_versions()

    assert not system_config.exists()
    assert window._pm_externally_managed
    assert not window._pm_available_table.isEnabled()
    assert not window._pm_refresh_btn.isEnabled()
    assert "system package manager" in window._pm_path_status.text()


def test_browse_opens_selected_binary_directory(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.write_bytes(_host_binary_header())
    started: list[tuple[str, list[str]]] = []
    monkeypatch.setattr(platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        shutil,
        "which",
        lambda program: "/usr/bin/dolphin" if program == "dolphin" else None,
    )
    monkeypatch.setattr(
        QProcess,
        "startDetached",
        lambda program, arguments: (
            started.append((program, list(arguments))) or (True, 123)
        ),
    )
    window._refresh_pm_versions(select_installed_version="0.50.0")

    assert window._pm_browse_btn.isEnabled()
    window._pm_browse_btn.click()

    assert started == [("dolphin", ["--select", os.fspath(binary)])]


def test_version_statuses_align_and_button_stacks_are_centered(
    window: ProvisionMainWindow,
    qtbot,
) -> None:
    window.resize(1060, 720)
    window.show()
    window._pm_status.setText(
        "Release information loaded from https://api.ruyisdk.cn/releases/latest-pm."
    )
    window._set_status_kind(window._pm_status, "success")
    window._pm_path_status.setText("PATH ready: ruyi resolves to the managed version.")
    window._set_status_kind(window._pm_path_status, "success")

    qtbot.waitUntil(
        lambda: window._pm_status.height() == window._pm_path_status.height(),
        timeout=1000,
    )

    assert window._pm_status.objectName() == window._pm_path_status.objectName()
    assert window._pm_status.property("statusKind") == ""
    assert window._pm_path_status.property("statusKind") == ""
    assert window._pm_status.alignment() & Qt.AlignmentFlag.AlignTop
    assert window._pm_path_status.alignment() & Qt.AlignmentFlag.AlignTop
    assert window._pm_status.height() == window._pm_path_status.height()

    available_buttons_center = (
        window._pm_refresh_btn.geometry().top()
        + window._pm_add_url_btn.geometry().bottom()
    ) // 2
    installed_buttons_center = (
        window._pm_local_refresh_btn.geometry().top()
        + window._pm_browse_btn.geometry().bottom()
    ) // 2
    assert (
        abs(
            available_buttons_center
            - window._pm_available_table.geometry().center().y()
        )
        <= 2
    )
    assert (
        abs(
            installed_buttons_center
            - window._pm_installed_table.geometry().center().y()
        )
        <= 2
    )
    assert window._pm_installed_table.horizontalScrollBar().maximum() == 0


def test_version_statuses_shrink_to_current_text_height(
    window: ProvisionMainWindow,
    qtbot,
) -> None:
    window.resize(1060, 720)
    window.show()
    long_message = " ".join(["A long status message that wraps."] * 12)
    window._pm_status.setText(long_message)
    window._pm_path_status.setText(long_message)
    window._align_pm_status_heights()
    tall_height = window._pm_status.height()

    window._pm_status.setText("API ready.")
    window._pm_path_status.setText("PATH ready.")
    window._align_pm_status_heights()
    qtbot.wait(0)

    expected_height = max(
        label.heightForWidth(label.width())
        for label in (window._pm_status, window._pm_path_status)
    )
    assert window._pm_status.height() == expected_height
    assert window._pm_path_status.height() == expected_height
    assert window._pm_status.height() < tall_height


def test_local_refresh_rescans_versions_directory(
    window: ProvisionMainWindow,
) -> None:
    window._refresh_pm_versions()
    assert window._pm_installed_table.rowCount() == 0

    window._pm_versions_directory.mkdir(parents=True)
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.write_bytes(_host_binary_header())

    window._pm_local_refresh_btn.click()

    assert window._pm_installed_table.rowCount() == 1
    assert window._pm_installed_table.item(0, 0).text() == "0.50.0"


def test_download_dialog_requires_confirmation_even_for_one_url(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    release = version_manager.RuyiRelease(
        "0.50.0",
        "stable",
        "2026-06-23T13:06:10Z",
        ("https://example.test/ruyi-0.50.0.amd64",),
        "x86_64",
    )
    window._pm_catalog_releases = [release]
    window._refresh_pm_versions(select_available_url=release.download_urls[0])
    started: list[tuple[version_manager.RuyiRelease, str]] = []
    monkeypatch.setattr(
        window,
        "_start_pm_download",
        lambda selected, url, _dialog: started.append((selected, url)),
    )

    window._download_selected_pm_version()

    dialog = window._pm_download_dialog
    assert dialog is not None
    qtbot.waitUntil(dialog.isVisible, timeout=1000)
    assert dialog._url_combo.count() == 1
    assert started == []

    dialog._download_button.click()

    assert started == [(release, release.download_urls[0])]
    assert dialog._progress.isVisible()
    assert dialog._progress.value() == 0
    assert dialog._progress.format() == "Connecting..."
    assert dialog._cancel_button.isEnabled()
    dialog.show_failure("test cleanup")
    dialog.reject()


def test_download_dialog_selects_url_and_tracks_success_or_failure(
    qtbot,
) -> None:
    release = version_manager.RuyiRelease(
        "0.50.0",
        "stable",
        "2026-06-23T13:06:10Z",
        (
            "https://primary.test/ruyi-0.50.0.amd64",
            "https://mirror.test/ruyi-0.50.0.amd64",
        ),
        "x86_64",
    )
    dialog = _VersionDownloadDialog(release)
    qtbot.addWidget(dialog)
    selected: list[str] = []
    dialog.download_requested.connect(selected.append)
    dialog.show()
    dialog._url_combo.setCurrentIndex(1)

    dialog._download_button.click()
    dialog.update_progress(50, 100)

    assert selected == [release.download_urls[1]]
    assert dialog._progress.value() == 50
    assert "50 B / 100 B" in dialog._progress.format()

    dialog.show_failure("mirror unavailable")

    assert dialog.isVisible()
    assert dialog._status.text() == "Download failed. See output below."
    assert "mirror unavailable" not in dialog._status.text()
    assert dialog._status.toolTip() == ""
    assert "mirror unavailable" in dialog._output.toPlainText()
    assert dialog._status.property("statusKind") == "error"
    assert dialog._url_combo.isEnabled()
    assert dialog._download_button.text() == "Retry"

    dialog._download_button.click()
    dialog.complete()

    assert selected == [release.download_urls[1], release.download_urls[1]]
    assert not dialog.isVisible()


def test_download_dialog_retries_another_url_and_closes_after_success(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    release = version_manager.RuyiRelease(
        "0.50.0",
        "stable",
        "2026-06-23T13:06:10Z",
        (
            "https://primary.test/ruyi-0.50.0.amd64",
            "https://mirror.test/ruyi-0.50.0.amd64",
        ),
        "x86_64",
    )
    window._pm_catalog_releases = [release]
    window._refresh_pm_versions(select_available_url=release.download_urls[0])
    calls: list[str] = []

    def download_release(
        selected_release,
        directory,
        *,
        download_url,
        progress,
        cancelled,
        response_changed,
    ):
        assert selected_release is release
        assert not cancelled()
        response_changed(None)
        calls.append(download_url)
        progress(32, 64)
        if download_url == release.download_urls[0]:
            raise OSError("primary unavailable")
        directory.mkdir(parents=True, exist_ok=True)
        binary = directory / "ruyi-0.50.0"
        binary.write_bytes(_host_binary_header())
        return binary

    monkeypatch.setattr(version_manager, "download_release", download_release)

    window._download_selected_pm_version()
    dialog = window._pm_download_dialog
    assert dialog is not None
    dialog._download_button.click()

    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert dialog.isVisible()
    assert "primary unavailable" not in dialog._status.text()
    assert "primary unavailable" in dialog._output.toPlainText()
    assert dialog._status.property("statusKind") == "error"
    assert dialog._download_button.text() == "Retry"

    dialog._url_combo.setCurrentIndex(1)
    dialog._download_button.click()

    qtbot.waitUntil(lambda: window._pm_download_dialog is None, timeout=2000)
    assert calls == list(release.download_urls)
    assert dialog._progress.value() == 50
    assert not dialog.isVisible()
    assert window._pm_installed_table.rowCount() == 1


def test_download_dialog_cancel_requests_worker_and_cleans_up(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    release = version_manager.RuyiRelease(
        "0.50.0",
        "stable",
        "2026-06-23T13:06:10Z",
        ("https://primary.test/ruyi-0.50.0.amd64",),
        "x86_64",
    )
    window._pm_catalog_releases = [release]
    window._refresh_pm_versions(select_available_url=release.download_urls[0])
    entered = threading.Event()

    def download_release(
        _release,
        directory,
        *,
        download_url,
        progress,
        cancelled,
        response_changed,
    ):
        assert download_url == release.download_urls[0]
        directory.mkdir(parents=True, exist_ok=True)
        partial = directory / ".ruyi-0.50.0.test.download"
        partial.write_bytes(b"partial")
        entered.set()
        while not cancelled():
            time.sleep(0.01)
        partial.unlink()
        raise version_manager.DownloadCancelledError("download cancelled")

    monkeypatch.setattr(version_manager, "download_release", download_release)

    window._download_selected_pm_version()
    dialog = window._pm_download_dialog
    assert dialog is not None
    dialog._download_button.click()
    qtbot.waitUntil(entered.is_set, timeout=1000)

    assert dialog._cancel_button.isEnabled()
    dialog._cancel_button.click()

    assert window._pm_download_dialog is None
    assert not dialog.isVisible()
    assert dialog._progress.value() == 0
    assert dialog._progress.format() == "Cancelling..."
    assert window._pm_status.text() == "Cancelling download..."
    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert window._pm_status.text() == "Download cancelled."
    assert not (window._pm_versions_directory / "ruyi-0.50.0").exists()
    assert not list(window._pm_versions_directory.glob("*.download"))


def test_add_url_is_transient_and_survives_refresh(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    custom_url = _host_download_url("0.53.0-beta.1")
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: (custom_url, True),
    )

    window._add_pm_download_url()

    assert window._pm_available_table.rowCount() == 1
    assert window._pm_available_table.item(0, 0).text() == "0.53.0-beta.1"
    assert window._pm_available_table.item(0, 1).text() == "custom"
    assert (
        window._pm_available_table.item(0, 2).text()
        == version_manager.host_architecture()
    )
    assert window._pm_download_btn.isEnabled()
    assert window._pm_remove_url_btn.isEnabled()

    window._on_pm_catalog_ready(
        version_manager.ReleaseCatalog(
            (
                version_manager.RuyiRelease(
                    "0.50.0",
                    "stable",
                    "2026-06-23T13:06:10Z",
                    ("https://example.test/ruyi",),
                    "x86_64",
                ),
            ),
            version_manager.PRIMARY_RELEASES_URL,
        )
    )

    assert window._pm_available_table.rowCount() == 2
    assert {window._pm_available_table.item(row, 1).text() for row in range(2)} == {
        "custom",
        "stable",
    }


def test_remove_does_not_remove_api_release_with_same_version(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    custom_url = _host_download_url("0.53.0-beta.1")
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: (custom_url, True),
    )
    window._add_pm_download_url()
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.53.0-beta.1",
            "testing",
            "2026-07-14T10:54:29Z",
            ("https://api.example/ruyi-0.53.0-beta.1.amd64",),
            "x86_64",
        )
    ]
    window._refresh_pm_versions(select_available_url=custom_url)

    assert window._pm_available_table.rowCount() == 2
    assert window._pm_remove_url_btn.isEnabled()

    for row in range(window._pm_available_table.rowCount()):
        if window._pm_available_table.item(row, 1).text() == "testing":
            window._pm_available_table.selectRow(row)
            break
    assert not window._pm_remove_url_btn.isEnabled()
    window._remove_selected_pm_download_url()
    assert len(window._pm_custom_releases) == 1
    assert window._pm_available_table.rowCount() == 2

    for row in range(window._pm_available_table.rowCount()):
        release = window._pm_available_table.item(row, 0).data(Qt.ItemDataRole.UserRole)
        if release is window._pm_custom_releases[0]:
            window._pm_available_table.selectRow(row)
            break
    assert window._pm_remove_url_btn.isEnabled()
    window._pm_remove_url_btn.click()

    assert window._pm_custom_releases == []
    assert window._pm_available_table.rowCount() == 1
    assert window._pm_available_table.item(0, 1).text() == "testing"
    assert not window._pm_remove_url_btn.isEnabled()


def test_add_url_rejects_incompatible_architecture(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        QInputDialog,
        "getText",
        lambda *_args, **_kwargs: (
            "https://downloads.example/ruyi-0.53.0-beta.1.riscv64",
            True,
        ),
    )
    warnings: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "warning",
        lambda _parent, title, message: warnings.append((title, message)),
    )

    window._add_pm_download_url()

    assert window._pm_custom_releases == []
    assert window._pm_available_table.rowCount() == 0
    assert warnings == [
        (
            "Incompatible ruyi architecture",
            f"The URL provides a riscv64 binary, but this computer uses {version_manager.host_architecture()}.",
        )
    ]


@pytest.mark.parametrize("machine", ["x86_64", "aarch64"])
def test_installed_table_hides_incompatible_binary(
    window: ProvisionMainWindow,
    monkeypatch,
    machine: str,
) -> None:
    monkeypatch.setattr(version_manager.platform, "machine", lambda: machine)
    window._pm_versions_directory.mkdir(parents=True)
    compatible = window._pm_versions_directory / "ruyi-0.50.0"
    incompatible = window._pm_versions_directory / "ruyi-0.51.0"
    compatible.write_bytes(_binary_header_for_arch(machine))
    incompatible.write_bytes(_binary_header_for_arch("riscv64"))

    window._refresh_pm_versions()

    assert window._pm_installed_table.rowCount() == 1
    assert window._pm_installed_table.item(0, 0).text() == "0.50.0"
    assert window._pm_installed_table.item(0, 2).text() == ""


def test_latest_note_ignores_transient_custom_releases(
    window: ProvisionMainWindow,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    stable = window._pm_versions_directory / "ruyi-0.50.0"
    custom = window._pm_versions_directory / "ruyi-0.53.0-beta.1"
    stable.write_bytes(_host_binary_header())
    custom.write_bytes(_host_binary_header())
    window._pm_catalog_releases = [
        version_manager.RuyiRelease(
            "0.50.0",
            "stable",
            "2026-06-23T13:06:10Z",
            ("https://example.test/ruyi",),
            "x86_64",
        )
    ]
    window._pm_custom_releases = [
        version_manager.RuyiRelease(
            "0.53.0-beta.1",
            "custom",
            "",
            ("https://example.test/custom-ruyi",),
            "x86_64",
        )
    ]

    window._refresh_pm_versions()

    notes = {
        window._pm_installed_table.item(row, 0).text(): window._pm_installed_table.item(
            row, 4
        ).text()
        for row in range(window._pm_installed_table.rowCount())
    }
    assert notes == {"0.53.0-beta.1": "", "0.50.0": "Latest"}


def test_deactivate_requires_selected_active_version(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.write_bytes(_host_binary_header())
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(binary)
    questions: list[bool] = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: (
            questions.append(True) or main_window.QMessageBox.StandardButton.Yes
        ),
    )

    window._refresh_pm_versions()

    assert window._pm_installed_table.currentRow() == -1
    assert not window._pm_toggle_activation_btn.isEnabled()
    window._toggle_selected_pm_version_activation()
    assert not questions
    assert window._pm_activation_link.is_symlink()

    window._pm_installed_table.selectRow(0)
    assert window._pm_toggle_activation_btn.isEnabled()
    assert window._pm_toggle_activation_btn.text() == "Deactivate"


def test_activation_confirms_and_backs_up_unmanaged_command(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.write_bytes(b"new")
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.write_bytes(b"old")
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: main_window.QMessageBox.StandardButton.Yes,
    )
    window._refresh_pm_versions(select_installed_version="0.50.0")

    window._toggle_selected_pm_version_activation()

    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert window._pm_activation_link.is_symlink()
    assert window._pm_activation_link.resolve() == binary
    assert window._pm_activation_link.with_name("ruyi.bak").read_bytes() == b"old"


def test_downloaded_versions_can_switch_delete_and_deactivate(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    stable = window._pm_versions_directory / "ruyi-0.50.0"
    testing = window._pm_versions_directory / "ruyi-0.52.0-alpha.20260714"
    stable.write_bytes(b"stable")
    testing.write_bytes(b"testing")
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(stable)
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: main_window.QMessageBox.StandardButton.Yes,
    )

    window._refresh_pm_versions(select_installed_version="0.52.0-alpha.20260714")
    assert window._pm_toggle_activation_btn.isEnabled()
    assert window._pm_toggle_activation_btn.text() == "Activate"
    assert window._pm_delete_btn.isEnabled()
    window._toggle_selected_pm_version_activation()
    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert window._pm_activation_link.resolve() == testing

    window._toggle_selected_pm_version_activation()
    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert not os.path.lexists(window._pm_activation_link)
    assert stable.exists() and testing.exists()

    window._refresh_pm_versions(select_installed_version="0.50.0")
    window._delete_selected_pm_version()
    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert not stable.exists()
    assert testing.exists()


def test_path_status_warns_when_another_ruyi_shadows_managed_version(
    window: ProvisionMainWindow,
    monkeypatch,
    tmp_path,
) -> None:
    window._pm_versions_directory.mkdir(parents=True)
    managed = window._pm_versions_directory / "ruyi-0.50.0"
    managed.write_bytes(b"managed")
    managed.chmod(0o755)
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(managed)
    shadow_bin = tmp_path / "shadow-bin"
    shadow_bin.mkdir()
    shadow = shadow_bin / "ruyi"
    shadow.write_text("#!/bin/sh\n")
    shadow.chmod(0o755)
    monkeypatch.setenv(
        "PATH",
        os.pathsep.join(
            [os.fspath(shadow_bin), os.fspath(window._pm_activation_link.parent)]
        ),
    )

    window._refresh_pm_versions()

    assert "resolves first" in window._pm_path_status.text()
    assert os.fspath(shadow) in window._pm_path_status.text()
    assert os.fspath(managed) not in window._pm_path_status.text()
    assert os.fspath(window._pm_activation_link) in window._pm_path_status.text()
    assert window._pm_path_status.property("statusKind") == "error"


@pytest.mark.parametrize(
    ("answers", "expected"),
    [
        ([main_window.QMessageBox.StandardButton.Yes], "consent"),
        (
            [
                main_window.QMessageBox.StandardButton.No,
                main_window.QMessageBox.StandardButton.Yes,
            ],
            "optout",
        ),
        (
            [
                main_window.QMessageBox.StandardButton.No,
                main_window.QMessageBox.StandardButton.No,
            ],
            "local",
        ),
    ],
)
def test_first_install_telemetry_choices_are_graphical(
    window: ProvisionMainWindow,
    monkeypatch,
    answers: list,
    expected: str,
) -> None:
    remaining = iter(answers)
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: next(remaining),
    )

    assert window._ask_for_pm_telemetry_mode() == expected


def test_first_install_runs_selected_mode_and_telemetry_status(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    window._pm_telemetry_installation.unlink()
    log = tmp_path / "telemetry-commands.log"
    binary = window._pm_versions_directory / "ruyi-0.50.0"
    binary.parent.mkdir(parents=True)
    binary.write_text(
        "#!/bin/sh\n"
        f"printf '%s|%s\\n' \"$0\" \"$*\" >> '{log}'\n"
        "read upload\n"
        "if [ \"$upload\" = 'y' ]; then printf 'on\\n'; exit 0; fi\n"
        "read optout\n"
        "if [ \"$optout\" = 'y' ]; then printf 'off\\n'; else printf 'local\\n'; fi\n"
    )
    binary.chmod(0o755)
    window._pm_activation_link.parent.mkdir(parents=True)
    window._pm_activation_link.symlink_to(binary)
    answers = iter(
        [
            main_window.QMessageBox.StandardButton.No,
            main_window.QMessageBox.StandardButton.No,
        ]
    )
    monkeypatch.setattr(
        main_window.QMessageBox,
        "question",
        lambda *_args, **_kwargs: next(answers),
    )

    window._maybe_start_pm_telemetry()

    qtbot.waitUntil(lambda: window._pm_worker is None, timeout=2000)
    assert log.read_text().splitlines() == [
        f"{window._pm_activation_link}|telemetry status"
    ]
    assert window._pm_status.text() == "Telemetry mode: local"


def test_pm_failure_uses_error_dialog_without_output_panel(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    errors: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "critical",
        lambda _parent, title, message: errors.append((title, message)),
    )
    window._pm_operation = "activate"

    window._on_pm_worker_failed("activation failed")

    assert errors == [("Operation failed", "activation failed")]
    assert window._pm_status.text() == "Operation failed. See the error dialog."
    assert not hasattr(window, "_pm_output")
