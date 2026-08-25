"""Core domain models, FSM, and state structures."""

from .models import (
    ActivationResult,
    ActivationState,
    BlockDeviceChoice,
    ComboChoice,
    DeviceChoice,
    InstalledVersion,
    PackageVersionOption,
    PackageVersionSelection,
    PathState,
    ReleaseCatalog,
    RuyiRelease,
    TelemetryMode,
    TelemetrySetupResult,
    VariantChoice,
)
from .repo_presets import (
    DEFAULT_REPO_FALLBACK_NAME,
    DEFAULT_REPO_OFFICIAL_NAME,
    OFFICIAL_REPO_REMOTES,
    PRESET_REPOS,
    RUYISDK_SOURCE_PRESETS,
    RepoPreset,
    RepoSource,
)
from .state import WizardState
from .state_machine import ProvisionStateMachine

__all__ = [
    "ActivationResult",
    "ActivationState",
    "BlockDeviceChoice",
    "ComboChoice",
    "DeviceChoice",
    "InstalledVersion",
    "PackageVersionOption",
    "PackageVersionSelection",
    "PathState",
    "ReleaseCatalog",
    "RuyiRelease",
    "TelemetryMode",
    "TelemetrySetupResult",
    "VariantChoice",
    "DEFAULT_REPO_FALLBACK_NAME",
    "DEFAULT_REPO_OFFICIAL_NAME",
    "OFFICIAL_REPO_REMOTES",
    "PRESET_REPOS",
    "RUYISDK_SOURCE_PRESETS",
    "RepoPreset",
    "RepoSource",
    "WizardState",
    "ProvisionStateMachine",
]
