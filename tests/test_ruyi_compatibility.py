from __future__ import annotations

import os
import re
import sys
from pathlib import Path
from typing import Any

import pytest
from ruyi.ruyipkg.entity_provider import BaseEntity
from ruyi.ruyipkg.pkg_manifest import BoundPackageManifest

from oh_my_ruyi.services import ruyi_facade, version_manager


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


class _Logger:
    def __init__(self) -> None:
        self.debug: list[str] = []
        self.failures: list[str] = []

    def D(self, message: str) -> None:
        self.debug.append(message)

    def F(self, message: str) -> None:
        self.failures.append(message)


class _ContractRepo:
    repo_id = "compatibility-fixture"

    def __init__(self) -> None:
        device = _entity("device", "contract-device", "Contract device")
        variant = _entity(
            "device-variant",
            "contract-device@generic",
            "Generic",
            variant_name="generic",
        )
        combo = _entity(
            "image-combo",
            "contract-image",
            "Contract image",
            package_atoms=["board-image/contract-image"],
        )
        self.entities = (device, variant, combo)
        self.entity_store = _EntityStore(
            [device],
            {
                device: [variant],
                variant: [combo],
            },
        )
        self.flash_calls: list[tuple[dict[str, str], dict[str, str]]] = []
        self._manifests = [
            self._manifest("1.0.0"),
            self._manifest("1.1.0"),
        ]

    def _manifest(self, version: str) -> BoundPackageManifest:
        return BoundPackageManifest(
            "board-image",
            "contract-image",
            version,
            {
                "format": "v1",
                "metadata": {
                    "desc": "Compatibility fixture",
                    "vendor": {"name": "Oh My Ruyi tests", "eula": None},
                },
                "distfiles": [],
                "kind": ["provisionable"],
                "provisionable": {
                    "partition_map": {"disk": "images/disk.img"},
                    "strategy": "contract-v1",
                },
            },
            self,
        )

    def get_pkg_latest_ver(
        self,
        name: str,
        category: str | None,
        include_prerelease_vers: bool,
    ) -> BoundPackageManifest:
        candidates = list(self.iter_pkg_vers(name, category))
        if not include_prerelease_vers:
            candidates = [pm for pm in candidates if not pm.is_prerelease]
        if not candidates:
            raise KeyError((category, name))
        return max(candidates, key=lambda pm: pm.semver)

    def iter_pkg_vers(self, name: str, category: str | None):
        if (category, name) != ("board-image", "contract-image"):
            raise KeyError((category, name))
        return iter(self._manifests)

    def get_from_plugin(self, plugin_id: str, key: str) -> object:
        assert plugin_id == "ruyi-device-provision-strategy-std"
        assert key == "PROVIDED_DEVICE_PROVISION_STRATEGIES_V1"
        return {
            "contract-v1": {
                "priority": 10,
                "need_host_blkdevs_fn": self._need_host_blkdevs,
                "need_cmd": ["sudo", "dd"],
                "pretend_fn": self._pretend,
                "flash_fn": self._flash,
            }
        }

    def eval_plugin_fn(
        self,
        function: object,
        *args: object,
        **kwargs: object,
    ) -> object:
        assert callable(function)
        return function(*args, **kwargs)

    @staticmethod
    def _need_host_blkdevs(parts: list[str]) -> list[str]:
        return ["disk"] if "disk" in parts else []

    @staticmethod
    def _pretend(images: dict[str, str], devices: dict[str, str]) -> list[str]:
        return [f"write {images['disk']} to {devices['disk']}"]

    def _flash(self, images: dict[str, str], devices: dict[str, str]) -> int:
        self.flash_calls.append((dict(images), dict(devices)))
        return 0


def _entity(
    entity_type: str,
    entity_id: str,
    display_name: str,
    **data: Any,
) -> BaseEntity:
    return BaseEntity(
        entity_type,
        entity_id,
        {entity_type: {"display_name": display_name, **data}},
    )


def _config(tmp_path: Path, logger: _Logger):
    return type(
        "ContractConfig",
        (),
        {
            "include_prereleases": False,
            "logger": logger,
            "global_blob_install_root": staticmethod(
                lambda slug: os.fspath(tmp_path / "blobs" / slug)
            ),
        },
    )()


def test_facade_contract_uses_real_ruyi_provisioning_api(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    repo = _ContractRepo()
    logger = _Logger()
    config = _config(tmp_path, logger)
    device, variant, combo = repo.entities
    monkeypatch.setattr(ruyi_facade.platform, "system", lambda: "Linux")

    assert [item.entity for item in ruyi_facade.list_devices(repo)] == [device]
    assert [item.entity for item in ruyi_facade.list_variants(repo, device)] == [
        variant
    ]
    assert [item.entity for item in ruyi_facade.list_combos(repo, variant)] == [combo]

    selections = ruyi_facade.list_package_version_selections(
        config,
        repo,
        ["board-image/contract-image"],
    )
    assert [option.atom for option in selections[0].options] == [
        "board-image/contract-image(==1.1.0)",
        "board-image/contract-image(==1.0.0)",
    ]
    assert ruyi_facade.is_package_version_customization_possible(
        config,
        repo,
        ["board-image/contract-image"],
    )

    prepared = ruyi_facade.prepare_provision(
        config,
        repo,
        ["board-image/contract-image"],
    )
    image_path = os.fspath(
        tmp_path / "blobs" / "contract-image-1.1.0" / "images" / "disk.img"
    )
    target = {"disk": "/dev/compatibility-test"}

    assert prepared.all_parts == ["disk"]
    assert prepared.requested_host_blkdevs == ["disk"]
    assert prepared.needed_cmds == {"sudo", "dd"}
    assert prepared.pkg_part_maps == {
        "board-image/contract-image": {"disk": image_path}
    }
    assert ruyi_facade.compute_pretend_steps(prepared, target) == [
        f"write {image_path} to /dev/compatibility-test"
    ]
    assert ruyi_facade.run_flash(config, prepared, target) == 0
    assert repo.flash_calls == [({"disk": image_path}, target)]


def test_download_contract_uses_real_ruyi_install_entrypoint(tmp_path: Path) -> None:
    repo = _ContractRepo()
    logger = _Logger()
    config = _config(tmp_path, logger)

    assert ruyi_facade.run_download(config, repo, ["board-image/missing"]) == 1
    assert logger.failures
    assert "matches no package" in logger.failures[-1]


@pytest.mark.parametrize(
    ("mode", "expected_status"),
    [
        ("consent", "on"),
        ("local", "local"),
        ("optout", "off"),
    ],
)
def test_first_use_answers_work_with_installed_ruyi_cli(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    mode: version_manager.TelemetryMode,
    expected_status: str,
) -> None:
    binary = Path(sys.executable).with_name("ruyi")
    assert binary.is_file(), f"ruyi console script is missing beside {sys.executable}"

    roots = {
        "XDG_CACHE_HOME": tmp_path / "cache",
        "XDG_CONFIG_HOME": tmp_path / "config",
        "XDG_DATA_HOME": tmp_path / "data",
        "XDG_STATE_HOME": tmp_path / "state",
    }
    for name, path in roots.items():
        monkeypatch.setenv(name, os.fspath(path))
    monkeypatch.setenv("XDG_CONFIG_DIRS", os.fspath(tmp_path / "config-dirs"))
    monkeypatch.setenv("XDG_DATA_DIRS", os.fspath(tmp_path / "data-dirs"))
    monkeypatch.delenv("RUYI_TELEMETRY_OPTOUT", raising=False)

    config_file = roots["XDG_CONFIG_HOME"] / "ruyi" / "config.toml"
    config_file.parent.mkdir(parents=True)
    config_file.write_text(
        '[repo]\ndisabled = true\n\n[telemetry]\npm_telemetry_url = ""\n',
        encoding="utf-8",
    )

    result = version_manager.run_telemetry_setup(binary, mode, timeout=15)
    plain_output = re.sub(r"\x1b\[[0-?]*[ -/]*[@-~]", "", result.output).replace(
        "\r", ""
    )
    status_lines = {line.strip() for line in plain_output.splitlines()}

    assert result.status == expected_status
    assert expected_status in status_lines
    assert f'mode = "{expected_status}"' in config_file.read_text(encoding="utf-8")
