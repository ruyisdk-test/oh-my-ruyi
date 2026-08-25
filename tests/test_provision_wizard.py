"""Provisioning wizard pages and actions."""

from __future__ import annotations

from oh_my_ruyi.core.state_machine import ProvisionStateMachine
import os
import platform
import threading
import time
from types import SimpleNamespace
import pytest
from PySide6.QtCore import QProcess, QTimer, Qt
from PySide6.QtWidgets import QApplication
from oh_my_ruyi.infra import os_storage, ruyi_adapter
from oh_my_ruyi.ui.views import _provision_wizard_mixin, main_window
from oh_my_ruyi.ui.views.main_window import ProvisionMainWindow
from oh_my_ruyi.workers import workers
from oh_my_ruyi.workers.workers import FlashWorker
from tests._helpers import (
    _contrast_ratio,
    _test_palette,
)


def test_sidebar_cannot_skip_forward_steps(window: ProvisionMainWindow) -> None:
    print("BEFORE SET_STEP: current=", window._machine.current_step)
    window._set_step(ProvisionStateMachine.STEP_PACKAGES)
    print("AFTER SET_STEP: current=", window._machine.current_step)

    window._steps.setCurrentRow(ProvisionStateMachine.STEP_REVIEW)
    print("AFTER SETCURRENTROW: current=", window._machine.current_step)

    assert window._machine.current_step == ProvisionStateMachine.STEP_PACKAGES
    assert window._steps.currentRow() == ProvisionStateMachine.STEP_PACKAGES


def test_device_step_is_clickable_after_returning_to_ready(
    window: ProvisionMainWindow,
) -> None:
    window.state.mr = object()
    window._set_step(ProvisionStateMachine.STEP_DEVICE)

    window._go_back()

    device_item = window._steps.item(ProvisionStateMachine.STEP_DEVICE)
    assert device_item.flags() & Qt.ItemFlag.ItemIsEnabled

    window._steps.setCurrentRow(ProvisionStateMachine.STEP_DEVICE)

    assert window._machine.current_step == ProvisionStateMachine.STEP_DEVICE


@pytest.mark.parametrize(
    ("step", "widget_name"),
    [
        (ProvisionStateMachine.STEP_DEVICE, "_device_list"),
        (ProvisionStateMachine.STEP_VARIANT, "_variant_list"),
        (ProvisionStateMachine.STEP_COMBO, "_combo_list"),
        (ProvisionStateMachine.STEP_PACKAGES, "_packages_list"),
        (ProvisionStateMachine.STEP_DOWNLOAD, "_download_log"),
        (ProvisionStateMachine.STEP_FLASH, "_flash_log"),
    ],
)
def test_primary_step_content_fills_page_height(
    window: ProvisionMainWindow,
    qtbot,
    step: int,
    widget_name: str,
) -> None:
    window.resize(1060, 720)
    window._stack.setCurrentIndex(step)
    window.show()
    qtbot.waitUntil(lambda: window._stack.height() > 400, timeout=1000)

    page = window._stack.widget(step)
    widget = getattr(window, widget_name)
    bottom_gap = page.height() - widget.geometry().bottom() - 1

    assert bottom_gap <= page.layout().contentsMargins().bottom() + 1


@pytest.mark.parametrize("dark", [False, True])
def test_theme_uses_application_palette(
    window: ProvisionMainWindow,
    qtbot,
    dark: bool,
) -> None:
    app = QApplication.instance()
    assert app is not None
    original = app.palette()
    try:
        app.setPalette(_test_palette(dark=dark))
        expected_window = "#202124" if dark else "#f8f9fa"
        qtbot.waitUntil(
            lambda: expected_window in window.styleSheet(),
            timeout=1000,
        )
        colors = window._theme_colors()
        stylesheet = window.styleSheet()

        assert colors["window"] in stylesheet
        assert colors["window_text"] in stylesheet
        assert colors["base"] in stylesheet
        assert colors["highlight"] in stylesheet
        assert colors["disabled_text"] in stylesheet
        assert _contrast_ratio(colors["window_text"], colors["window"]) >= 4.5
        assert _contrast_ratio(colors["text"], colors["base"]) >= 4.5
        assert _contrast_ratio(colors["success"], colors["window"]) >= 4.5
        assert _contrast_ratio(colors["warning"], colors["window"]) >= 4.5
        assert _contrast_ratio(colors["error"], colors["window"]) >= 4.5
    finally:
        app.setPalette(original)


def test_storage_requires_explicit_target(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: False)
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(
        os_storage,
        "list_disks",
        lambda: [
            os_storage.BlockDeviceChoice(
                path="/dev/test-disk",
                display_name="/dev/test-disk - 32.0 GiB",
            )
        ],
    )

    window._populate_storage()
    target = window._storage_inputs["disk"]

    assert target.currentIndex() == -1
    assert target.currentText() == ""
    assert not window._storage_complete()


def test_flash_revalidates_mount_state(
    window: ProvisionMainWindow,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: False)
    window._tabs.setCurrentIndex(2)
    target = tmp_path / "target.img"
    target.touch()
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    window.state.host_blkdev_map = {"disk": str(target)}
    window._set_step(ProvisionStateMachine.STEP_REVIEW)
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(os_storage, "list_disks", lambda: [])
    monkeypatch.setattr(os_storage, "is_disk_or_child_mounted", lambda _path: True)
    monkeypatch.setattr(os_storage, "device_fingerprint", lambda _path: "target-v1")
    window.state.host_blkdev_fingerprints = {"disk": "target-v1"}

    window._start_flash()

    assert window._machine.current_step == ProvisionStateMachine.STEP_STORAGE
    assert "now mounted" in window._storage_error.text()
    assert window._storage_mount_warnings["disk"].isVisibleTo(window)
    assert not window._storage_mount_confirmations["disk"].isChecked()
    assert window._worker is None


def test_failed_download_start_releases_busy_state(window: ProvisionMainWindow) -> None:
    window._tabs.setCurrentIndex(2)
    window.state.pkg_atoms = ["board-image/test"]
    window._set_step(ProvisionStateMachine.STEP_DOWNLOAD)
    window._download_process = QProcess(window)

    window._on_download_process_error(QProcess.ProcessError.FailedToStart)

    assert window._download_process is None
    assert not window._is_busy()
    assert window._machine.download_recoverable
    assert window._download_recovery_row.isVisibleTo(window)


def test_download_log_replaces_progress_line(window: ProvisionMainWindow) -> None:
    window._download_log.clear()

    window._download_log.feed_bytes(b"Connecting...\nfile 10%\r")
    window._download_log.feed_bytes(b"file 100%\nSaved\n", final=True)

    assert window._download_log.toPlainText().splitlines() == [
        "Connecting...",
        "file 100%",
        "Saved",
    ]


def test_successful_download_prepares_provision_and_advances_to_review(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    """A successful package download must build PreparedProvision and advance."""
    window._tabs.setCurrentIndex(2)
    window.state.pkg_atoms = ["board-image/test"]
    window.state.mr = SimpleNamespace()  # type: ignore[assignment]
    prepared = SimpleNamespace(
        strategies=[],
        pkg_part_maps={},
        needed_cmds=set(),
        requested_host_blkdevs=[],
    )
    monkeypatch.setattr(
        ruyi_adapter,
        "prepare_provision",
        lambda _config, _mr, _atoms: prepared,
    )
    monkeypatch.setattr(
        window.provision_controller,
        "start_download",
        lambda: QTimer.singleShot(
            0,
            lambda: window.provision_controller.download_finished.emit(
                True, "Download complete."
            ),
        ),
    )

    window._set_step(ProvisionStateMachine.STEP_PACKAGES)
    window._go_next()

    qtbot.waitUntil(
        lambda: window._machine.current_step == ProvisionStateMachine.STEP_REVIEW,
        timeout=2000,
    )
    assert window.state.prepared is prepared
    assert window._machine.download_ok
    assert not window._machine.download_recoverable


def test_fastboot_check_runs_without_blocking_ui(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nsleep 0.1\nprintf 'SERIAL\\tfastboot\\n'\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )
    event_loop_ran: list[bool] = []

    window._check_fastboot_devices()
    QTimer.singleShot(0, lambda: event_loop_ran.append(True))

    qtbot.waitUntil(lambda: bool(event_loop_ran), timeout=500)
    assert window._fastboot_process is not None
    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert window._fastboot_ok
    assert window._fastboot_status.text() == "Fastboot device check completed."
    assert "SERIAL" not in window._fastboot_status.text()
    assert "SERIAL" in window._fastboot_log.toPlainText()


def test_fastboot_check_reports_missing_command(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    monkeypatch.setattr(
        _provision_wizard_mixin,
        "FASTBOOT_PROGRAM",
        os.fspath(tmp_path / "missing-fastboot"),
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert not window._fastboot_ok
    assert window._fastboot_status.text() == "fastboot command was not found."
    assert window._check_fastboot_btn.isEnabled()


def test_fastboot_check_reports_no_devices(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nexit 0\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert not window._fastboot_ok
    assert window._fastboot_status.text() == "No fastboot devices found."


def test_fastboot_check_accepts_nonempty_stderr_without_parsing(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nprintf 'device output\\n' >&2\nexit 0\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert window._fastboot_ok
    assert "device output" not in window._fastboot_status.text()
    assert "device output" in window._fastboot_log.toPlainText()


def test_fastboot_check_accepts_device_record_on_stderr(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nprintf 'SERIAL\\tfastboot\\n' >&2\nexit 0\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert window._fastboot_ok
    assert "SERIAL" not in window._fastboot_status.text()
    assert "SERIAL" in window._fastboot_log.toPlainText()


def test_fastboot_check_accepts_dfu_download_output(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nprintf 'dfu-device       DFU download\\n'\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert window._fastboot_ok
    assert "dfu-device       DFU download" not in window._fastboot_status.text()
    assert "dfu-device       DFU download" in window._fastboot_log.toPlainText()


def test_fastboot_check_accepts_nonempty_stdout_without_parsing(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
    tmp_path,
) -> None:
    fastboot = tmp_path / "fastboot"
    fastboot.write_text("#!/bin/sh\nprintf 'unrecognized device format\\n'\n")
    fastboot.chmod(0o755)
    monkeypatch.setattr(
        _provision_wizard_mixin, "FASTBOOT_PROGRAM", os.fspath(fastboot)
    )

    window._check_fastboot_devices()

    qtbot.waitUntil(lambda: window._fastboot_process is None, timeout=5000)
    assert window._fastboot_ok
    assert "unrecognized device format" not in window._fastboot_status.text()
    assert "unrecognized device format" in window._fastboot_log.toPlainText()


def test_flash_rejects_replaced_target(
    window: ProvisionMainWindow,
    monkeypatch,
    tmp_path,
) -> None:
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: False)
    target = tmp_path / "target.img"
    target.touch()
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    window.state.host_blkdev_map = {"disk": str(target)}
    window.state.host_blkdev_fingerprints = {"disk": "old-device"}
    monkeypatch.setattr(os_storage, "device_fingerprint", lambda _path: "new-device")
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(os_storage, "list_disks", lambda: [])

    window._start_flash()

    assert window._machine.current_step == ProvisionStateMachine.STEP_STORAGE
    assert "has changed" in window._storage_error.text()


def test_review_steps_render_ruyi_rich_markup(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=[], needed_cmds=set()
    )
    monkeypatch.setattr(
        ruyi_adapter,
        "compute_pretend_steps",
        lambda *_args: ["write [yellow]/path/to/image.img[/] to [green]/dev/rdisk4[/]"],
    )
    monkeypatch.setattr(ruyi_adapter, "missing_cmds", lambda _prepared: [])
    monkeypatch.setattr(
        ruyi_adapter,
        "needs_fastboot_confirmation",
        lambda _prepared: False,
    )

    window._populate_review()

    assert window._review_steps.toPlainText().strip() == (
        "* write /path/to/image.img to /dev/rdisk4"
    )
    assert "[yellow]" not in window._review_steps.toPlainText()
    assert "color:" in window._review_steps.toHtml()


def test_flash_confirmation_renders_ruyi_rich_markup(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    captured: dict[str, object] = {}

    def fake_exec(box) -> int:  # noqa: ANN001
        captured["text"] = box.text()
        captured["format"] = box.textFormat()
        captured["default"] = box.standardButton(box.defaultButton())
        return int(main_window.QMessageBox.StandardButton.Yes)

    monkeypatch.setattr(main_window.QMessageBox, "exec", fake_exec)
    response: dict[str, bool] = {}

    window._on_flash_yes_no_requested(
        "Do you want to retry the command with [yellow]sudo[/]?",
        False,
        response,
    )

    assert "[yellow]" not in str(captured["text"])
    assert "sudo" in str(captured["text"])
    assert "color:" in str(captured["text"])
    assert captured["format"] == Qt.TextFormat.RichText
    assert captured["default"] == main_window.QMessageBox.StandardButton.No
    assert response["answer"] is True


def test_successful_flash_advances_to_done_and_can_return_to_flash(
    window: ProvisionMainWindow,
) -> None:
    window.state.pkg_atoms = ["image/pkg"]
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=[], needed_cmds=set()
    )
    window._flash_log.setPlainText("fastboot flash complete")
    window._set_step(ProvisionStateMachine.STEP_FLASH)

    window._on_flash_finished(0)

    assert window._machine.current_step == ProvisionStateMachine.STEP_DONE
    assert window.state.flash_ret == 0
    assert window._done_label.text() == (
        "It seems the flashing has finished without errors. Happy hacking!"
    )

    window._go_back()

    assert window._machine.current_step == ProvisionStateMachine.STEP_FLASH
    assert window._flash_status.text() == "Flash complete."
    assert window._flash_log.toPlainText() == "fastboot flash complete"
    assert window._next_btn.isEnabled()
    assert (
        window._steps.item(ProvisionStateMachine.STEP_DONE).flags()
        & Qt.ItemFlag.ItemIsEnabled
    )

    window._go_next()

    assert window._machine.current_step == ProvisionStateMachine.STEP_DONE
    assert (
        window._steps.item(ProvisionStateMachine.STEP_FLASH).flags()
        & Qt.ItemFlag.ItemIsEnabled
    )

    window._steps.setCurrentRow(ProvisionStateMachine.STEP_FLASH)
    assert window._machine.current_step == ProvisionStateMachine.STEP_FLASH

    window._steps.setCurrentRow(ProvisionStateMachine.STEP_DONE)
    assert window._machine.current_step == ProvisionStateMachine.STEP_DONE


def test_failed_flash_stays_on_flash_page(window: ProvisionMainWindow) -> None:
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=[], needed_cmds=set()
    )
    window._set_step(ProvisionStateMachine.STEP_FLASH)

    window._on_flash_finished(1)

    assert window._machine.current_step == ProvisionStateMachine.STEP_FLASH
    assert window.state.flash_ret == 1
    assert window._flash_status.text() == "Flash failed (exit code 1)."
    assert window._machine.flash_recoverable
    assert not (
        window._steps.item(ProvisionStateMachine.STEP_DONE).flags()
        & Qt.ItemFlag.ItemIsEnabled
    )


def test_interrupt_flash_requests_worker_cancellation(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    worker = FlashWorker(None, None, {}, {}, set())  # type: ignore[arg-type]
    requests: list[bool] = []
    monkeypatch.setattr(worker, "request_cancel", lambda: requests.append(True))
    window._worker = worker
    window._set_step(ProvisionStateMachine.STEP_FLASH)

    window._interrupt_flash_btn.click()

    assert requests == [True]
    assert window._flash_cancel_requested
    assert window._flash_status.text() == "Interrupting flash..."
    assert not window._interrupt_flash_btn.isEnabled()

    window._worker = None


def test_interrupted_flash_becomes_recoverable(window: ProvisionMainWindow) -> None:
    window._tabs.setCurrentIndex(2)
    window.state.flash_ret = 0
    window._flash_cancel_requested = True
    window._set_step(ProvisionStateMachine.STEP_FLASH)

    window._on_flash_cancelled()

    assert window._machine.current_step == ProvisionStateMachine.STEP_FLASH
    assert window.state.flash_ret is None
    assert window._flash_status.text() == "Flash interrupted."
    assert window._machine.flash_recoverable
    assert window._flash_recovery_row.isVisibleTo(window)


@pytest.mark.skipif(
    platform.system() == "Windows", reason="native Windows flashing is unsupported"
)
@pytest.mark.parametrize("command", ["dd", "fastboot"])
def test_flash_worker_interrupts_active_command(
    monkeypatch,
    tmp_path,
    command: str,
) -> None:
    executable = tmp_path / command
    executable.write_text("#!/bin/sh\n/bin/sleep 30\n")
    executable.chmod(0o755)
    monkeypatch.setenv("PATH", os.fspath(tmp_path))
    target = tmp_path / "target.img"
    target.touch()
    worker = FlashWorker(
        None,
        None,
        {"disk": os.fspath(target)},
        {"disk": "reviewed-device"},
        set(),
    )  # type: ignore[arg-type]
    monkeypatch.setattr(
        os_storage, "device_fingerprint", lambda _path: "reviewed-device"
    )
    monkeypatch.setattr(os_storage, "is_disk_or_child_mounted", lambda _path: False)
    argv = ["dd", f"of={target}"] if command == "dd" else ["fastboot", "flash"]
    result: list[int] = []
    thread = threading.Thread(
        target=lambda: result.append(worker._call_subprocess(argv))
    )

    thread.start()
    deadline = time.monotonic() + 2
    while worker._process is None and time.monotonic() < deadline:
        time.sleep(0.01)
    assert worker._process is not None

    worker.request_cancel()
    thread.join(timeout=5)

    assert not thread.is_alive()
    assert result and result[0] != 0


def test_unflashed_done_back_returns_to_fresh_review(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window.state.pkg_atoms = ["image/pkg"]
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=[], needed_cmds=set()
    )
    window._proceed_cb.setChecked(True)
    window._fastboot_ok = True
    monkeypatch.setattr(
        window,
        "_populate_review",
        lambda: (
            window._proceed_cb.setChecked(False),
            setattr(window, "_fastboot_ok", False),
        ),
    )
    window._set_step(ProvisionStateMachine.STEP_DONE)

    window._go_back()

    assert window._machine.current_step == ProvisionStateMachine.STEP_REVIEW
    assert not window._proceed_cb.isChecked()
    assert not window._fastboot_ok


def test_flash_worker_revalidates_dd_target_before_spawn(monkeypatch, tmp_path) -> None:
    target = tmp_path / "target.img"
    target.touch()
    worker = FlashWorker(
        None,
        None,
        {"disk": os.fspath(target)},
        {"disk": "reviewed-device"},
        set(),
    )  # type: ignore[arg-type]
    monkeypatch.setattr(os_storage, "device_fingerprint", lambda _path: "replacement")
    spawned: list[bool] = []
    monkeypatch.setattr(
        workers.subprocess,
        "Popen",
        lambda *_args, **_kwargs: spawned.append(True),
    )

    with pytest.raises(RuntimeError, match="changed after review"):
        worker._call_subprocess(["dd", "if=image", f"of={target}"])

    assert not spawned


def test_flash_worker_rejects_multiple_dd_outputs(monkeypatch, tmp_path) -> None:
    target = tmp_path / "target.img"
    other = tmp_path / "other.img"
    target.touch()
    other.touch()
    worker = FlashWorker(
        None,
        None,
        {"disk": os.fspath(target)},
        {"disk": "reviewed-device"},
        set(),
    )  # type: ignore[arg-type]
    monkeypatch.setattr(
        os_storage, "device_fingerprint", lambda _path: "reviewed-device"
    )

    with pytest.raises(RuntimeError, match="exactly one"):
        worker._call_subprocess(["dd", "if=image", f"of={target}", f"of={other}"])


def test_slow_storage_discovery_does_not_block_ui(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: True)

    def slow_discovery():
        time.sleep(0.1)
        return [
            os_storage.BlockDeviceChoice(
                path="/dev/rdisk2",
                display_name="/dev/rdisk2 - 32.0 GiB",
                fingerprint="darwin:disk2",
            )
        ]

    monkeypatch.setattr(os_storage, "list_disks", slow_discovery)
    event_loop_ran: list[bool] = []

    window._populate_storage()
    QTimer.singleShot(0, lambda: event_loop_ran.append(True))

    qtbot.waitUntil(lambda: bool(event_loop_ran), timeout=500)
    assert window._worker is not None
    qtbot.waitUntil(lambda: window._worker is None, timeout=2000)
    assert window._storage_box.isEnabled()
    assert window._storage_inputs["disk"].count() == 1


def test_storage_refresh_discovers_new_disk_and_preserves_selection(
    window: ProvisionMainWindow,
    monkeypatch,
    qtbot,
) -> None:
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: False)
    first_disk = os_storage.BlockDeviceChoice(
        path="/dev/disk-old",
        display_name="/dev/disk-old - 16.0 GiB",
        fingerprint="old-disk",
    )
    new_disk = os_storage.BlockDeviceChoice(
        path="/dev/disk-new",
        display_name="/dev/disk-new - 32.0 GiB",
        fingerprint="new-disk",
    )
    discoveries = iter([[first_disk], [first_disk, new_disk]])
    monkeypatch.setattr(os_storage, "list_disks", lambda: next(discoveries))

    window._set_step(ProvisionStateMachine.STEP_STORAGE)
    window._populate_storage()
    target = window._storage_inputs["disk"]
    target.setCurrentIndex(0)

    window._refresh_storage_btn.click()

    qtbot.waitUntil(lambda: window._worker is None, timeout=1000)
    target = window._storage_inputs["disk"]
    assert target.count() == 2
    assert target.findData("/dev/disk-new") >= 0
    assert window._storage_path(target) == "/dev/disk-old"
    assert window._refresh_storage_btn.isEnabled()


def test_storage_controls_have_accessible_labels(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    monkeypatch.setattr(os_storage, "validation_is_slow", lambda: False)
    window.state.prepared = SimpleNamespace(
        requested_host_blkdevs=["disk"],
        needed_cmds=set(),
    )
    monkeypatch.setattr(ruyi_adapter, "part_description", lambda _part: "Whole disk")
    monkeypatch.setattr(os_storage, "list_disks", lambda: [])

    window._populate_storage()
    target = window._storage_inputs["disk"]
    labels = target.parentWidget().findChildren(type(window._storage_error))
    browse_buttons = target.parentWidget().findChildren(type(window._next_btn))

    assert target.accessibleName() == "Target disk for Whole disk"
    assert any(label.buddy() is target for label in labels)
    assert any(
        button.accessibleName() == "Choose target disk or image file for Whole disk"
        for button in browse_buttons
    )
