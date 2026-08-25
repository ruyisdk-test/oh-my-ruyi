"""Background QThread worker tasks and thread management."""

from __future__ import annotations

from .worker_manager import WorkerTaskRunner
from .workers import (
    FlashWorker,
    RepoInitWorker,
    RepoSyncWorker,
    StorageDiscoveryWorker,
    TelemetrySetupWorker,
    VersionActivationWorker,
    VersionCatalogWorker,
    VersionDeactivationWorker,
    VersionDeleteWorker,
    VersionDownloadWorker,
    _BaseWorker,
    run_worker_in_thread,
    safe_stop_thread,
)

__all__ = [
    "FlashWorker",
    "RepoInitWorker",
    "RepoSyncWorker",
    "StorageDiscoveryWorker",
    "TelemetrySetupWorker",
    "VersionActivationWorker",
    "VersionCatalogWorker",
    "VersionDeactivationWorker",
    "VersionDeleteWorker",
    "VersionDownloadWorker",
    "WorkerTaskRunner",
    "_BaseWorker",
    "run_worker_in_thread",
    "safe_stop_thread",
]
