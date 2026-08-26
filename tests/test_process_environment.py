from __future__ import annotations

from PySide6.QtCore import QProcessEnvironment

from oh_my_ruyi.processes.environment import configure_ruyi_qprocess_environment
from oh_my_ruyi.runtime.rich_output import RICH_TERMINAL_ENV


def test_configure_ruyi_qprocess_environment_applies_shared_output_contract() -> None:
    environment = QProcessEnvironment()
    environment.insert("NO_COLOR", "1")

    configure_ruyi_qprocess_environment(
        environment,
        unbuffered=True,
        telemetry_optout=True,
    )

    assert environment.value("NO_COLOR") == ""
    assert environment.value("LANGUAGE")
    assert environment.value("PYTHONUNBUFFERED") == "1"
    assert environment.value("RUYI_TELEMETRY_OPTOUT") == "1"
    for key, value in RICH_TERMINAL_ENV.items():
        assert environment.value(key) == value


def test_configure_ruyi_qprocess_environment_keeps_optional_flags_opt_in() -> None:
    environment = QProcessEnvironment()

    configure_ruyi_qprocess_environment(environment)

    assert environment.value("PYTHONUNBUFFERED") == ""
    assert environment.value("RUYI_TELEMETRY_OPTOUT") == ""
    assert environment.value("FORCE_COLOR") == RICH_TERMINAL_ENV["FORCE_COLOR"]
