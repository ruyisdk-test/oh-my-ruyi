"""Build the provisioning wizard pages.

The page factory owns widget construction and signal wiring only.  Provisioning
state transitions remain in :mod:`oh_my_ruyi.main_window`; callbacks are passed
in so this module stays independent of the window's state machine.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from PySide6.QtWidgets import (
    QCheckBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QPushButton,
    QStyle,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from ..rich_output import RichTextView


Callback = Callable[..., object]
AddPage = Callable[[str, list[QWidget]], object]
MakeLogView = Callable[[], RichTextView]


@dataclass(slots=True)
class ProvisionPageWidgets:
    """Widgets that the provisioning state machine updates after construction."""

    welcome_status: QLabel
    device_list: QListWidget
    device_status: QLabel
    device_details: RichTextView
    update_repo_btn: QPushButton
    variant_list: QListWidget
    combo_list: QListWidget
    versions_box: QWidget
    versions_layout: QVBoxLayout
    versions_status: QLabel
    packages_list: QListWidget
    download_status: QLabel
    download_log: RichTextView
    cancel_download_btn: QPushButton
    resume_download_btn: QPushButton
    reselect_versions_btn: QPushButton
    restart_btn: QPushButton
    download_recovery_row: QWidget
    storage_box: QWidget
    storage_layout: QVBoxLayout
    storage_error: QLabel
    refresh_storage_btn: QPushButton
    review_steps: RichTextView
    review_missing: QLabel
    fastboot_status: QLabel
    fastboot_log: RichTextView
    check_fastboot_btn: QPushButton
    proceed_cb: QCheckBox
    flash_status: QLabel
    interrupt_flash_btn: QPushButton
    retry_flash_btn: QPushButton
    review_flash_btn: QPushButton
    restart_flash_btn: QPushButton
    flash_recovery_row: QWidget
    flash_log: RichTextView
    done_label: QLabel
    postinst_label: QLabel


def build_provision_pages(
    *,
    add_page: AddPage,
    make_log_view: MakeLogView,
    style: QStyle,
    storage_hint: str,
    refresh_buttons: Callback,
    activate_current_step: Callback,
    start_repo_sync: Callback,
    cancel_download: Callback,
    resume_download: Callback,
    reselect_versions: Callback,
    restart_flow: Callback,
    refresh_storage_disks: Callback,
    check_fastboot_devices: Callback,
    interrupt_flash: Callback,
    retry_flash: Callback,
    review_flash_settings: Callback,
) -> ProvisionPageWidgets:
    """Construct and register all pages used by the provisioning wizard."""

    welcome_status = QLabel("Preparing the RuyiSDK metadata repository...")
    welcome_status.setWordWrap(True)
    welcome_status.setProperty("statusKind", "warning")
    add_page(
        "RuyiSDK Device Provisioning",
        [
            QLabel(
                "This screen walks through the same flow as `ruyi device provision`. "
                "The left side shows the whole process; the right side keeps your "
                "choices visible while showing the current step."
            ),
            welcome_status,
        ],
    )

    device_list = QListWidget()
    device_list.setAccessibleName("Devices")
    device_list.currentRowChanged.connect(refresh_buttons)
    device_list.itemDoubleClicked.connect(activate_current_step)
    device_status = QLabel("")
    device_status.setWordWrap(True)
    device_status.setProperty("statusKind", "warning")
    device_details = make_log_view()
    device_details.setMaximumHeight(180)
    device_details.hide()
    update_repo_btn = QPushButton("Update metadata")
    update_repo_btn.clicked.connect(start_repo_sync)
    add_page(
        "Pick your device",
        [device_status, update_repo_btn, device_list, device_details],
    )

    variant_list = QListWidget()
    variant_list.setAccessibleName("Device variants")
    variant_list.currentRowChanged.connect(refresh_buttons)
    variant_list.itemDoubleClicked.connect(activate_current_step)
    add_page("Pick the device variant", [variant_list])

    combo_list = QListWidget()
    combo_list.setAccessibleName("System images")
    combo_list.currentRowChanged.connect(refresh_buttons)
    combo_list.itemDoubleClicked.connect(activate_current_step)
    add_page("Pick the system image", [combo_list])

    versions_box = QWidget()
    versions_layout = QVBoxLayout(versions_box)
    versions_layout.setContentsMargins(0, 0, 0, 0)
    versions_status = QLabel("")
    versions_status.setWordWrap(True)
    add_page(
        "Customize package versions",
        [
            QLabel(
                "By default, ruyi installs the latest version of each package. "
                "When other versions are available, choose them here."
            ),
            versions_status,
            versions_box,
        ],
    )

    packages_list = QListWidget()
    packages_list.setAccessibleName("Packages to install")
    packages_list.itemDoubleClicked.connect(activate_current_step)
    add_page(
        "Confirm packages",
        [
            QLabel("The following packages will be downloaded and installed:"),
            packages_list,
        ],
    )

    download_status = QLabel("Download has not started.")
    download_log = make_log_view()
    cancel_download_btn = QPushButton("Cancel download")
    cancel_download_btn.setIcon(
        style.standardIcon(QStyle.StandardPixmap.SP_DialogCancelButton)
    )
    cancel_download_btn.clicked.connect(cancel_download)
    resume_download_btn = QPushButton("Resume download")
    resume_download_btn.clicked.connect(resume_download)
    reselect_versions_btn = QPushButton("Reselect versions")
    reselect_versions_btn.clicked.connect(reselect_versions)
    restart_btn = QPushButton("Start over")
    restart_btn.clicked.connect(restart_flow)
    download_recovery_row = QWidget()
    recovery_layout = QHBoxLayout(download_recovery_row)
    recovery_layout.setContentsMargins(0, 0, 0, 0)
    recovery_layout.addWidget(resume_download_btn)
    recovery_layout.addWidget(reselect_versions_btn)
    recovery_layout.addWidget(restart_btn)
    add_page(
        "Download and install packages",
        [download_status, cancel_download_btn, download_recovery_row, download_log],
    )

    storage_box = QWidget()
    storage_layout = QVBoxLayout(storage_box)
    storage_layout.setContentsMargins(0, 0, 0, 0)
    storage_error = QLabel("")
    storage_error.setWordWrap(True)
    storage_error.setProperty("statusKind", "warning")
    refresh_storage_btn = QPushButton("Refresh disks")
    refresh_storage_btn.setIcon(
        style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
    )
    refresh_storage_btn.setToolTip("Scan for newly connected storage devices")
    refresh_storage_btn.clicked.connect(refresh_storage_disks)
    add_page(
        "Provide storage paths",
        [
            QLabel(storage_hint),
            refresh_storage_btn,
            storage_box,
            storage_error,
        ],
    )

    review_steps = make_log_view()
    review_steps.setLineWrapMode(QTextEdit.LineWrapMode.WidgetWidth)
    review_steps.setReadOnly(True)
    review_missing = QLabel("")
    review_missing.setWordWrap(True)
    review_missing.setProperty("statusKind", "error")
    fastboot_status = QLabel("")
    fastboot_status.setWordWrap(True)
    fastboot_log = make_log_view()
    fastboot_log.setMaximumHeight(130)
    fastboot_log.hide()
    check_fastboot_btn = QPushButton("Check fastboot devices")
    check_fastboot_btn.setIcon(
        style.standardIcon(QStyle.StandardPixmap.SP_BrowserReload)
    )
    check_fastboot_btn.clicked.connect(check_fastboot_devices)
    proceed_cb = QCheckBox("Proceed with flashing.")
    proceed_cb.toggled.connect(refresh_buttons)
    add_page(
        "Review flashing actions",
        [
            review_steps,
            review_missing,
            fastboot_status,
            fastboot_log,
            check_fastboot_btn,
            proceed_cb,
        ],
    )

    flash_status = QLabel("Flash has not started.")
    interrupt_flash_btn = QPushButton("Interrupt flash")
    interrupt_flash_btn.setIcon(
        style.standardIcon(QStyle.StandardPixmap.SP_BrowserStop)
    )
    interrupt_flash_btn.clicked.connect(interrupt_flash)
    retry_flash_btn = QPushButton("Retry flash")
    retry_flash_btn.clicked.connect(retry_flash)
    review_flash_btn = QPushButton("Review settings")
    review_flash_btn.clicked.connect(review_flash_settings)
    restart_flash_btn = QPushButton("Start over")
    restart_flash_btn.clicked.connect(restart_flow)
    flash_recovery_row = QWidget()
    flash_recovery_layout = QHBoxLayout(flash_recovery_row)
    flash_recovery_layout.setContentsMargins(0, 0, 0, 0)
    flash_recovery_layout.addWidget(retry_flash_btn)
    flash_recovery_layout.addWidget(review_flash_btn)
    flash_recovery_layout.addWidget(restart_flash_btn)
    flash_log = make_log_view()
    add_page(
        "Flash device",
        [flash_status, interrupt_flash_btn, flash_recovery_row, flash_log],
    )

    done_label = QLabel("")
    done_label.setWordWrap(True)
    postinst_label = QLabel("")
    postinst_label.setWordWrap(True)
    postinst_label.setFrameShape(QFrame.Shape.Box)
    postinst_label.setObjectName("postInstallMessage")
    add_page("Done", [done_label, postinst_label])

    return ProvisionPageWidgets(
        welcome_status=welcome_status,
        device_list=device_list,
        device_status=device_status,
        device_details=device_details,
        update_repo_btn=update_repo_btn,
        variant_list=variant_list,
        combo_list=combo_list,
        versions_box=versions_box,
        versions_layout=versions_layout,
        versions_status=versions_status,
        packages_list=packages_list,
        download_status=download_status,
        download_log=download_log,
        cancel_download_btn=cancel_download_btn,
        resume_download_btn=resume_download_btn,
        reselect_versions_btn=reselect_versions_btn,
        restart_btn=restart_btn,
        download_recovery_row=download_recovery_row,
        storage_box=storage_box,
        storage_layout=storage_layout,
        storage_error=storage_error,
        refresh_storage_btn=refresh_storage_btn,
        review_steps=review_steps,
        review_missing=review_missing,
        fastboot_status=fastboot_status,
        fastboot_log=fastboot_log,
        check_fastboot_btn=check_fastboot_btn,
        proceed_cb=proceed_cb,
        flash_status=flash_status,
        interrupt_flash_btn=interrupt_flash_btn,
        retry_flash_btn=retry_flash_btn,
        review_flash_btn=review_flash_btn,
        restart_flash_btn=restart_flash_btn,
        flash_recovery_row=flash_recovery_row,
        flash_log=flash_log,
        done_label=done_label,
        postinst_label=postinst_label,
    )


__all__ = ["ProvisionPageWidgets", "build_provision_pages"]
