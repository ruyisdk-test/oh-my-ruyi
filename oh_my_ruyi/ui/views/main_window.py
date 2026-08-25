"""Single-window provisioning frontend.

The original CLI is a linear wizard, but a GUI is easier to inspect when the
whole flow is visible at once. This window keeps a step list on the left and a
stable right-hand work area: a summary of choices made so far, followed by the
controls for the current step.
"""

from __future__ import annotations

from __future__ import annotations
from pathlib import Path
from typing import Callable
from PySide6.QtCore import (
    QEvent,
    QProcess,
    QTimer,
    Qt,
)
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QMessageBox,
    QPushButton,
    QStackedWidget,
    QStyle,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from . import first_use
from ...infra import (
    repo_manager,
    version_manager,
)
from .about_tab import AboutTab
from .first_use import FirstUseDialog
from ...i18n import _, translate_widget_tree
from ..widgets.qt_logger import LogEmitter, QtRuyiLogger
from .repo_manager_tab import RepoManagementTab
from ..widgets.rich_output import (
    RichTextView,
)
from ..styles.styles import build_stylesheet, resolve_theme_colors
from ...controllers import ProvisionController, RepoController
from .version_dialogs import (
    VersionDownloadDialog as _VersionDownloadDialog,
)
from ...workers import (
    FlashWorker,
)
from ._common import _message_box
from ._first_use_mixin import FirstUseMixin
from ._provision_wizard_mixin import ProvisionWizardMixin
from ._version_management_mixin import VersionManagementMixin


class ProvisionMainWindow(
    ProvisionWizardMixin, VersionManagementMixin, FirstUseMixin, QMainWindow
):
    """One-screen GUI for the device provisioning flow."""

    STEP_TITLES = [
        "Ready",
        "Device",
        "Variant",
        "Image",
        "Versions",
        "Packages",
        "Download",
        "Storage",
        "Review",
        "Flash",
        "Done",
    ]

    def __init__(
        self,
        config,
        logger: QtRuyiLogger,
        emitter: LogEmitter,
        *,
        auto_start: bool = True,
        versions_directory: Path | None = None,
        managed_data_directory: Path | None = None,
        activation_link: Path | None = None,
        telemetry_installation: Path | None = None,
        system_ruyi_config: Path | None = None,
        repo_config_path: Path | None = None,
        config_loader: Callable[[], object] | None = None,
        parent=None,
    ) -> None:
        super().__init__(parent)
        self.setWindowTitle("Ohh My Ruyi")
        self.resize(1060, 720)

        self.provision_controller = ProvisionController(config, emitter, self)
        self.repo_controller = RepoController(self)
        self.state = self.provision_controller.state
        self._machine = self.provision_controller.machine
        self.provision_controller.step_changed.connect(self._on_machine_step_changed)
        self.provision_controller.busy_changed.connect(
            lambda _busy: self._refresh_buttons()
        )
        self.provision_controller.download_output.connect(self._on_download_output_data)
        self.provision_controller.download_finished.connect(
            self._on_download_finished_controller
        )
        self._logger = logger
        from ...workers.workers import _BaseWorker

        self._worker: _BaseWorker | None = None
        from ...workers.worker_manager import WorkerTaskRunner

        self._runner = WorkerTaskRunner(self)
        self._download_process: QProcess | None = None
        self._fastboot_process: QProcess | None = None
        self._fastboot_output = bytearray()
        self._fastboot_timed_out = False
        self._fastboot_timer = QTimer(self)
        self._fastboot_timer.setSingleShot(True)
        self._fastboot_timer.setInterval(10_000)
        self._fastboot_timer.timeout.connect(self._on_fastboot_timeout)
        self._download_cancelled = False
        self._flash_cancel_requested = False
        self._applying_styles = False
        self._pm_versions_directory = (
            version_manager.versions_dir()
            if versions_directory is None
            else Path(versions_directory)
        )
        self._pm_activation_link = (
            version_manager.DEFAULT_ACTIVATION_LINK
            if activation_link is None
            else Path(activation_link)
        )
        self._pm_telemetry_installation = (
            version_manager.telemetry_installation_path()
            if telemetry_installation is None
            else Path(telemetry_installation)
        )
        self._pm_system_config = (
            version_manager.DEFAULT_SYSTEM_CONFIG
            if system_ruyi_config is None
            else Path(system_ruyi_config)
        )
        self._config_loader = config_loader
        self._repo_config_path = (
            repo_manager.user_config_path()
            if repo_config_path is None
            else Path(repo_config_path)
        )
        self._pm_config_externally_managed = bool(
            getattr(config, "is_installation_externally_managed", False)
        )
        self._pm_externally_managed = self._pm_config_externally_managed or (
            version_manager.is_ruyi_externally_managed(self._pm_system_config)
        )
        self._pm_catalog_releases: list[version_manager.RuyiRelease] = []
        self._pm_custom_releases: list[version_manager.RuyiRelease] = []
        self._pm_worker: _BaseWorker | None = None
        self._pm_runner = WorkerTaskRunner(self)
        self._pm_operation = ""
        self._pm_download_dialog: _VersionDownloadDialog | None = None
        self._pm_error_output = ""
        if managed_data_directory is not None:
            self._first_use_data_directory = Path(managed_data_directory)
        elif versions_directory is not None:
            self._first_use_data_directory = self._pm_versions_directory.parent
        else:
            self._first_use_data_directory = version_manager.managed_data_dir()
        self._first_use_active = auto_start and first_use.should_offer_first_use_setup(
            self._pm_telemetry_installation,
            self._first_use_data_directory,
        )
        self._first_use_dialog: FirstUseDialog | None = None
        self._first_use_release: version_manager.RuyiRelease | None = None
        self._first_use_binary: Path | None = None
        self._first_use_action = ""
        self._first_use_operation = ""
        self._first_use_catalog_error: str | None = None
        self._first_use_catalog_pending = self._first_use_active
        self._first_use_activated = False
        self._pm_first_run_check_pending = auto_start and not self._first_use_active

        from typing import Any

        self._device_choices: dict[str, Any] = {}
        self._variant_choices: dict[str, Any] = {}
        self._combo_choices: dict[str, Any] = {}
        self._version_combos: list[QComboBox] = []
        self._storage_inputs: dict[str, QComboBox] = {}
        self._storage_mount_warnings: dict[str, QLabel] = {}
        self._storage_mount_confirmations: dict[str, QCheckBox] = {}
        self._storage_discovery_paths: dict[str, str] = {}

        self._build_ui()
        translate_widget_tree(self)
        self._connect_logs()
        self._set_step(self._machine.STEP_WELCOME)
        if self._first_use_active:
            QTimer.singleShot(0, self._open_first_use_setup)
        if auto_start:
            self._refresh_pm_catalog()

    def closeEvent(self, event) -> None:  # noqa: N802 - Qt override
        self._stop_fastboot_check()
        if hasattr(self, "_about_tab"):
            self._about_tab.stop_path_probe()
        if self._download_process is not None:
            ret = _message_box(
                QMessageBox.question,
                self,
                "Cancel download?",
                "A download or package installation is still running. Cancel it and close?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
                QMessageBox.StandardButton.No,
            )
            if ret != QMessageBox.StandardButton.Yes:
                event.ignore()
                return
            self._download_cancelled = True
            self._terminate_download_process()
            event.accept()
            return

        if self._worker is not None:
            _message_box(
                QMessageBox.warning,
                self,
                "Operation in progress",
                "An operation is still running. Wait for it to finish before closing this window.",
            )
            event.ignore()
            return

        if self._pm_worker is not None:
            _message_box(
                QMessageBox.warning,
                self,
                "Operation in progress",
                "A package manager version operation is still running. Wait for it to finish before closing this window.",
            )
            event.ignore()
            return

        if self._repo_manager_tab.is_busy:
            _message_box(
                QMessageBox.warning,
                self,
                "Repository operation in progress",
                "A repository operation is still running. Cancel or finish it before "
                "closing this window.",
            )
            event.ignore()
            return

        event.accept()

    def _build_ui(self) -> None:
        provision_tab = QWidget()
        root_layout = QHBoxLayout(provision_tab)
        root_layout.setContentsMargins(12, 12, 12, 12)
        root_layout.setSpacing(12)

        self._steps = QListWidget()
        self._steps.setFixedWidth(180)
        self._steps.setObjectName("stepList")
        self._steps.setAccessibleName("Provisioning steps")
        self._steps.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        for i, title in enumerate(self.STEP_TITLES):
            item = QListWidgetItem(f"{i + 1}. {title}")
            item.setData(Qt.ItemDataRole.UserRole, i)
            item.setFlags(Qt.ItemFlag.ItemIsEnabled | Qt.ItemFlag.ItemIsSelectable)
            self._steps.addItem(item)
        self._steps.currentRowChanged.connect(self._on_step_clicked)
        root_layout.addWidget(self._steps)

        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_layout.setSpacing(10)
        root_layout.addWidget(right, 1)

        self._summary = QGroupBox("Selected options")
        summary_layout = QVBoxLayout(self._summary)
        self._summary_device = QLabel("Device: -")
        self._summary_variant = QLabel("Variant: -")
        self._summary_combo = QLabel("Image: -")
        self._summary_packages = QLabel("Packages: -")
        self._summary_storage = QLabel("Storage: -")
        for label in [
            self._summary_device,
            self._summary_variant,
            self._summary_combo,
            self._summary_packages,
            self._summary_storage,
        ]:
            label.setWordWrap(True)
            summary_layout.addWidget(label)
        right_layout.addWidget(self._summary)

        self._stack = QStackedWidget()
        right_layout.addWidget(self._stack, 1)
        self._build_pages()

        button_row = QHBoxLayout()
        button_row.addStretch()
        self._back_btn = QPushButton("Back")
        self._next_btn = QPushButton("Next")
        self._back_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowBack)
        )
        self._next_btn.setIcon(
            self.style().standardIcon(QStyle.StandardPixmap.SP_ArrowForward)
        )
        self._next_btn.setObjectName("primaryButton")
        self._back_btn.clicked.connect(self._go_back)
        self._next_btn.clicked.connect(self._go_next)
        button_row.addWidget(self._back_btn)
        button_row.addWidget(self._next_btn)
        right_layout.addLayout(button_row)

        self._tabs = QTabWidget()
        self._tabs.setObjectName("featureTabs")
        self._version_manager_tab = self._build_version_manager_tab()
        self._repo_manager_tab = RepoManagementTab(
            self.repo_controller,
            config_path=self._repo_config_path,
        )
        self._repo_manager_tab.configuration_changed.connect(
            self._on_repo_configuration_changed
        )
        self._repo_manager_tab.repository_updated.connect(self._on_managed_repo_updated)
        self._repo_manager_tab.repository_update_finished.connect(
            self._on_first_use_repo_update_finished
        )
        self._repo_manager_tab.busy_changed.connect(self._on_repo_manager_busy_changed)
        self._repo_manager_tab.provision_update_finished.connect(
            self._on_provision_repo_update_finished
        )
        self._provision_tab = provision_tab
        self._tabs.addTab(self._version_manager_tab, "Version Management")
        self._tabs.addTab(self._repo_manager_tab, "Repo Management")
        self._tabs.addTab(self._provision_tab, "Device Provision")
        self._about_tab = AboutTab(
            self.state.config,
            activation_link=self._pm_activation_link,
            versions_directory=self._pm_versions_directory,
            parent=self,
        )
        self._tabs.addTab(self._about_tab, "About")
        self._tabs.currentChanged.connect(self._on_feature_tab_changed)
        self.setCentralWidget(self._tabs)
        self._apply_styles()

    def _on_feature_tab_changed(self, index: int) -> None:
        if index == self._tabs.indexOf(self._provision_tab):
            self._repo_manager_tab.start_provision_update()
        elif index == self._tabs.indexOf(self._about_tab):
            self._refresh_about_tab()

    def _apply_styles(self) -> None:
        if self._applying_styles:
            return
        self._applying_styles = True
        try:
            app = QApplication.instance()
            palette = app.palette() if app is not None else self.palette()
            self.setStyleSheet(build_stylesheet(palette))
        finally:
            self._applying_styles = False

    def _theme_colors(self) -> dict[str, str]:
        app = QApplication.instance()
        palette = app.palette() if app is not None else self.palette()
        return resolve_theme_colors(palette)

    def changeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().changeEvent(event)
        if event.type() in {
            QEvent.Type.ApplicationPaletteChange,
            QEvent.Type.PaletteChange,
        } and hasattr(self, "_steps"):
            self._apply_styles()

    def resizeEvent(self, event) -> None:  # noqa: N802 - Qt override
        super().resizeEvent(event)
        if hasattr(self, "_pm_status") and hasattr(self, "_pm_path_status"):
            QTimer.singleShot(0, self._align_pm_status_heights)

    def _set_status_kind(self, label: QLabel, kind: str | None) -> None:
        label.setText(_(label.text()))
        if label.toolTip():
            label.setToolTip(_(label.toolTip()))
        if label.objectName() == "versionStatus":
            kind = "error" if kind in {"warning", "error"} else None
        label.setProperty("statusKind", kind or "")
        label.style().unpolish(label)
        label.style().polish(label)
        label.update()
        if label in {
            getattr(self, "_pm_status", None),
            getattr(self, "_pm_path_status", None),
        }:
            QTimer.singleShot(0, self._align_pm_status_heights)

    def _connect_logs(self) -> None:
        self.state.emitter.targeted_terminal_emitted.connect(self._on_terminal_log)
        for target, text in self.state.emitter.start_terminal_delivery():
            self._append_terminal_output(target, text)

    def _terminal_view(self, target: str) -> RichTextView | None:
        return {
            "device": self._device_details,
            "download": self._download_log,
            "flash": self._flash_log,
            "fastboot": self._fastboot_log,
        }.get(target)

    def _append_terminal_output(self, target: str, text: str) -> None:
        view = self._terminal_view(target)
        if view is not None:
            view.feed_text(text)

    def _on_terminal_log(self, target: str, text: str) -> None:
        self._append_terminal_output(target, text)

    def _cleanup_thread(self) -> None:
        self._runner.safe_stop_all()
        self._worker = None

    def _set_step(self, step: int) -> None:
        if (
            self._machine.current_step == self._machine.STEP_REVIEW
            and step != self._machine.STEP_REVIEW
        ):
            self._stop_fastboot_check()
        self._machine.set_step(step)

    def _on_machine_step_changed(self, step: int) -> None:
        self._steps.blockSignals(True)
        self._steps.setCurrentRow(step)
        self._steps.blockSignals(False)
        self._stack.setCurrentIndex(step)
        self._refresh_step_items()
        self._refresh_summary()
        self._refresh_buttons()
        QTimer.singleShot(0, self._focus_current_step)

    def _refresh_step_items(self) -> None:
        for row in range(self._steps.count()):
            item = self._steps.item(row)
            flags = Qt.ItemFlag.ItemIsSelectable
            if row == self._machine.current_step or (
                (
                    row == self._machine.current_step + 1
                    or row < self._machine.current_step
                    or self._is_completed_flash_history_step(row)
                )
                and self._machine.can_open_step(row)
            ):
                flags |= Qt.ItemFlag.ItemIsEnabled
            item.setFlags(flags)

    def _focus_current_step(self) -> None:
        target: QWidget | None = None
        if self._machine.current_step == self._machine.STEP_DEVICE:
            target = self._device_list
        elif self._machine.current_step == self._machine.STEP_VARIANT:
            target = self._variant_list
        elif self._machine.current_step == self._machine.STEP_COMBO:
            target = self._combo_list
        elif (
            self._machine.current_step == self._machine.STEP_VERSIONS
            and self._version_combos
        ):
            target = self._version_combos[0]
        elif self._machine.current_step == self._machine.STEP_PACKAGES:
            target = self._packages_list
        elif self._machine.current_step == self._machine.STEP_DOWNLOAD:
            target = self._download_log
        elif (
            self._machine.current_step == self._machine.STEP_STORAGE
            and self._storage_inputs
        ):
            target = next(iter(self._storage_inputs.values()))
        elif self._machine.current_step == self._machine.STEP_REVIEW:
            target = self._proceed_cb
        elif self._machine.current_step == self._machine.STEP_FLASH:
            target = self._flash_log
        elif self._machine.current_step == self._machine.STEP_DONE:
            target = self._next_btn
        if target is not None and target.isEnabled():
            target.setFocus(Qt.FocusReason.OtherFocusReason)

    def _on_step_clicked(self, row: int) -> None:
        if row < 0 or row == self._machine.current_step:
            return
        if self._is_busy() or (
            row > self._machine.current_step
            and row != self._machine.current_step + 1
            and not self._is_completed_flash_history_step(row)
        ):
            self._steps.setCurrentRow(self._machine.current_step)
            return
        if self._machine.can_open_step(row):
            if row == self._machine.STEP_REVIEW:
                self._populate_review()
            self._set_step(row)
        else:
            self._steps.setCurrentRow(self._machine.current_step)

    def _is_completed_flash_history_step(self, step: int) -> bool:
        return self.state.flash_ret == 0 and step in {
            self._machine.STEP_FLASH,
            self._machine.STEP_DONE,
        }

    def _review_complete_if_possible(self) -> bool:
        if self.state.prepared is None:
            return False
        return self._review_complete()

    def _refresh_summary(self) -> None:
        self._summary_device.setText(
            _(
                "Device: {value}",
                value=self.state.device.display_name if self.state.device else "-",
            )
        )
        self._summary_variant.setText(
            _(
                "Variant: {value}",
                value=self.state.variant.display_name if self.state.variant else "-",
            )
        )
        self._summary_combo.setText(
            _(
                "Image: {value}",
                value=self.state.combo.display_name if self.state.combo else "-",
            )
        )
        pkgs = ", ".join(self.state.pkg_atoms) if self.state.pkg_atoms else "-"
        self._summary_packages.setText(_("Packages: {value}", value=pkgs))
        if self.state.host_blkdev_map:
            storage = ", ".join(
                f"{k}: {v}" for k, v in self.state.host_blkdev_map.items()
            )
        else:
            storage = "-"
        self._summary_storage.setText(_("Storage: {value}", value=storage))

    def _refresh_buttons(self) -> None:
        repo_tab = getattr(self, "_repo_manager_tab", None)
        if repo_tab is not None:
            repo_tab.set_external_busy(
                self._worker is not None
                or self._pm_worker is not None
                or self._download_process is not None
                or self._fastboot_process is not None
            )
        busy = self._is_busy()
        self._back_btn.setEnabled(
            not busy
            and self._machine.current_step
            not in {
                self._machine.STEP_WELCOME,
                self._machine.STEP_DOWNLOAD,
                self._machine.STEP_FLASH,
            }
        )
        self._next_btn.setEnabled(not busy and self._can_go_next())
        if self._machine.current_step == self._machine.STEP_DONE:
            self._next_btn.setText(_("Close"))
        elif self._machine.current_step == self._machine.STEP_PACKAGES:
            self._next_btn.setText(_("Proceed"))
        else:
            self._next_btn.setText(_("Next"))
        self._update_repo_btn.setEnabled(not busy and self.state.mr is not None)
        download_running = self.provision_controller.is_busy
        self._cancel_download_btn.setVisible(
            self._machine.current_step == self._machine.STEP_DOWNLOAD
            and download_running
        )
        self._cancel_download_btn.setEnabled(download_running)
        self._download_recovery_row.setVisible(
            self._machine.current_step == self._machine.STEP_DOWNLOAD
            and self._machine.download_recoverable
            and not busy
        )
        self._resume_download_btn.setEnabled(bool(self.state.pkg_atoms))
        self._reselect_versions_btn.setEnabled(self.state.combo is not None)
        self._reselect_versions_btn.setText(
            _(
                "Reselect versions"
                if self._machine.versions_visited
                else "Reselect packages"
            )
        )
        self._restart_btn.setEnabled(self.state.mr is not None)
        self._refresh_storage_btn.setEnabled(
            not busy
            and self._machine.current_step == self._machine.STEP_STORAGE
            and self.state.prepared is not None
        )
        flash_recoverable = (
            self._machine.current_step == self._machine.STEP_FLASH
            and self._machine.flash_recoverable
            and not busy
        )
        flash_running = (
            self._machine.current_step == self._machine.STEP_FLASH
            and isinstance(self._worker, FlashWorker)
            and self._worker is not None
        )
        self._interrupt_flash_btn.setVisible(flash_running)
        self._interrupt_flash_btn.setEnabled(
            flash_running and not self._flash_cancel_requested
        )
        self._flash_recovery_row.setVisible(flash_recoverable)
        self._retry_flash_btn.setEnabled(self.state.prepared is not None)
        self._review_flash_btn.setEnabled(self.state.prepared is not None)
        self._restart_flash_btn.setEnabled(self.state.mr is not None)

    def _is_busy(self) -> bool:
        repo_tab = getattr(self, "_repo_manager_tab", None)
        return (
            self._worker is not None
            or self._download_process is not None
            or self._fastboot_process is not None
            or self.provision_controller.is_busy
            or bool(repo_tab is not None and repo_tab.is_busy)
        )
