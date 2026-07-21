"""First-use detection and the setup flow's step/status dialog."""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QVBoxLayout,
)

from .i18n import _, translate_widget_tree


SETUP_STEPS = (
    "Download a compatible ruyi",
    "Activate ruyi at /usr/local/bin/ruyi",
    "Choose and update the RuyiSDK mirror",
    "Review the completed setup",
)


def should_offer_first_use_setup(
    telemetry_installation: Path,
    managed_data_directory: Path,
    *,
    path: str | None = None,
    runtime_executable: Path | None = None,
    which: Callable[..., str | None] = shutil.which,
) -> bool:
    """Return whether all three first-use conditions are satisfied."""
    return (
        not Path(telemetry_installation).exists()
        and _find_external_ruyi(
            path=path,
            runtime_executable=runtime_executable,
            which=which,
        )
        is None
        and not Path(managed_data_directory).exists()
    )


def _find_external_ruyi(
    *,
    path: str | None,
    runtime_executable: Path | None,
    which: Callable[..., str | None],
) -> str | None:
    """Find ruyi outside the scripts directory of the running Python environment."""
    runtime_executable = (
        Path(sys.executable) if runtime_executable is None else Path(runtime_executable)
    )
    runtime_scripts = runtime_executable.parent.resolve(strict=False)
    search_path = os.environ.get("PATH", os.defpath) if path is None else path
    external_directories: list[str] = []
    for entry in search_path.split(os.pathsep):
        directory = Path(entry or os.curdir).expanduser().resolve(strict=False)
        if directory != runtime_scripts:
            external_directories.append(entry)
    if not external_directories:
        return None
    return which("ruyi", path=os.pathsep.join(external_directories))


class FirstUseDialog(QDialog):
    """Show setup steps and status while the main window owns operations."""

    action_requested = Signal()
    exit_requested = Signal()
    skip_requested = Signal()

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle(_("First-use setup"))
        self.setModal(False)
        self.setMinimumWidth(560)
        self._step = 0

        layout = QVBoxLayout(self)
        introduction = QLabel(
            _(
                "Set up a compatible ruyi command and choose the metadata mirror used by "
                "RuyiSDK. You can exit this setup at any time."
            )
        )
        introduction.setWordWrap(True)
        layout.addWidget(introduction)

        self.current_label = QLabel()
        self.current_label.setObjectName("setupCurrentStep")
        self.remaining_label = QLabel()
        layout.addWidget(self.current_label)
        layout.addWidget(self.remaining_label)

        self.steps = QListWidget()
        self.steps.setAccessibleName(_("First-use setup steps"))
        self.steps.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for index, title in enumerate(SETUP_STEPS, start=1):
            item = QListWidgetItem(_("{number}. {step}", number=index, step=_(title)))
            item.setFlags(Qt.ItemFlag.ItemIsEnabled)
            self.steps.addItem(item)
        layout.addWidget(self.steps)

        self.status = QLabel()
        self.status.setObjectName("setupStatus")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        buttons = QHBoxLayout()
        buttons.addStretch()
        self.exit_button = QPushButton("Exit setup")
        self.skip_button = QPushButton()
        self.action_button = QPushButton()
        self.action_button.setObjectName("primaryButton")
        self.exit_button.clicked.connect(lambda _checked=False: self.reject())
        self.skip_button.clicked.connect(
            lambda _checked=False: self.skip_requested.emit()
        )
        self.action_button.clicked.connect(
            lambda _checked=False: self.action_requested.emit()
        )
        buttons.addWidget(self.exit_button)
        buttons.addWidget(self.skip_button)
        buttons.addWidget(self.action_button)
        layout.addLayout(buttons)

        translate_widget_tree(self)
        self.set_stage(
            0,
            _("Checking for compatible ruyi releases..."),
            busy=True,
        )

    @property
    def step(self) -> int:
        return self._step

    def set_stage(
        self,
        step: int,
        status: str,
        *,
        action: str | None = None,
        skip: str | None = None,
        busy: bool = False,
        kind: str | None = None,
    ) -> None:
        if not 0 <= step < len(SETUP_STEPS):
            raise ValueError(f"invalid first-use setup step: {step}")
        self._step = step
        current = _(SETUP_STEPS[step])
        self.current_label.setText(_("Current step: {step}", step=current))
        self.remaining_label.setText(
            _("Remaining steps: {count}", count=len(SETUP_STEPS) - step - 1)
        )
        for index in range(self.steps.count()):
            font = self.steps.item(index).font()
            font.setBold(index == step)
            self.steps.item(index).setFont(font)
        self.status.setText(_(status))
        self.status.setProperty("statusKind", kind or "")
        self.status.style().unpolish(self.status)
        self.status.style().polish(self.status)
        self.action_button.setVisible(action is not None)
        self.action_button.setEnabled(action is not None and not busy)
        if action is not None:
            self.action_button.setText(_(action))
        self.skip_button.setVisible(skip is not None)
        self.skip_button.setEnabled(skip is not None and not busy)
        if skip is not None:
            self.skip_button.setText(_(skip))

    def reject(self) -> None:  # noqa: D401 - Qt override
        self.exit_requested.emit()
        super().reject()


__all__ = ["FirstUseDialog", "SETUP_STEPS", "should_offer_first_use_setup"]
