"""Domain models for oh-my-ruyi.
These models are completely independent of the ruyi SDK and Qt.
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal


@dataclass(slots=True)
class DeviceChoice:
    id: str
    display_name: str
    entity: Any = None


@dataclass(slots=True)
class VariantChoice:
    id: str
    display_name: str
    entity: Any = None


@dataclass(slots=True)
class ComboChoice:
    id: str
    display_name: str
    entity: Any = None


@dataclass(slots=True)
class PackageVersionOption:
    atom: str
    display_name: str


@dataclass(slots=True)
class PackageVersionSelection:
    original_atom: str
    package_name: str
    options: list[PackageVersionOption]
    locked_reason: str | None = None


@dataclass(frozen=True, slots=True)
class RuyiRelease:
    version: str
    channel: str
    release_date: str
    download_urls: tuple[str, ...]
    architecture: str = ""


@dataclass(frozen=True, slots=True)
class ReleaseCatalog:
    releases: tuple[RuyiRelease, ...]
    source_url: str


@dataclass(frozen=True, slots=True)
class InstalledVersion:
    version: str
    path: Path
    size: int
    architecture: str
    channel: str


@dataclass(frozen=True, slots=True)
class ActivationState:
    path: Path
    exists: bool
    is_symlink: bool
    managed: bool
    target: Path | None
    version: str | None


@dataclass(frozen=True, slots=True)
class ActivationResult:
    state: ActivationState
    backup_path: Path | None


@dataclass(frozen=True, slots=True)
class PathState:
    command: Path | None
    resolved_command: Path | None
    active_target: Path | None
    correct: bool


TelemetryMode = Literal["consent", "local", "optout"]


@dataclass(frozen=True, slots=True)
class TelemetrySetupResult:
    mode: TelemetryMode
    status: str
    output: str = ""


@dataclass(slots=True)
class BlockDeviceChoice:
    path: str
    display_name: str
    mounted: bool = False
    fingerprint: str | None = None
