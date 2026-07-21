from __future__ import annotations

import os
from pathlib import Path

from PySide6.QtWidgets import QApplication

from oh_my_ruyi.first_use import FirstUseDialog, should_offer_first_use_setup


def test_first_use_requires_missing_telemetry_path_command_and_data_dir(
    qtbot,
    tmp_path: Path,
) -> None:
    telemetry = tmp_path / "state" / "ruyi" / "telemetry" / "installation.json"
    data_dir = tmp_path / "share" / "oh-my-ruyi"

    def missing_ruyi(_name, **_kwargs):
        return None

    assert should_offer_first_use_setup(
        telemetry,
        data_dir,
        which=missing_ruyi,
    )

    telemetry.parent.mkdir(parents=True)
    telemetry.write_text("{}")
    assert not should_offer_first_use_setup(
        telemetry,
        data_dir,
        which=missing_ruyi,
    )

    telemetry.unlink()
    data_dir.mkdir(parents=True)
    assert not should_offer_first_use_setup(
        telemetry,
        data_dir,
        which=missing_ruyi,
    )

    data_dir.rmdir()
    assert not should_offer_first_use_setup(
        telemetry,
        data_dir,
        which=lambda _name, **_kwargs: "/usr/bin/ruyi",
    )


def test_first_use_dialog_shows_current_and_remaining_steps(qtbot) -> None:
    _app = QApplication.instance() or QApplication([])
    dialog = FirstUseDialog()
    qtbot.addWidget(dialog)

    dialog.set_stage(
        2,
        "Choose the mirror used by the default ruyisdk repository.",
        action="Choose mirror",
    )

    assert (
        dialog.current_label.text()
        == "Current step: Choose and update the RuyiSDK mirror"
    )
    assert dialog.remaining_label.text() == "Remaining steps: 1"
    assert dialog.steps.item(2).font().bold()
    assert dialog.action_button.text() == "Choose mirror"

    with qtbot.waitSignal(dialog.skip_requested):
        dialog.set_stage(0, "Ready", skip="Skip download")
        dialog.skip_button.click()


def test_first_use_ignores_ruyi_from_running_python_environment(tmp_path: Path) -> None:
    telemetry = tmp_path / "state" / "installation.json"
    data_dir = tmp_path / "share" / "oh-my-ruyi"
    runtime_bin = tmp_path / "venv" / "bin"
    runtime_bin.mkdir(parents=True)
    bundled_ruyi = runtime_bin / "ruyi"
    bundled_ruyi.write_text("#!/bin/sh\n")
    bundled_ruyi.chmod(0o755)

    assert should_offer_first_use_setup(
        telemetry,
        data_dir,
        path=os.fspath(runtime_bin),
        runtime_executable=runtime_bin / "python3",
    )


def test_first_use_finds_external_ruyi_after_runtime_environment(
    tmp_path: Path,
) -> None:
    telemetry = tmp_path / "state" / "installation.json"
    data_dir = tmp_path / "share" / "oh-my-ruyi"
    runtime_bin = tmp_path / "venv" / "bin"
    external_bin = tmp_path / "usr" / "local" / "bin"
    runtime_bin.mkdir(parents=True)
    external_bin.mkdir(parents=True)
    for directory in (runtime_bin, external_bin):
        command = directory / "ruyi"
        command.write_text("#!/bin/sh\n")
        command.chmod(0o755)

    assert not should_offer_first_use_setup(
        telemetry,
        data_dir,
        path=os.pathsep.join((os.fspath(runtime_bin), os.fspath(external_bin))),
        runtime_executable=runtime_bin / "python3",
    )
