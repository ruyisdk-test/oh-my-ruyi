from __future__ import annotations

import pathlib
import runpy
import tomllib
from types import SimpleNamespace


PROJECT_ROOT = pathlib.Path(__file__).resolve().parents[1]


def test_ruyi_dependency_uses_registry_source() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    dependencies = pyproject["project"]["dependencies"]
    assert "rich>=13.3.1" in dependencies
    assert "ruyi>=0.52.0a20260714,<0.53" in dependencies
    assert "ruyi" not in pyproject.get("tool", {}).get("uv", {}).get("sources", {})

    lock = tomllib.loads((PROJECT_ROOT / "uv.lock").read_text())
    ruyi = next(package for package in lock["package"] if package["name"] == "ruyi")
    assert ruyi["source"] == {"registry": "https://pypi.org/simple"}


def test_project_identity_uses_oh_my_ruyi() -> None:
    pyproject = tomllib.loads((PROJECT_ROOT / "pyproject.toml").read_text())
    assert pyproject["project"]["name"] == "oh-my-ruyi"
    assert pyproject["project"]["scripts"] == {"oh-my-ruyi": "oh_my_ruyi.__main__:main"}
    assert pyproject["tool"]["hatch"]["build"]["targets"]["wheel"]["packages"] == [
        "oh_my_ruyi"
    ]


def test_lock_file_has_no_machine_local_ruyi_path() -> None:
    lock_text = (PROJECT_ROOT / "uv.lock").read_text()
    assert "../ruyi" not in lock_text
    assert "/home/" not in lock_text


def test_frozen_entrypoint_dispatches_embedded_child_module(monkeypatch) -> None:
    from oh_my_ruyi import __main__ as entrypoint

    calls: list[list[str]] = []
    module = SimpleNamespace(main=lambda argv: calls.append(argv) or 7)
    monkeypatch.setattr(entrypoint.importlib, "import_module", lambda _name: module)

    result = entrypoint._run_embedded_command(
        ["oh-my-ruyi", "-m", "oh_my_ruyi.processes.download_child", "pkg/test"]
    )

    assert result == 7
    assert calls == [["pkg/test"]]


def test_frozen_entrypoint_dispatches_ruyi_with_cli_argv0(monkeypatch) -> None:
    from oh_my_ruyi import __main__ as entrypoint

    calls: list[list[str]] = []

    def ruyi_entrypoint() -> None:
        calls.append(list(entrypoint.sys.argv))

    module = SimpleNamespace(entrypoint=ruyi_entrypoint)
    monkeypatch.setattr(entrypoint.importlib, "import_module", lambda _name: module)

    result = entrypoint._run_embedded_command(["oh-my-ruyi", "-m", "ruyi", "version"])

    assert result == 0
    assert calls == [["ruyi", "version"]]


def test_pyinstaller_spec_collects_dynamic_children_and_cffi() -> None:
    spec = (PROJECT_ROOT / "oh-my-ruyi.spec").read_text()

    assert "collect_submodules('oh_my_ruyi.processes')" in spec
    assert "'_cffi_backend'" in spec
    assert "collect_all('ruyi')" in spec


def test_script_entrypoint_can_run_without_relative_imports(monkeypatch) -> None:
    called_with: list[list[str]] = []
    monkeypatch.setattr(
        "oh_my_ruyi.app.run",
        lambda argv: called_with.append(argv) or 19,
    )

    namespace = runpy.run_path(
        PROJECT_ROOT / "oh_my_ruyi" / "__main__.py",
        run_name="pyinstaller_entrypoint_probe",
    )

    assert namespace["main"](["oh-my-ruyi"]) == 19
    assert called_with == [["oh-my-ruyi"]]
