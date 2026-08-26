"""Compatibility alias for :mod:`oh_my_ruyi.services.ruyi_facade`."""

from importlib import import_module
import sys

sys.modules[__name__] = import_module("oh_my_ruyi.services.ruyi_facade")
