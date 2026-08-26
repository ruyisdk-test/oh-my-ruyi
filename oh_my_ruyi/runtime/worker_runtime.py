"""Reusable Qt worker/thread lifecycle primitives.

Workers own blocking operations; callers own the worker and thread references.
Keeping the lifecycle code here makes every operation use the same queued
start and bounded cleanup semantics without changing worker signal contracts.
"""

from __future__ import annotations

from collections.abc import Callable

from PySide6.QtCore import QObject, QThread, Qt


def start_worker(
    worker: QObject,
    run_slot,
    *,
    thread_factory: Callable[[], QThread] | None = None,
    connection_type: Qt.ConnectionType | None = None,
) -> QThread:
    """Move ``worker`` to a fresh thread and invoke ``run_slot`` once queued."""
    thread_factory = QThread if thread_factory is None else thread_factory
    connection_type = (
        Qt.ConnectionType.QueuedConnection
        if connection_type is None
        else connection_type
    )
    thread = thread_factory()
    worker.moveToThread(thread)
    thread.started.connect(run_slot, type=connection_type)
    thread.start()
    return thread


def stop_thread(thread: QThread | None) -> None:
    """Quit and wait for a worker thread using the established cleanup contract."""
    if thread is None:
        return
    thread.quit()
    thread.wait()


__all__ = ["start_worker", "stop_thread"]
