"""Build the provisioning wizard shell around its page stack."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QStyle,
    QVBoxLayout,
    QWidget,
)


Callback = Callable[..., object]
BuildPages = Callable[[QStackedWidget], object]


@dataclass(slots=True)
class WizardShellWidgets:
    """Controls retained by the provisioning coordinator."""

    provision_tab: QWidget
    steps: QListWidget
    summary: QGroupBox
    summary_device: QLabel
    summary_variant: QLabel
    summary_combo: QLabel
    summary_packages: QLabel
    summary_storage: QLabel
    stack: QStackedWidget
    back_btn: QPushButton
    next_btn: QPushButton


def build_wizard_shell(
    *,
    step_titles: Sequence[str],
    style: QStyle,
    build_pages: BuildPages,
    on_step_clicked: Callback,
    on_back: Callback,
    on_next: Callback,
) -> WizardShellWidgets:
    """Construct the sidebar, summary, page stack, and navigation controls."""

    provision_tab = QWidget()
    root_layout = QHBoxLayout(provision_tab)
    root_layout.setContentsMargins(12, 12, 12, 12)
    root_layout.setSpacing(12)

    steps = QListWidget()
    steps.setFixedWidth(180)
    steps.setObjectName("stepList")
    steps.setAccessibleName("Provisioning steps")
    steps.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
    for index, title in enumerate(step_titles):
        item = QListWidgetItem(f"{index + 1}. {title}")
        item.setData(Qt.ItemDataRole.UserRole, index)
        item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
        steps.addItem(item)
    steps.currentRowChanged.connect(on_step_clicked)
    root_layout.addWidget(steps)

    right = QWidget()
    right_layout = QVBoxLayout(right)
    right_layout.setContentsMargins(0, 0, 0, 0)
    right_layout.setSpacing(10)
    root_layout.addWidget(right, 1)

    summary = QGroupBox("Selected options")
    summary_layout = QVBoxLayout(summary)
    summary_device = QLabel("Device: -")
    summary_variant = QLabel("Variant: -")
    summary_combo = QLabel("Image: -")
    summary_packages = QLabel("Packages: -")
    summary_storage = QLabel("Storage: -")
    for label in (
        summary_device,
        summary_variant,
        summary_combo,
        summary_packages,
        summary_storage,
    ):
        label.setWordWrap(True)
        summary_layout.addWidget(label)
    right_layout.addWidget(summary)

    stack = QStackedWidget()
    right_layout.addWidget(stack, 1)
    build_pages(stack)

    button_row = QHBoxLayout()
    button_row.addStretch()
    back_btn = QPushButton("Back")
    next_btn = QPushButton("Next")
    back_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowBack))
    next_btn.setIcon(style.standardIcon(QStyle.StandardPixmap.SP_ArrowForward))
    next_btn.setObjectName("primaryButton")
    back_btn.clicked.connect(on_back)
    next_btn.clicked.connect(on_next)
    button_row.addWidget(back_btn)
    button_row.addWidget(next_btn)
    right_layout.addLayout(button_row)

    return WizardShellWidgets(
        provision_tab=provision_tab,
        steps=steps,
        summary=summary,
        summary_device=summary_device,
        summary_variant=summary_variant,
        summary_combo=summary_combo,
        summary_packages=summary_packages,
        summary_storage=summary_storage,
        stack=stack,
        back_btn=back_btn,
        next_btn=next_btn,
    )


__all__ = ["WizardShellWidgets", "build_wizard_shell"]
