"""First-use policy and setup-dialog exports for the GUI."""

from __future__ import annotations

from ..core.first_use_policy import (
    _find_external_ruyi,  # noqa: F401 - shared policy helper
    should_offer_first_use_setup,
)
from ..ui.first_use_dialog import FirstUseDialog, SETUP_STEPS


__all__ = ["FirstUseDialog", "SETUP_STEPS", "should_offer_first_use_setup"]
