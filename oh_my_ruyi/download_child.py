"""Compatibility entry point for :mod:`oh_my_ruyi.processes.download_child`."""

from .processes.download_child import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
