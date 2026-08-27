from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from oh_my_ruyi.processes import version_activation_child
from oh_my_ruyi.runtime import worker_services
from oh_my_ruyi.services import version_manager


def test_activation_child_delegates_and_serializes_result(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "ruyi-0.50.0"
    directory = tmp_path / "versions"
    link = tmp_path / "bin" / "ruyi"
    backup = tmp_path / "bin" / "ruyi.bak"
    state = version_manager.ActivationState(
        link,
        True,
        True,
        True,
        binary,
        "0.50.0",
    )
    calls: list[tuple[Path, Path, Path, bool]] = []

    def activate(
        actual_binary: Path,
        actual_directory: Path,
        *,
        link: Path,
        backup_unmanaged: bool,
    ) -> version_manager.ActivationResult:
        calls.append((actual_binary, actual_directory, link, backup_unmanaged))
        return version_manager.ActivationResult(state, backup)

    monkeypatch.setattr(version_activation_child, "activate_version", activate)

    assert (
        version_activation_child.main(
            [
                "activate",
                str(binary),
                str(directory),
                str(link),
                "--backup-unmanaged",
            ]
        )
        == 0
    )

    assert calls == [(binary, directory, link, True)]
    assert json.loads(capsys.readouterr().out) == {
        "target": str(binary),
        "version": "0.50.0",
        "backup_path": str(backup),
    }


def test_deactivation_child_delegates_and_serializes_result(
    monkeypatch,
    capsys,
    tmp_path: Path,
) -> None:
    directory = tmp_path / "versions"
    link = tmp_path / "bin" / "ruyi"
    state = version_manager.ActivationState(
        link,
        False,
        False,
        False,
        None,
        None,
    )
    calls: list[tuple[Path, Path]] = []

    def deactivate(
        actual_directory: Path,
        *,
        link: Path,
    ) -> version_manager.ActivationState:
        calls.append((actual_directory, link))
        return state

    monkeypatch.setattr(version_activation_child, "deactivate_version", deactivate)

    assert version_activation_child.main(["deactivate", str(directory), str(link)]) == 0

    assert calls == [(directory, link)]
    assert json.loads(capsys.readouterr().out) == {
        "target": None,
        "version": None,
        "backup_path": None,
    }


def test_privileged_workers_invoke_canonical_activation_child(
    monkeypatch,
    tmp_path: Path,
) -> None:
    binary = tmp_path / "ruyi-0.50.0"
    directory = tmp_path / "versions"
    link = tmp_path / "bin" / "ruyi"
    state = version_manager.ActivationState(
        link,
        True,
        True,
        True,
        binary,
        "0.50.0",
    )
    commands: list[list[str]] = []

    def run(command: list[str], **_kwargs) -> SimpleNamespace:
        commands.append(command)
        return SimpleNamespace(returncode=0, stdout='{"backup_path": null}', stderr="")

    monkeypatch.setattr(worker_services.subprocess, "run", run)
    monkeypatch.setattr(worker_services.platform, "system", lambda: "Linux")
    monkeypatch.setattr(
        worker_services.version_manager,
        "read_activation_state",
        lambda _link, _directory: state,
    )

    activation = worker_services.VersionActivationWorker(
        binary,
        directory,
        link,
        backup_unmanaged=False,
    )
    activation.password_requested.connect(
        lambda _message, response: response.__setitem__("password", "secret")
    )
    activation._activate_with_sudo()

    deactivation = worker_services.VersionDeactivationWorker(directory, link)
    deactivation.password_requested.connect(
        lambda _message, response: response.__setitem__("password", "secret")
    )
    deactivation._deactivate_with_sudo()

    assert [command[6] for command in commands] == [
        "oh_my_ruyi.processes.version_activation_child",
        "oh_my_ruyi.processes.version_activation_child",
    ]
