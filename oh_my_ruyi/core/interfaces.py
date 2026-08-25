"""Interfaces for infra adapters to invert dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING, Protocol, List

if TYPE_CHECKING:
    from ..infra.ruyi_adapter import PreparedProvision

from .models import (
    DeviceChoice,
    VariantChoice,
    ComboChoice,
    PackageVersionSelection,
    BlockDeviceChoice,
)


class IRuyiAdapter(Protocol):
    def list_devices(self) -> List[DeviceChoice]: ...

    def list_variants(self, device_id: str) -> List[VariantChoice]: ...

    def list_combos(self, variant_id: str) -> List[ComboChoice]: ...

    def list_package_version_selections(
        self, combo_id: str
    ) -> List[PackageVersionSelection]: ...

    def prepare_provision(
        self, combo_id: str, packages: List[str]
    ) -> PreparedProvision: ...


class IStorageScanner(Protocol):
    def list_disks(self) -> List[BlockDeviceChoice]: ...

    def is_disk_or_child_mounted(self, path: str) -> bool: ...

    def is_path_mounted_blkdev(self, path: str) -> bool: ...

    def validate_host_block_device_fingerprint(
        self, path: str, expected_fingerprint: str
    ) -> bool: ...
