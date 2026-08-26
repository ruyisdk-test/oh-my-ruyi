"""Compatibility alias for :mod:`oh_my_ruyi.gui.repo_manager_tab`."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("oh_my_ruyi.gui.repo_manager_tab")
