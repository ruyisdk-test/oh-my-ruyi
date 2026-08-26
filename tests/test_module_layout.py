"""Compatibility contracts for the classified implementation packages."""

from __future__ import annotations

from importlib import import_module

import pytest


_COMPATIBILITY_ALIASES = (
    ("oh_my_ruyi.app", "oh_my_ruyi.gui.app"),
    ("oh_my_ruyi.main_window", "oh_my_ruyi.gui.main_window"),
    ("oh_my_ruyi.about_tab", "oh_my_ruyi.gui.about_tab"),
    ("oh_my_ruyi.first_use", "oh_my_ruyi.gui.first_use"),
    ("oh_my_ruyi.repo_manager_tab", "oh_my_ruyi.gui.repo_manager_tab"),
    ("oh_my_ruyi.host_storage", "oh_my_ruyi.services.host_storage"),
    ("oh_my_ruyi.repo_manager", "oh_my_ruyi.services.repo_manager"),
    ("oh_my_ruyi.ruyi_facade", "oh_my_ruyi.services.ruyi_facade"),
    ("oh_my_ruyi.version_manager", "oh_my_ruyi.services.version_manager"),
    ("oh_my_ruyi.i18n", "oh_my_ruyi.runtime.i18n"),
    ("oh_my_ruyi.qt_logger", "oh_my_ruyi.runtime.qt_logger"),
    ("oh_my_ruyi.rich_output", "oh_my_ruyi.runtime.rich_output"),
    ("oh_my_ruyi.worker_runtime", "oh_my_ruyi.runtime.worker_runtime"),
    ("oh_my_ruyi.worker_services", "oh_my_ruyi.runtime.worker_services"),
    ("oh_my_ruyi.workers", "oh_my_ruyi.runtime.workers"),
)


@pytest.mark.parametrize(("legacy_name", "canonical_name"), _COMPATIBILITY_ALIASES)
def test_legacy_module_alias_preserves_identity(
    legacy_name: str, canonical_name: str
) -> None:
    """A monkeypatch through the old path must reach the moved module object."""
    assert import_module(legacy_name) is import_module(canonical_name)
