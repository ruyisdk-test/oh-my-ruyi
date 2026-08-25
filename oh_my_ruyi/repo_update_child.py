"""Compatibility entry point for :mod:`oh_my_ruyi.processes.repo_update_child`."""

from .processes.repo_update_child import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
