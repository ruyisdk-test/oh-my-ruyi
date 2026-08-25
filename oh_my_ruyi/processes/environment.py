"""Shared environment configuration for ruyi child processes."""

from __future__ import annotations

from PySide6.QtCore import QProcessEnvironment

from ..i18n import apply_qprocess_locale
from ..rich_output import RICH_TERMINAL_ENV


def configure_ruyi_qprocess_environment(
    environment: QProcessEnvironment,
    *,
    unbuffered: bool = False,
    telemetry_optout: bool = False,
) -> QProcessEnvironment:
    """Apply common locale, output, and opt-out settings in place.

    Callers still create the environment in their owning module. Keeping that
    lookup local preserves existing ``QProcessEnvironment`` monkeypatch seams;
    this function only centralizes the shared mutation policy.
    """

    apply_qprocess_locale(environment)
    environment.remove("NO_COLOR")
    if unbuffered:
        environment.insert("PYTHONUNBUFFERED", "1")
    if telemetry_optout:
        environment.insert("RUYI_TELEMETRY_OPTOUT", "1")
    for key, value in RICH_TERMINAL_ENV.items():
        environment.insert(key, value)
    return environment


__all__ = ["configure_ruyi_qprocess_environment"]
