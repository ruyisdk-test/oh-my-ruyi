"""Shared helpers for the split main-window test modules."""

from __future__ import annotations

import platform
from PySide6.QtGui import QColor, QPalette
from PySide6.QtWidgets import QApplication
from ruyi.config import GlobalConfig
from ruyi.utils.global_mode import EnvGlobalModeProvider
from oh_my_ruyi.infra import version_manager
from oh_my_ruyi.ui.views import first_use
from oh_my_ruyi.ui.views.main_window import ProvisionMainWindow
from oh_my_ruyi.ui.widgets.qt_logger import LogEmitter, QtRuyiLogger


def _elf_header(machine: int, *, elf_class: int = 2) -> bytes:
    header = bytearray(64)
    header[:7] = b"\x7fELF" + bytes((elf_class, 1, 1))
    header[18:20] = machine.to_bytes(2, "little")
    return bytes(header)


def _macho_header(cpu_type: int) -> bytes:
    header = bytearray(64)
    header[:4] = b"\xcf\xfa\xed\xfe"
    header[4:8] = cpu_type.to_bytes(4, "little")
    return bytes(header)


def _binary_header_for_arch(architecture: str) -> bytes:
    normalized = version_manager.normalize_architecture(architecture) or architecture
    if normalized == "x86_64":
        return (
            _macho_header(0x01000007)
            if platform.system() == "Darwin"
            else _elf_header(62)
        )
    if normalized == "aarch64":
        return (
            _macho_header(0x0100000C)
            if platform.system() == "Darwin"
            else _elf_header(183)
        )
    if normalized == "riscv64":
        return _elf_header(243)
    return b"standalone ruyi"


def _host_binary_header() -> bytes:
    return _binary_header_for_arch(version_manager.host_architecture())


def _download_architecture_for_host() -> str:
    host = version_manager.host_architecture()
    if platform.system() == "Darwin" and host == "aarch64":
        return "macos-arm64"
    if host == "x86_64":
        return "amd64"
    return host


def _host_download_url(version: str) -> str:
    return (
        f"https://downloads.example/ruyi-{version}.{_download_architecture_for_host()}"
    )


def _first_use_window(qtbot, monkeypatch, tmp_path) -> ProvisionMainWindow:
    _app = QApplication.instance() or QApplication([])
    gm = EnvGlobalModeProvider({}, [])
    emitter = LogEmitter()
    logger = QtRuyiLogger(gm, emitter)
    config = GlobalConfig(gm, logger)
    data_dir = tmp_path / "share" / "oh-my-ruyi"
    repo_config = tmp_path / "config" / "ruyi" / "config.toml"
    repo_config.parent.mkdir(parents=True)
    monkeypatch.setattr(
        first_use,
        "should_offer_first_use_setup",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(ProvisionMainWindow, "_refresh_pm_catalog", lambda _self: None)
    result = ProvisionMainWindow(
        config,
        logger,
        emitter,
        versions_directory=data_dir / "versions",
        managed_data_directory=data_dir,
        activation_link=tmp_path / "bin" / "ruyi",
        telemetry_installation=tmp_path / "state" / "installation.json",
        system_ruyi_config=tmp_path / "etc" / "ruyi" / "config.toml",
        repo_config_path=repo_config,
    )
    qtbot.addWidget(result)
    qtbot.waitUntil(lambda: result._first_use_dialog is not None)
    return result


def _contrast_ratio(foreground: str, background: str) -> float:
    def luminance(color_name: str) -> float:
        color = QColor(color_name)
        channels = [color.redF(), color.greenF(), color.blueF()]
        linear = [
            channel / 12.92
            if channel <= 0.04045
            else ((channel + 0.055) / 1.055) ** 2.4
            for channel in channels
        ]
        return 0.2126 * linear[0] + 0.7152 * linear[1] + 0.0722 * linear[2]

    first = luminance(foreground)
    second = luminance(background)
    lighter, darker = max(first, second), min(first, second)
    return (lighter + 0.05) / (darker + 0.05)


def _test_palette(*, dark: bool) -> QPalette:
    palette = QPalette()
    values = (
        {
            QPalette.ColorRole.Window: "#202124",
            QPalette.ColorRole.WindowText: "#f1f3f4",
            QPalette.ColorRole.Base: "#121212",
            QPalette.ColorRole.Text: "#f1f3f4",
            QPalette.ColorRole.Button: "#303134",
            QPalette.ColorRole.ButtonText: "#f1f3f4",
            QPalette.ColorRole.Mid: "#5f6368",
            QPalette.ColorRole.Highlight: "#8ab4f8",
            QPalette.ColorRole.HighlightedText: "#202124",
        }
        if dark
        else {
            QPalette.ColorRole.Window: "#f8f9fa",
            QPalette.ColorRole.WindowText: "#202124",
            QPalette.ColorRole.Base: "#ffffff",
            QPalette.ColorRole.Text: "#202124",
            QPalette.ColorRole.Button: "#f1f3f4",
            QPalette.ColorRole.ButtonText: "#202124",
            QPalette.ColorRole.Mid: "#bdc1c6",
            QPalette.ColorRole.Highlight: "#1967d2",
            QPalette.ColorRole.HighlightedText: "#ffffff",
        }
    )
    for role, value in values.items():
        palette.setColor(role, QColor(value))
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Text,
        QColor("#9aa0a6" if dark else "#80868b"),
    )
    palette.setColor(
        QPalette.ColorGroup.Disabled,
        QPalette.ColorRole.Button,
        QColor("#3c4043" if dark else "#e8eaed"),
    )
    return palette
