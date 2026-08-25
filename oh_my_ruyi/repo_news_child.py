"""Compatibility entry point for :mod:`oh_my_ruyi.processes.repo_news_child`."""

from .processes.repo_news_child import main

__all__ = ["main"]

if __name__ == "__main__":
    raise SystemExit(main())
