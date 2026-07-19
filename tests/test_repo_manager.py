from __future__ import annotations

from pathlib import Path

import pytest
from ruyi.utils import xdg_basedir

from oh_my_ruyi import repo_manager


def test_reads_default_and_additional_repos_in_config_order(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        """
[telemetry]
mode = "on"

[repo]
remote = "https://gitee.com/ruyisdk/packages-index.git"
local = "/srv/ruyi/packages-index"
branch = "stable"
disabled = true

[[repos]]
id = "second"
name = "Second repo"
remote = "https://example.test/second.git"
priority = -20
active = false

[[repos]]
id = "first"
local = "/srv/ruyi/first"
branch = "dev"
priority = 999999999999999999999999
""".strip()
        + "\n"
    )

    repos = repo_manager.read_configured_repos(config)

    assert [repo.id for repo in repos] == ["ruyisdk", "second", "first"]
    assert repos[0] == repo_manager.ConfiguredRepo(
        "ruyisdk",
        "Ruyi default packages-index",
        "https://gitee.com/ruyisdk/packages-index.git",
        "/srv/ruyi/packages-index",
        "stable",
        0,
        False,
        True,
        repo_manager.RepoSource(
            "https://gitee.com/ruyisdk/packages-index.git",
            "/srv/ruyi/packages-index",
            "stable",
        ),
    )
    assert repos[1].name == "Second repo"
    assert repos[1].priority == -20
    assert not repos[1].active
    assert repos[1].configured_source == repo_manager.RepoSource(
        "https://example.test/second.git",
        None,
        None,
    )
    assert repos[2].name == "first"
    assert repos[2].remote is None
    assert repos[2].local == "/srv/ruyi/first"
    assert repos[2].priority == 999999999999999999999999
    assert repos[2].active
    assert repos[2].configured_source == repo_manager.RepoSource(
        None,
        "/srv/ruyi/first",
        "dev",
    )


def test_missing_user_config_still_exposes_default_repo(tmp_path: Path) -> None:
    repos = repo_manager.read_configured_repos(tmp_path / "missing.toml")

    assert len(repos) == 1
    assert repos[0].id == "ruyisdk"
    assert repos[0].remote == repo_manager.DEFAULT_REPO_REMOTE
    assert repos[0].branch == "main"
    assert repos[0].active


@pytest.mark.parametrize(
    "remote, expected",
    [
        (
            "https://github.com/ruyisdk/packages-index.git",
            "RuyiSDK official repository",
        ),
        (
            "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git/",
            "RuyiSDK official repository",
        ),
        ("https://gitee.com/ruyisdk/packages-index.git", "Ruyi default packages-index"),
        (None, "Ruyi default packages-index"),
    ],
)
def test_default_repo_name_depends_on_configured_remote(
    tmp_path: Path,
    remote: str | None,
    expected: str,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[repo]\n" if remote is None else f'[repo]\nremote = "{remote}"\n'
    )

    assert repo_manager.read_configured_repos(config)[0].name == expected


def test_user_config_path_uses_ruyis_xdg_rules(monkeypatch) -> None:
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.setattr(xdg_basedir.sys, "platform", "darwin")

    assert repo_manager.user_config_path() == (
        Path.home() / "Library" / "Preferences" / "ruyi" / "config.toml"
    )


@pytest.mark.parametrize(
    "content, message",
    [
        ("repo = []\n", r"\[repo] must be a TOML table"),
        ("repos = {}\n", r"\[\[repos]] must be a TOML array"),
        ("[[repos]]\nid = 'bad'\npriority = true\nremote = 'x'\n", "priority"),
        ("[[repos]]\nid = 'bad'\nactive = 1\nremote = 'x'\n", "active"),
    ],
)
def test_rejects_invalid_repo_config(
    tmp_path: Path,
    content: str,
    message: str,
) -> None:
    config = tmp_path / "config.toml"
    config.write_text(content)

    with pytest.raises(repo_manager.RepoManagerError, match=message):
        repo_manager.read_configured_repos(config)


def test_adds_preset_inactive_through_ruyi_config_editor(tmp_path: Path) -> None:
    preset = repo_manager.PRESET_REPOS[0]
    source = repo_manager.RepoSource(
        "https://mirror.test/loongson.git",
        "/srv/ruyi/loongson",
        "next",
    )
    config = tmp_path / "config.toml"

    repo_manager.add_repo(config, preset, source, -999999999999)

    repos = repo_manager.read_configured_repos(config)
    assert [repo.id for repo in repos] == ["ruyisdk", "ruyi-addons-loongson"]
    assert repos[1] == repo_manager.ConfiguredRepo(
        "ruyi-addons-loongson",
        "loongson addon",
        "https://mirror.test/loongson.git",
        "/srv/ruyi/loongson",
        "next",
        -999999999999,
        False,
        configured_source=repo_manager.RepoSource(
            "https://mirror.test/loongson.git",
            "/srv/ruyi/loongson",
            "next",
        ),
    )


def test_default_repo_edit_sets_and_unsets_overrides(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    config.write_text(
        "[repo]\n"
        'remote = "https://old.test/repo.git"\n'
        'local = "/old/local"\n'
        'branch = "old"\n'
    )
    current = repo_manager.ConfiguredRepo(
        "ruyisdk",
        repo_manager.DEFAULT_REPO_NAME,
        "https://old.test/repo.git",
        "/old/local",
        "old",
        0,
        True,
        True,
        repo_manager.RepoSource("https://old.test/repo.git", "/old/local", "old"),
    )

    changed = repo_manager.edit_default_repo(
        config,
        current,
        repo_manager.RepoSource("https://new.test/repo.git", "/old/local", "main"),
    )

    assert changed
    default = repo_manager.read_configured_repos(config)[0]
    assert default.remote == "https://new.test/repo.git"
    assert default.local == "/old/local"
    assert default.branch == "main"


def test_edit_toggle_and_remove_additional_repo(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    preset = repo_manager.PRESET_REPOS[0]
    repo_manager.add_repo(config, preset, preset.sources[0], 10)
    repo = repo_manager.read_configured_repos(config)[1]

    repo_manager.edit_repo(
        config,
        repo,
        repo_manager.RepoSource("https://mirror.test/addon.git", None, "next"),
        -5,
    )
    repo = repo_manager.read_configured_repos(config)[1]
    assert repo.priority == -5
    assert repo.remote == "https://mirror.test/addon.git"
    assert repo.branch == "next"
    assert not repo.active

    repo_manager.set_enabled(config, repo, True)
    repo = repo_manager.read_configured_repos(config)[1]
    assert repo.active

    repo_manager.remove_repo(config, repo)
    assert [item.id for item in repo_manager.read_configured_repos(config)] == [
        "ruyisdk"
    ]


def test_default_repo_enable_disable_uses_ruyi_config_editor(tmp_path: Path) -> None:
    config = tmp_path / "config.toml"
    default = repo_manager.read_configured_repos(config)[0]

    repo_manager.set_enabled(config, default, False)
    default = repo_manager.read_configured_repos(config)[0]
    assert not default.active

    repo_manager.set_enabled(config, default, True)
    assert repo_manager.read_configured_repos(config)[0].active
