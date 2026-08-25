"""Read-only application and ruyi runtime information."""

from __future__ import annotations

import datetime as dt
import json
import os
import sys
import time
from pathlib import Path

from PySide6.QtCore import QProcess, QTimer, Qt
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

from ruyi.telemetry.provider import next_utc_weekday

from ... import __version__
from ...infra import version_manager
from ...i18n import (
    _,
    translate_widget_tree,
)
from ..widgets.qprocess_utils import configure_qprocess_environment
from ..widgets.rich_output import RichTextView


def application_version() -> str:
    return __version__


def telemetry_summary(config, now: float | None = None) -> tuple[str, str]:
    mode = config.telemetry_mode
    if mode == "off":
        return _("Off"), _("No periodic upload is scheduled.")
    if mode == "local":
        return _("Local only"), _("No periodic upload is scheduled.")
    now = time.time() if now is None else now
    try:
        installation = Path(config.state_root) / "telemetry" / "installation.json"
        data = json.loads(installation.read_text(encoding="utf-8"))
        report_uuid = data["report_uuid"]
        if not isinstance(report_uuid, str) or len(report_uuid) < 8:
            raise ValueError("invalid report UUID")
        upload_day = next_utc_weekday(int(report_uuid[:8], 16) % 7, now)
    except (OSError, KeyError, TypeError, ValueError, json.JSONDecodeError):
        return _("On"), _("Next upload window is unavailable.")
    upload_window_end = upload_day + 86400
    last_upload = None
    try:
        last_upload = (
            (Path(config.state_root) / "telemetry" / ".stamp-last-upload")
            .stat()
            .st_mtime
        )
    except OSError:
        pass
    if upload_day <= now < upload_window_end and not (
        last_upload is not None and upload_day <= last_upload < upload_window_end
    ):
        pass
    elif upload_day <= now:
        upload_day += 7 * 86400
    start = dt.datetime.fromtimestamp(upload_day, dt.UTC).astimezone()
    end = start + dt.timedelta(days=1)
    return _("On"), _(
        "Next upload window: {window}.",
        window=f"{start:%Y-%m-%d %H:%M %Z} - {end:%H:%M %Z}",
    )


class AboutTab(QWidget):
    """Display application, ruyi, PATH, and telemetry information."""

    def __init__(
        self, config, *, activation_link: Path, versions_directory: Path, parent=None
    ):
        super().__init__(parent)
        self._config = config
        self._activation_link = Path(activation_link)
        self._versions_directory = Path(versions_directory)
        self._path_process: QProcess | None = None
        self._path_probe_started = False
        self._path_probe_timer = QTimer(self)
        self._path_probe_timer.setSingleShot(True)
        self._path_probe_timer.setInterval(10_000)
        self._path_probe_timer.timeout.connect(self._on_path_probe_timeout)
        self._bundled_process: QProcess | None = None
        self._bundled_probe_timer = QTimer(self)
        self._bundled_probe_timer.setSingleShot(True)
        self._bundled_probe_timer.setInterval(10_000)
        self._bundled_probe_timer.timeout.connect(self._on_bundled_probe_timeout)
        self._build_ui()
        translate_widget_tree(self)
        self._load_info()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self.stop_path_probe()
        self.stop_bundled_probe()
        super().closeEvent(event)

    def stop_path_probe(self) -> None:
        self._path_probe_timer.stop()
        self._path_probe_started = False
        process = self._path_process
        if process is None:
            return
        self._path_process = None
        process.kill()

    def stop_bundled_probe(self) -> None:
        self._bundled_probe_timer.stop()
        process = self._bundled_process
        if process is None:
            return
        self._bundled_process = None
        process.kill()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(16, 16, 16, 16)
        root.setSpacing(12)
        title = QLabel("<b>About Oh My Ruyi</b>")
        title.setObjectName("pageTitle")
        self._title = title
        root.addWidget(title)
        self._version_label = QLabel()
        root.addWidget(self._version_label)
        intro = QLabel(
            "Oh My Ruyi is a graphical frontend for managing ruyi package manager "
            "versions, repositories, and device provisioning."
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        versions_box = QGroupBox("Ruyi versions")
        versions_layout = QHBoxLayout(versions_box)
        versions_layout.setSpacing(12)
        self.bundled_version = self._make_version_view()
        self.path_version = self._make_version_view()
        versions_layout.addWidget(
            self._version_group("Bundled ruyi", self.bundled_version)
        )
        versions_layout.addWidget(
            self._version_group("PATH default ruyi", self.path_version)
        )
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
        self.telemetry_mode = QLabel()
        self.telemetry_schedule = QLabel()
        for label in (self.telemetry_mode, self.telemetry_schedule):
            label.setAlignment(Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop)
            label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
            label.setWordWrap(False)
        telemetry_form.addRow("Current status", self.telemetry_mode)
        telemetry_form.addRow("Next upload", self.telemetry_schedule)
        root.addWidget(telemetry_box)
        root.addStretch()

    @staticmethod
    def _make_version_view() -> RichTextView:
        view = RichTextView()
        view.setFrameShape(QFrame.Shape.NoFrame)
        view.setMinimumHeight(150)
        return view

    @staticmethod
    def _version_group(title: str, view: RichTextView) -> QWidget:
        box = QWidget()
        layout = QVBoxLayout(box)
        layout.setContentsMargins(0, 0, 0, 0)
        label = QLabel(f"<b>{title}</b>")
        layout.addWidget(label)
        layout.addWidget(view)
        return box

    def _load_info(self) -> None:
        self._version_label.setText(
            _("Version {version}", version=application_version())
        )
        self._start_bundled_probe()
        mode, schedule = telemetry_summary(self._config)
        self.telemetry_mode.setText(mode)
        self.telemetry_schedule.setText(schedule)
        self.path_version.setPlainText(_("Switch to this tab to inspect PATH ruyi."))

    def refresh(self, config=None) -> None:
        if config is not None:
            self._config = config
        mode, schedule = telemetry_summary(self._config)
        self.telemetry_mode.setText(mode)
        self.telemetry_schedule.setText(schedule)
        self.stop_path_probe()
        self.start_path_probe()

    def start_path_probe(self) -> None:
        if self._path_probe_started or self._path_process is not None:
            return
        self._path_probe_started = True
        path_state = version_manager.read_path_state(
            self._versions_directory,
            link=self._activation_link,
        )
        if path_state.command is None:
            self.path_version.setPlainText(
                _("No executable named ruyi was found on PATH.")
            )
            return
        # The process is parented to this widget, so it is destroyed together
        # with the About tab.  Never call deleteLater() on it from a signal
        # handler: a nested event loop can destroy the QProcess before Qt
        # finishes emitting the signal, which segfaults.
        process = QProcess(self)
        self._path_process = process
        process.setProgram(os.fspath(path_state.command))
        process.setArguments(["version"])
        configure_qprocess_environment(process)
        process.finished.connect(
            lambda code, status, p=process: self._on_path_probe_finished(
                p, code, status
            )
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_path_probe_error(p, error)
        )
        process.start()
        self._path_probe_timer.start()

    def _on_path_probe_finished(self, process: QProcess, code: int, _status) -> None:
        if process != self._path_process:
            return
        self._path_probe_timer.stop()
        output = bytes(process.readAllStandardOutput()).decode(errors="replace").strip()
        self._path_process = None
        self.path_version.set_ansi(
            output or _("PATH ruyi exited with code {code}.", code=code)
        )

    def _on_path_probe_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process != self._path_process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._on_path_probe_finished(process, 1, error)

    def _on_path_probe_timeout(self) -> None:
        process = self._path_process
        if process is None:
            return
        self._path_process = None
        process.kill()
        self.path_version.setPlainText(_("PATH ruyi version probe timed out."))

    def _start_bundled_probe(self) -> None:
        if self._bundled_process is not None:
            return
        self.bundled_version.setPlainText(_("Checking bundled ruyi version..."))
        # The process is parented to this widget, so it is destroyed together
        # with the About tab.  Never call deleteLater() on it from a signal
        # handler: a nested event loop can destroy the QProcess before Qt
        # finishes emitting the signal, which segfaults.
        process = QProcess(self)
        self._bundled_process = process
        process.setProgram(sys.executable)
        process.setArguments(["-m", "ruyi", "version"])
        configure_qprocess_environment(process)
        process.finished.connect(
            lambda code, status, p=process: self._on_bundled_probe_finished(
                p, code, status
            )
        )
        process.errorOccurred.connect(
            lambda error, p=process: self._on_bundled_probe_error(p, error)
        )
        process.start()
        self._bundled_probe_timer.start()

    def _on_bundled_probe_finished(self, process: QProcess, code: int, _status) -> None:
        if process != self._bundled_process:
            return
        self._bundled_probe_timer.stop()
        output = bytes(process.readAllStandardOutput()).decode(errors="replace").strip()
        self._bundled_process = None
        self.bundled_version.set_ansi(
            output or _("Bundled ruyi exited with code {code}.", code=code)
        )

    def _on_bundled_probe_error(
        self, process: QProcess, error: QProcess.ProcessError
    ) -> None:
        if process != self._bundled_process:
            return
        if error == QProcess.ProcessError.FailedToStart:
            self._on_bundled_probe_finished(process, 1, error)

    def _on_bundled_probe_timeout(self) -> None:
        process = self._bundled_process
        if process is None:
            return
        self._bundled_process = None
        process.kill()
        self.bundled_version.setPlainText(_("Bundled ruyi version probe timed out."))


__all__ = ["AboutTab", "application_version", "telemetry_summary"]
