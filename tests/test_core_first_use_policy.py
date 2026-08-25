"""Tests for the Qt-free first-use eligibility policy."""

from __future__ import annotations

import os
from pathlib import Path

from oh_my_ruyi.core.first_use_policy import should_offer_first_use_setup


def test_policy_ignores_the_running_environment_but_finds_external_ruyi(
    tmp_path: Path,
) -> None:
    runtime_dir = tmp_path / "runtime" / "bin"
    external_dir = tmp_path / "external" / "bin"
    runtime_dir.mkdir(parents=True)
    external_dir.mkdir(parents=True)
    calls: list[tuple[str, str | None]] = []

    def fake_which(name: str, *, path: str | None = None) -> str | None:
        calls.append((name, path))
        return os.fspath(external_dir / name)

    path = os.pathsep.join((os.fspath(runtime_dir), os.fspath(external_dir)))
    assert not should_offer_first_use_setup(
        tmp_path / "telemetry.json",
        tmp_path / "managed",
        path=path,
        runtime_executable=runtime_dir / "python",
        which=fake_which,
    )
    assert calls == [("ruyi", os.fspath(external_dir))]


def test_policy_requires_absent_telemetry_and_managed_data(tmp_path: Path) -> None:
    runtime_dir = tmp_path / "runtime"
    runtime_dir.mkdir()
    telemetry = tmp_path / "telemetry.json"
    managed = tmp_path / "managed"

    def no_external_ruyi(_name: str, *, path: str | None = None) -> None:
        return None

    kwargs = {
        "path": os.fspath(runtime_dir),
        "runtime_executable": runtime_dir / "python",
        "which": no_external_ruyi,
    }
    assert should_offer_first_use_setup(telemetry, managed, **kwargs)

    telemetry.touch()
    assert not should_offer_first_use_setup(telemetry, managed, **kwargs)

    telemetry.unlink()
    managed.mkdir()
    assert not should_offer_first_use_setup(telemetry, managed, **kwargs)
