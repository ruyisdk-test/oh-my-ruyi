"""First-use setup orchestration."""

from __future__ import annotations

from oh_my_ruyi.infra import version_manager
from oh_my_ruyi.ui.views import main_window
from oh_my_ruyi.ui.views.version_dialogs import (
    VersionDownloadDialog as _VersionDownloadDialog,
)
from tests._helpers import (
    _first_use_window,
)


def test_first_use_catalog_prefers_latest_stable_release(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)

    window._on_pm_catalog_ready(
        version_manager.ReleaseCatalog(
            (
                version_manager.RuyiRelease(
                    "0.52.0-alpha.1",
                    "testing",
                    "2026-07-14",
                    ("https://example.test/testing",),
                    "x86_64",
                ),
                version_manager.RuyiRelease(
                    "0.50.0",
                    "stable",
                    "2026-06-23",
                    ("https://example.test/stable-old",),
                    "x86_64",
                ),
                version_manager.RuyiRelease(
                    "0.51.0",
                    "stable",
                    "2026-08-01",
                    ("https://example.test/stable-new",),
                    "x86_64",
                ),
            ),
            version_manager.PRIMARY_RELEASES_URL,
        )
    )

    dialog = window._first_use_dialog
    assert dialog is not None
    assert window._first_use_release is not None
    assert window._first_use_release.version == "0.51.0"
    assert dialog.current_label.text() == "Current step: Download a compatible ruyi"
    assert dialog.remaining_label.text() == "Remaining steps: 3"
    assert dialog.action_button.text() == "Download and activate"
    assert dialog.skip_button.text() == "Skip download"


def test_first_use_uses_testing_release_when_stable_is_unavailable(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)

    window._on_pm_catalog_ready(
        version_manager.ReleaseCatalog(
            (
                version_manager.RuyiRelease(
                    "0.52.0-alpha.1",
                    "testing",
                    "2026-07-14",
                    ("https://example.test/testing",),
                    "macos-arm64",
                ),
            ),
            version_manager.PRIMARY_RELEASES_URL,
        )
    )

    assert window._first_use_release is not None
    assert window._first_use_release.version == "0.52.0-alpha.1"
    assert window._first_use_dialog is not None
    assert "testing" in window._first_use_dialog.status.text()
    assert window._first_use_dialog.action_button.text() == "Download and activate"


def test_first_use_catalog_failure_can_continue_without_download(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)
    failures: list[tuple[str, str]] = []
    monkeypatch.setattr(
        main_window.QMessageBox,
        "critical",
        lambda _parent, title, message: failures.append((title, message)),
    )
    window._pm_operation = "refresh"

    window._on_pm_worker_failed("catalog unavailable")

    dialog = window._first_use_dialog
    assert dialog is not None
    assert dialog.action_button.text() == "Retry"
    assert dialog.skip_button.text() == "Continue without download"
    assert failures == []


def test_first_use_skip_switches_to_repo_management(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)
    attempts: list[None] = []
    monkeypatch.setattr(
        window._repo_manager_tab,
        "choose_default_source_and_update",
        lambda: attempts.append(None) or False,
    )

    window._skip_first_use_download()

    qtbot.waitUntil(lambda: bool(attempts))
    dialog = window._first_use_dialog
    assert dialog is not None
    assert window._tabs.currentWidget() is window._repo_manager_tab
    assert dialog.step == 2
    assert (
        dialog.current_label.text()
        == "Current step: Choose and update the RuyiSDK mirror"
    )
    assert dialog.action_button.text() == "Choose mirror"


def test_first_use_downloads_activates_then_opens_repo_management(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)
    release = version_manager.RuyiRelease(
        "0.51.0",
        "stable",
        "2026-08-01",
        ("https://example.test/stable",),
        version_manager.host_architecture(),
    )
    window._first_use_release = release
    source_dialog_attempted: list[None] = []

    def download_release(release, directory, **_kwargs):
        path = directory / f"ruyi-{release.version}"
        directory.mkdir(parents=True, exist_ok=True)
        path.write_bytes(b"standalone ruyi")
        path.chmod(0o755)
        return path

    monkeypatch.setattr(version_manager, "download_release", download_release)
    monkeypatch.setattr(
        window._repo_manager_tab,
        "choose_default_source_and_update",
        lambda: source_dialog_attempted.append(None) or False,
    )
    window._pm_activation_link.parent.mkdir(parents=True)

    window._start_first_use_download()

    download_dialog = window._pm_download_dialog
    assert isinstance(download_dialog, _VersionDownloadDialog)
    assert download_dialog.isVisible()
    download_dialog._download_button.click()

    qtbot.waitUntil(
        lambda: window._first_use_operation == "repository",
        timeout=3000,
    )
    qtbot.waitUntil(lambda: bool(source_dialog_attempted), timeout=1000)
    assert window._pm_activation_link.is_symlink()
    assert window._pm_activation_link.resolve() == (
        window._pm_versions_directory / "ruyi-0.51.0"
    )
    assert window._tabs.currentWidget() is window._repo_manager_tab


def test_first_use_exits_and_cancels_repository_update(
    qtbot, monkeypatch, tmp_path
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)
    cancelled: list[None] = []
    monkeypatch.setattr(
        window._repo_manager_tab,
        "cancel_current_update",
        lambda: cancelled.append(None),
    )
    window._first_use_operation = "repository"

    dialog = window._first_use_dialog
    assert dialog is not None
    dialog.reject()

    assert not window._first_use_active
    assert cancelled == [None]


def test_first_use_repo_update_opens_about_and_completes_dialog(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    window = _first_use_window(qtbot, monkeypatch, tmp_path)
    window._first_use_operation = "repository"

    window._on_first_use_repo_update_finished("ruyisdk", True, "Updated ruyisdk.")

    dialog = window._first_use_dialog
    assert dialog is not None
    assert window._tabs.currentWidget() is window._about_tab
    assert dialog.step == 3
    assert dialog.remaining_label.text() == "Remaining steps: 0"
    assert dialog.action_button.text() == "Finish"
