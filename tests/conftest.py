"""Global test configuration.

Force a deterministic locale and Qt platform before any
``oh_my_ruyi`` import runs.  Locale selection in ``oh_my_ruyi.i18n`` is
process-wide and initialized lazily, so pinning the environment here keeps the
suite independent of the host locale.  Locale-specific behavior is exercised in
``tests/test_i18n.py`` through isolated subprocesses.
"""

from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
os.environ["LANGUAGE"] = "C"
os.environ["LANG"] = "C"
os.environ["LC_ALL"] = "C"
os.environ["LC_MESSAGES"] = "C"


from oh_my_ruyi.ui.views.about_tab import AboutTab
from oh_my_ruyi.ui.views.main_window import ProvisionMainWindow
from oh_my_ruyi.ui.widgets.qt_logger import LogEmitter, QtRuyiLogger
from ruyi.config import GlobalConfig
from ruyi.utils.global_mode import EnvGlobalModeProvider
from PySide6.QtWidgets import QApplication
import pytest


@pytest.fixture(autouse=True)
def _disable_bundled_probe(monkeypatch, request) -> None:
    if request.module.__name__ == "tests.test_about_tab":
        return
    monkeypatch.setattr(AboutTab, "_start_bundled_probe", lambda self: None)


@pytest.fixture
def window(qtbot, tmp_path) -> ProvisionMainWindow:
    _app = QApplication.instance() or QApplication([])
    gm = EnvGlobalModeProvider({}, [])
    emitter = LogEmitter()
    logger = QtRuyiLogger(gm, emitter)
    config = GlobalConfig(gm, logger)
    telemetry_installation = tmp_path / "state" / "installation.json"
    telemetry_installation.parent.mkdir(parents=True)
    telemetry_installation.write_text("{}")
    repo_config = tmp_path / "config" / "ruyi" / "config.toml"
    repo_config.parent.mkdir(parents=True)
    repo_config.write_text("[repo]\ndisabled = true\n")
    result = ProvisionMainWindow(
        config,
        logger,
        emitter,
        auto_start=False,
        versions_directory=tmp_path / "versions",
        activation_link=tmp_path / "bin" / "ruyi",
        telemetry_installation=telemetry_installation,
        system_ruyi_config=tmp_path / "etc" / "ruyi" / "config.toml",
        repo_config_path=repo_config,
    )
    qtbot.addWidget(result)
    return result
