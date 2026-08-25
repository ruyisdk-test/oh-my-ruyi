"""Tests for the Qt-free state invalidation boundary."""

from __future__ import annotations

from oh_my_ruyi.core.state import WizardState
from oh_my_ruyi.core.repo_presets import RepoPreset as CoreRepoPreset
from oh_my_ruyi.state import WizardState as CompatibilityWizardState
from oh_my_ruyi.repo_presets import RepoPreset as CompatibilityRepoPreset


def test_repo_preset_compatibility_import_is_the_same_type() -> None:
    assert CompatibilityRepoPreset is CoreRepoPreset


def test_state_compatibility_import_is_the_same_type() -> None:
    assert CompatibilityWizardState is WizardState


def test_clear_prepared_discards_derived_values() -> None:
    state = WizardState(config=object(), emitter=object())  # type: ignore[arg-type]
    state.pkg_atoms.extend(["demo"])
    state.prepared = object()  # type: ignore[assignment]
    state.host_blkdev_map["root"] = "/dev/test"
    state.host_blkdev_fingerprints["root"] = "fingerprint"
    state.flash_ret = 0
    state.postinst_msg = "done"

    state.clear_prepared()

    assert state.pkg_atoms == ["demo"]
    assert state.prepared is None
    assert state.host_blkdev_map == {}
    assert state.host_blkdev_fingerprints == {}
    assert state.flash_ret == 0
    assert state.postinst_msg == "done"


def test_reset_for_repository_invalidates_repository_and_selection() -> None:
    state = WizardState(config=object(), emitter=object())  # type: ignore[arg-type]
    state.mr = object()  # type: ignore[assignment]
    state.device = object()  # type: ignore[assignment]
    state.variant = object()  # type: ignore[assignment]
    state.combo = object()  # type: ignore[assignment]
    state.pkg_atoms.append("demo")
    state.flash_ret = 1
    state.postinst_msg = "done"

    state.reset_for_repository()

    assert state.mr is None
    assert state.device is None
    assert state.variant is None
    assert state.combo is None
    assert state.pkg_atoms == []
    assert state.prepared is None
    assert state.flash_ret is None
    assert state.postinst_msg is None


def test_reset_for_restart_retains_repository() -> None:
    state = WizardState(config=object(), emitter=object())  # type: ignore[arg-type]
    repository = object()
    state.mr = repository  # type: ignore[assignment]
    state.device = object()  # type: ignore[assignment]
    state.pkg_atoms.append("demo")
    state.flash_ret = 1
    state.postinst_msg = "done"

    state.reset_for_restart()

    assert state.mr is repository
    assert state.device is None
    assert state.pkg_atoms == []
    assert state.flash_ret is None
    assert state.postinst_msg == "done"
