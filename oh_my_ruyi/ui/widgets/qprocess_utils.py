"""Shared QProcess environment and channel configuration.

Every child process that forwards ruyi output into the GUI needs the same
locale, Rich terminal, and buffering environment.  This helper keeps that
contract in one place so the GUI and child processes agree on language and
ANSI styling.
"""

from __future__ import annotations

from PySide6.QtCore import QProcess, QProcessEnvironment

from ...i18n import apply_qprocess_locale
from .rich_output import RICH_TERMINAL_ENV


def configure_qprocess_environment(process: QProcess) -> None:
    """Apply the shared GUI child-process environment and merged channels."""
    environment = QProcessEnvironment.systemEnvironment()
    apply_qprocess_locale(environment)
    environment.remove("NO_COLOR")
    environment.insert("PYTHONUNBUFFERED", "1")
    environment.insert("RUYI_TELEMETRY_OPTOUT", "1")
    for key, value in RICH_TERMINAL_ENV.items():
        environment.insert(key, value)
    process.setProcessEnvironment(environment)
    process.setProcessChannelMode(QProcess.ProcessChannelMode.MergedChannels)
