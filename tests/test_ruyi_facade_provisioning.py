from __future__ import annotations

from types import SimpleNamespace

from ruyi.ruyipkg.entity_provider import BaseEntity

from oh_my_ruyi.services import ruyi_facade


class _EntityStore:
    def __init__(
        self,
        devices: list[BaseEntity],
        related: dict[BaseEntity, list[BaseEntity]],
    ) -> None:
        self._devices = devices
        self._related = related

    def iter_entities(self, entity_type: str):
        return iter(self._devices if entity_type == "device" else [])

    def traverse_related_entities(self, entity: BaseEntity, **_kwargs):
        return iter(self._related.get(entity, []))


def _entity(
    entity_type: str,
    entity_id: str,
    display_name: str,
    **data,
) -> BaseEntity:
    return BaseEntity(
        entity_type,
        entity_id,
        {entity_type: {"display_name": display_name, **data}},
    )


def _provisioning_repo():
    hybrid = _entity("device", "hybrid", "Hybrid device")
    fastboot_only = _entity("device", "fastboot-only", "Fastboot-only device")
    docs_only = _entity("device", "docs-only", "Documentation-only device")
    broken = _entity("device", "broken", "Broken device")
    orphan = _entity("device", "orphan", "Orphan device")

    sd = _entity("device-variant", "hybrid@sd", "SD", variant_name="sd")
    emmc = _entity("device-variant", "hybrid@emmc", "eMMC", variant_name="emmc")
    fastboot_variant = _entity(
        "device-variant",
        "fastboot-only@generic",
        "Generic",
        variant_name="generic",
    )
    docs_variant = _entity(
        "device-variant",
        "docs-only@generic",
        "Generic",
        variant_name="generic",
    )
    broken_variant = _entity(
        "device-variant",
        "broken@generic",
        "Generic",
        variant_name="generic",
    )

    disk_image = _entity(
        "image-combo",
        "disk-image",
        "Disk image",
        package_atoms=["board-image/disk"],
    )
    fastboot_image = _entity(
        "image-combo",
        "fastboot-image",
        "Fastboot image",
        package_atoms=["board-image/fastboot"],
    )
    mixed_image = _entity(
        "image-combo",
        "mixed-image",
        "Mixed image",
        package_atoms=["board-image/disk", "board-image/fastboot"],
    )
    docs_image = _entity(
        "image-combo",
        "docs-image",
        "Documentation only",
        package_atoms=[],
        postinst_msgid="provisioner/docs",
    )
    broken_image = _entity(
        "image-combo",
        "broken-image",
        "Broken image",
        package_atoms=["board-image/missing"],
    )

    related = {
        hybrid: [sd, emmc],
        fastboot_only: [fastboot_variant],
        docs_only: [docs_variant],
        broken: [broken_variant],
        sd: [disk_image, fastboot_image, mixed_image, docs_image],
        emmc: [fastboot_image],
        fastboot_variant: [fastboot_image],
        docs_variant: [docs_image],
        broken_variant: [broken_image],
    }
    repo = SimpleNamespace(
        entity_store=_EntityStore(
            [hybrid, fastboot_only, docs_only, broken, orphan],
            related,
        )
    )
    return repo, SimpleNamespace(hybrid=hybrid, sd=sd)


def _stub_strategies(monkeypatch) -> None:
    strategies = {
        "board-image/disk": SimpleNamespace(need_cmd=["sudo", "dd"]),
        "board-image/fastboot": SimpleNamespace(need_cmd=["sudo", "fastboot"]),
    }
    monkeypatch.setattr(
        ruyi_facade,
        "ProvisionStrategyProvider",
        lambda _mr: object(),
    )
    monkeypatch.setattr(
        ruyi_facade,
        "get_pkg_provision_strategy",
        lambda _provider, _mr, atom: strategies[atom],
    )


def test_linux_filters_documentation_only_and_unresolvable_images(monkeypatch) -> None:
    repo, entities = _provisioning_repo()
    _stub_strategies(monkeypatch)
    monkeypatch.setattr(ruyi_facade.platform, "system", lambda: "Linux")

    assert [choice.id for choice in ruyi_facade.list_devices(repo)] == [
        "fastboot-only",
        "hybrid",
    ]
    assert [
        choice.id for choice in ruyi_facade.list_variants(repo, entities.hybrid)
    ] == ["hybrid@emmc", "hybrid@sd"]
    assert [choice.id for choice in ruyi_facade.list_combos(repo, entities.sd)] == [
        "disk-image",
        "fastboot-image",
        "mixed-image",
    ]


def test_macos_filters_fastboot_images_and_empty_parents(monkeypatch) -> None:
    repo, entities = _provisioning_repo()
    _stub_strategies(monkeypatch)
    monkeypatch.setattr(ruyi_facade.platform, "system", lambda: "Darwin")

    assert [choice.id for choice in ruyi_facade.list_devices(repo)] == ["hybrid"]
    assert [
        choice.id for choice in ruyi_facade.list_variants(repo, entities.hybrid)
    ] == ["hybrid@sd"]
    assert [choice.id for choice in ruyi_facade.list_combos(repo, entities.sd)] == [
        "disk-image"
    ]


def test_has_device_entities_ignores_host_filtering() -> None:
    repo, _entities = _provisioning_repo()
    empty_repo = SimpleNamespace(entity_store=_EntityStore([], {}))

    assert ruyi_facade.has_device_entities(repo)
    assert not ruyi_facade.has_device_entities(empty_repo)
