"""Contracts for the classified implementation package layout."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import pytest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = PROJECT_ROOT / "oh_my_ruyi"


@pytest.mark.parametrize(
    "module_name",
    (
        "oh_my_ruyi.gui.app",
        "oh_my_ruyi.gui.main_window",
        "oh_my_ruyi.gui.about_tab",
        "oh_my_ruyi.gui.first_use",
        "oh_my_ruyi.gui.repo_manager_tab",
        "oh_my_ruyi.services.host_storage",
        "oh_my_ruyi.services.repo_manager",
        "oh_my_ruyi.services.ruyi_facade",
        "oh_my_ruyi.services.version_manager",
        "oh_my_ruyi.runtime.i18n",
        "oh_my_ruyi.runtime.qt_logger",
        "oh_my_ruyi.runtime.rich_output",
        "oh_my_ruyi.runtime.worker_runtime",
        "oh_my_ruyi.runtime.worker_services",
        "oh_my_ruyi.runtime.workers",
    ),
)
def test_classified_module_imports(module_name: str) -> None:
    assert import_module(module_name).__name__ == module_name


def test_package_root_contains_only_package_entries() -> None:
    assert sorted(path.name for path in PACKAGE_ROOT.glob("*.py")) == [
        "__init__.py",
        "__main__.py",
    ]
