"""Qt workers for repository, storage, release, and telemetry services."""

from __future__ import annotations

import json
import os
import platform
import subprocess
import sys
import threading
from pathlib import Path
from typing import BinaryIO

from PySide6.QtCore import QObject, Signal, Slot

from ruyi.config import GlobalConfig
from ruyi.ruyipkg.composite_repo import CompositeRepo

from ..services import host_storage, ruyi_facade, version_manager
from .i18n import _


def _set_terminal_target(config: GlobalConfig | None, target: str) -> None:
    logger = getattr(config, "logger", None)
    setter = getattr(logger, "set_terminal_target", None)
    if callable(setter):
        setter(target)


class _BaseWorker(QObject):
    """Common signal surface for every service worker."""

    finished = Signal(object)  # worker-specific result type
    failed = Signal(str)  # error message

    def _fail(self, exc: BaseException) -> None:
        msg = f"{type(exc).__name__}: {_(str(exc))}"
        self.failed.emit(msg)


class RepoInitWorker(_BaseWorker):
    """Ensure the ruyi metadata repo is present and up to date."""

    def __init__(self, config: GlobalConfig) -> None:
        super().__init__()
        self._config = config

    @Slot()
    def run(self) -> None:
        _set_terminal_target(self._config, "welcome")
        try:
            mr = ruyi_facade.ensure_repo(self._config)
            self.finished.emit(mr)
        except BaseException as exc:  # noqa: BLE001 - surface to UI
            self._fail(exc)


class RepoSyncWorker(_BaseWorker):
    """Sync metadata repositories, equivalent to the repo part of ``ruyi update``."""

    def __init__(self, config: GlobalConfig, mr: CompositeRepo) -> None:
        super().__init__()
        self._config = config
        self._mr = mr

    @Slot()
    def run(self) -> None:
        _set_terminal_target(self._config, "device")
        try:
            mr = ruyi_facade.sync_repo(self._config, self._mr)
            self.finished.emit(mr)
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


class StorageDiscoveryWorker(_BaseWorker):
    """Discover host disks without blocking the GUI event loop."""

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(host_storage.list_disks())
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


class VersionCatalogWorker(_BaseWorker):
    """Fetch the latest stable and testing package manager releases."""

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(version_manager.fetch_release_catalog())
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


class VersionDownloadWorker(_BaseWorker):
    """Download one standalone ruyi binary into the user's version directory."""

    progress = Signal(int, int)
    cancelled = Signal()

    def __init__(
        self,
        release: version_manager.RuyiRelease,
        directory: Path,
        download_url: str,
    ) -> None:
        super().__init__()
        self._release = release
        self._directory = directory
        self._download_url = download_url
        self._cancel_requested = threading.Event()
        self._response_lock = threading.Lock()
        self._response: BinaryIO | None = None

    def request_cancel(self) -> None:
        self._cancel_requested.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            threading.Thread(
                target=self._close_response,
                args=(response,),
                daemon=True,
            ).start()

    @staticmethod
    def _close_response(response: BinaryIO) -> None:
        try:
            response.close()
        except Exception:  # noqa: BLE001 - cancellation must not block the UI
            pass

    def _set_response(self, response: BinaryIO | None) -> None:
        with self._response_lock:
            self._response = response
        if response is not None and self._cancel_requested.is_set():
            self._close_response(response)

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(
                version_manager.download_release(
                    self._release,
                    self._directory,
                    download_url=self._download_url,
                    progress=self.progress.emit,
                    cancelled=self._cancel_requested.is_set,
                    response_changed=self._set_response,
                )
            )
        except version_manager.DownloadCancelledError:
            self.cancelled.emit()
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


class VersionActivationWorker(_BaseWorker):
    """Activate a downloaded binary, requesting sudo credentials when needed."""

    password_requested = Signal(str, object)

    def __init__(
        self,
        binary: Path,
        directory: Path,
        link: Path,
        *,
        backup_unmanaged: bool,
    ) -> None:
        super().__init__()
        self._binary = binary
        self._directory = directory
        self._link = link
        self._backup_unmanaged = backup_unmanaged

    @Slot()
    def run(self) -> None:
        try:
            if os.access(self._link.parent, os.W_OK):
                result = version_manager.activate_version(
                    self._binary,
                    self._directory,
                    link=self._link,
                    backup_unmanaged=self._backup_unmanaged,
                )
            else:
                result = self._activate_with_sudo()
            self.finished.emit(result)
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)

    def _activate_with_sudo(self) -> version_manager.ActivationResult:
        if platform.system() == "Windows":
            raise RuntimeError(
                "activating /usr/local/bin/ruyi is unsupported on Windows"
            )

        response: dict[str, str | None] = {"password": None}
        self.password_requested.emit(
            _(
                "sudo password is required to update {path}.",
                path=self._link,
            ),
            response,
        )
        password = response["password"]
        if password is None:
            raise RuntimeError("activation was cancelled")

        command = [
            "sudo",
            "-S",
            "-p",
            "",
            sys.executable,
            "-m",
            "oh_my_ruyi.processes.version_activation_child",
            "activate",
            os.fspath(self._binary),
            os.fspath(self._directory),
            os.fspath(self._link),
        ]
        if self._backup_unmanaged:
            command.append("--backup-unmanaged")
        completed = subprocess.run(
            command,
            input=password + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                message or f"sudo exited with code {completed.returncode}"
            )
        try:
            payload = json.loads(completed.stdout)
        except json.JSONDecodeError as exc:
            raise RuntimeError("activation helper returned invalid output") from exc
        backup = payload.get("backup_path")
        return version_manager.ActivationResult(
            version_manager.read_activation_state(self._link, self._directory),
            Path(backup) if isinstance(backup, str) else None,
        )


class VersionDeleteWorker(_BaseWorker):
    """Delete one inactive binary from the user's version directory."""

    def __init__(self, binary: Path, directory: Path, link: Path) -> None:
        super().__init__()
        self._binary = binary
        self._directory = directory
        self._link = link

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(
                version_manager.delete_version(
                    self._binary,
                    self._directory,
                    link=self._link,
                )
            )
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


class VersionDeactivationWorker(_BaseWorker):
    """Remove the managed activation symlink, requesting sudo when needed."""

    password_requested = Signal(str, object)

    def __init__(self, directory: Path, link: Path) -> None:
        super().__init__()
        self._directory = directory
        self._link = link

    @Slot()
    def run(self) -> None:
        try:
            if os.access(self._link.parent, os.W_OK):
                result = version_manager.deactivate_version(
                    self._directory,
                    link=self._link,
                )
            else:
                result = self._deactivate_with_sudo()
            self.finished.emit(result)
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)

    def _deactivate_with_sudo(self) -> version_manager.ActivationState:
        response: dict[str, str | None] = {"password": None}
        self.password_requested.emit(
            _(
                "sudo password is required to update {path}.",
                path=self._link,
            ),
            response,
        )
        password = response["password"]
        if password is None:
            raise RuntimeError("deactivation was cancelled")
        completed = subprocess.run(
            [
                "sudo",
                "-S",
                "-p",
                "",
                sys.executable,
                "-m",
                "oh_my_ruyi.processes.version_activation_child",
                "deactivate",
                os.fspath(self._directory),
                os.fspath(self._link),
            ],
            input=password + "\n",
            capture_output=True,
            text=True,
            check=False,
        )
        if completed.returncode != 0:
            message = completed.stderr.strip() or completed.stdout.strip()
            raise RuntimeError(
                message or f"sudo exited with code {completed.returncode}"
            )
        return version_manager.read_activation_state(self._link, self._directory)


class TelemetrySetupWorker(_BaseWorker):
    """Apply the user's first-install telemetry choice using the activated ruyi."""

    process_output = Signal(str)

    def __init__(
        self,
        binary: Path,
        mode: version_manager.TelemetryMode,
    ) -> None:
        super().__init__()
        self._binary = binary
        self._mode = mode

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(
                version_manager.run_telemetry_setup(self._binary, self._mode)
            )
        except version_manager.TelemetryCommandError as exc:
            if exc.output:
                self.process_output.emit(exc.output)
            self._fail(exc)
        except BaseException as exc:  # noqa: BLE001
            self._fail(exc)


__all__ = [
    "RepoInitWorker",
    "RepoSyncWorker",
    "StorageDiscoveryWorker",
    "TelemetrySetupWorker",
    "VersionActivationWorker",
    "VersionCatalogWorker",
    "VersionDeactivationWorker",
    "VersionDeleteWorker",
    "VersionDownloadWorker",
]
