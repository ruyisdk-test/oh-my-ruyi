"""Build the read-only About page."""

from __future__ import annotations

from dataclasses import dataclass

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QFrame,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QSizePolicy,
    QVBoxLayout,
    QWidget,
)

from ..runtime.rich_output import RichTextView


@dataclass(slots=True)
class AboutWidgets:
    """Controls populated by the About tab's runtime queries."""

    title: QLabel
    version_label: QLabel
    bundled_version: RichTextView
    path_version: RichTextView
    telemetry_mode: QLabel
    telemetry_schedule: QLabel


def make_version_view() -> RichTextView:
    view = RichTextView()
    view.setFrameShape(QFrame.Shape.NoFrame)
    view.setMinimumHeight(150)
    return view


def version_group(title: str, view: RichTextView) -> QWidget:
    box = QWidget()
    layout = QVBoxLayout(box)
    layout.setContentsMargins(0, 0, 0, 0)
    label = QLabel(f"<b>{title}</b>")
    layout.addWidget(label)
    layout.addWidget(view)
    return box


def build_about_page(parent: QWidget) -> AboutWidgets:
    """Construct the About page without starting any runtime probes."""

    root = QVBoxLayout(parent)
    root.setContentsMargins(16, 16, 16, 16)
    root.setSpacing(12)
    title = QLabel("<b>About Oh My Ruyi</b>")
    title.setObjectName("pageTitle")
    root.addWidget(title)
    version_label = QLabel()
    root.addWidget(version_label)
    intro = QLabel(
        "Oh My Ruyi is a graphical frontend for managing ruyi package manager "
        "versions, repositories, and device provisioning."
    )
    intro.setWordWrap(True)
    root.addWidget(intro)

    versions_box = QGroupBox("Ruyi versions")
    versions_layout = QHBoxLayout(versions_box)
    versions_layout.setSpacing(12)
    bundled_version = make_version_view()
    path_version = make_version_view()
    versions_layout.addWidget(version_group("Bundled ruyi", bundled_version))
    versions_layout.addWidget(version_group("PATH default ruyi", path_version))
    root.addWidget(versions_box)

    telemetry_box = QGroupBox("Telemetry")
    telemetry_form = QFormLayout(telemetry_box)
    telemetry_form.setFieldGrowthPolicy(
        QFormLayout.FieldGrowthPolicy.AllNonFixedFieldsGrow
    )
    telemetry_form.setFormAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    telemetry_form.setLabelAlignment(
        Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop
    )
    telemetry_mode = QLabel()
    telemetry_schedule = QLabel()
    for label in (telemetry_mode, telemetry_schedule):
        label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
        label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        label.setWordWrap(False)
    telemetry_form.addRow("Current status", telemetry_mode)
    telemetry_form.addRow("Next upload", telemetry_schedule)
    root.addWidget(telemetry_box)
    root.addStretch()

    return AboutWidgets(
        title=title,
        version_label=version_label,
        bundled_version=bundled_version,
        path_version=path_version,
        telemetry_mode=telemetry_mode,
        telemetry_schedule=telemetry_schedule,
    )


__all__ = ["AboutWidgets", "build_about_page", "make_version_view", "version_group"]
