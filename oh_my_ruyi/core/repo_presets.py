"""Ordered repository presets maintained by Oh My Ruyi."""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_REPO_OFFICIAL_NAME = "RuyiSDK official repository"
DEFAULT_REPO_FALLBACK_NAME = "Ruyi default packages-index"
OFFICIAL_REPO_REMOTES = frozenset(
    {
        "https://github.com/ruyisdk/packages-index.git",
        "https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git",
    }
)


@dataclass(frozen=True, slots=True)
class RepoSource:
    remote: str | None = None
    local: str | None = None
    branch: str | None = None


@dataclass(frozen=True, slots=True)
class RepoPreset:
    id: str
    name: str
    sources: tuple[RepoSource, ...]


RUYISDK_SOURCE_PRESETS = (
    RepoSource(
        remote="https://github.com/ruyisdk/packages-index.git",
        branch="main",
    ),
    RepoSource(
        remote="https://mirror.iscas.ac.cn/git/ruyisdk/packages-index.git",
        branch="main",
    ),
    RepoSource(
        remote="https://gitee.com/ruyisdk/packages-index.git",
        branch="main",
    ),
)


PRESET_REPOS = (
    RepoPreset(
        "ruyi-addons-loongson",
        "loongson addon",
        (
            RepoSource(
                remote="https://github.com/xen0n/ruyi-addons-loongson.git",
                branch="main",
            ),
        ),
    ),
)
