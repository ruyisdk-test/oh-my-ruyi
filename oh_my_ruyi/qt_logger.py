"""Compatibility alias for :mod:`oh_my_ruyi.runtime.qt_logger`."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("oh_my_ruyi.runtime.qt_logger")
