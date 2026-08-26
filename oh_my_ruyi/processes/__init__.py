"""Child-process entry points used by Qt's ``QProcess`` integration.

Modules in this package are intentionally small command adapters.  They keep
blocking package, repository, and news operations out of the Qt event loop.
"""

from .environment import configure_ruyi_qprocess_environment

__all__ = ["configure_ruyi_qprocess_environment"]
