"""Main window core wiring."""

from __future__ import annotations

from oh_my_ruyi.core.state_machine import ProvisionStateMachine
from PySide6.QtWidgets import QApplication
from ruyi.config import GlobalConfig
from ruyi.utils.global_mode import EnvGlobalModeProvider
from oh_my_ruyi.infra import ruyi_adapter
from oh_my_ruyi.ui.views.main_window import ProvisionMainWindow
from oh_my_ruyi.ui.widgets.qt_logger import LogEmitter, QtRuyiLogger


def test_feature_tabs_are_in_required_order(window: ProvisionMainWindow) -> None:
    assert [window._tabs.tabText(i) for i in range(window._tabs.count())] == [
        "Version Management",
        "Repo Management",
        "Device Provision",
        "About",
    ]
    assert window._tabs.currentIndex() == 0
    assert window._tabs.widget(2) is window._provision_tab
    assert window._tabs.widget(3) is window._about_tab
    assert window._repo_manager_tab.layout() is not None
    assert window._repo_manager_tab.preset_table.rowCount() == 1
    assert window._repo_manager_tab.configured_table.rowCount() == 1
    assert window._stack.widget(
        ProvisionStateMachine.STEP_WELCOME
    ).accessibleName() == ("RuyiSDK Device Provisioning")


def test_repo_init_disables_repo_management(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    monkeypatch.setattr(
        "oh_my_ruyi.workers.worker_manager.WorkerTaskRunner.run_worker",
        lambda self, worker, *args, **kwargs: worker,
    )
    window._repo_manager_tab.preset_table.selectRow(0)
    assert window._repo_manager_tab.add_button.isEnabled()

    window._start_repo_init()

    assert window._worker is not None
    assert window._repo_manager_tab._external_busy
    assert not window._repo_manager_tab.preset_table.isEnabled()

    window._worker = None


def test_disabled_default_repo_stays_on_ready_page(
    qtbot,
    monkeypatch,
    tmp_path,
) -> None:
    _app = QApplication.instance() or QApplication([])
    gm = EnvGlobalModeProvider({}, [])
    emitter = LogEmitter()
    logger = QtRuyiLogger(gm, emitter)
    config = GlobalConfig(gm, logger)
    repo_config = tmp_path / "config" / "ruyi" / "config.toml"
    repo_config.parent.mkdir(parents=True)
    repo_config.write_text("[repo]\ndisabled = true\n")
    monkeypatch.setattr(ProvisionMainWindow, "_refresh_pm_catalog", lambda _self: None)

    window = ProvisionMainWindow(
        config,
        logger,
        emitter,
        versions_directory=tmp_path / "versions",
        activation_link=tmp_path / "bin" / "ruyi",
        telemetry_installation=tmp_path / "installation.json",
        system_ruyi_config=tmp_path / "etc" / "ruyi" / "config.toml",
        repo_config_path=repo_config,
    )
    qtbot.addWidget(window)
    window._tabs.setCurrentWidget(window._provision_tab)

    assert window._worker is None
    assert window._machine.current_step == ProvisionStateMachine.STEP_WELCOME
    assert window._welcome_status.text() == (
        "Enable the ruyisdk repository in Repo Management to load device metadata."
    )
    assert window._welcome_status.property("statusKind") == "warning"


def test_empty_device_repo_uses_detail_view_not_status_label(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    window.state.mr = object()  # type: ignore[assignment]
    monkeypatch.setattr(ruyi_adapter, "list_devices", lambda _mr: [])
    monkeypatch.setattr(ruyi_adapter, "list_entity_types", lambda _mr: ["package"])

    window._populate_devices()

    assert window._device_status.text() == (
        "No device provisioning data is available. See repository details."
    )
    assert "Available entity types: package" not in window._device_status.text()
    assert "Available entity types: package" in window._device_details.toPlainText()


def test_provision_update_waits_for_device_tab_switch(
    window: ProvisionMainWindow,
    monkeypatch,
) -> None:
    calls: list[None] = []
    monkeypatch.setattr(
        window._repo_manager_tab,
        "start_provision_update",
        lambda: calls.append(None),
    )

    assert calls == []
    window._tabs.setCurrentWidget(window._repo_manager_tab)
    assert calls == []
    window._tabs.setCurrentWidget(window._provision_tab)
    assert len(calls) == 1
