"""First-use policy compatibility exports."""

from __future__ import annotations

from .core.first_use_policy import (
    _find_external_ruyi,  # noqa: F401 - retain the former private import path
    should_offer_first_use_setup,
)
from .ui.first_use_dialog import FirstUseDialog, SETUP_STEPS


__all__ = ["FirstUseDialog", "SETUP_STEPS", "should_offer_first_use_setup"]
