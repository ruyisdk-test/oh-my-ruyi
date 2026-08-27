from __future__ import annotations

import json
import os
import shutil
import stat
import subprocess
import sys
import textwrap
from pathlib import Path

import pytest


SCRIPT = Path(__file__).parents[1] / "ruyi-install.sh"
RELEASE_API_URL = "https://api.ruyisdk.cn/releases/latest-pm"
FALLBACK_RELEASES_URL = (
    "https://ruyisdk.org/data/api/api_ruyisdk_cn/releases_latest_pm.json"
)


def _write_executable(path: Path, content: str) -> None:
    normalized = textwrap.dedent(content).lstrip()
    if normalized.startswith("#!/usr/bin/env python3\n"):
        normalized = f"#!{sys.executable}\n{normalized.split(chr(10), 1)[1]}"
    path.write_text(normalized, encoding="utf-8")
    path.chmod(0o755)


def _make_fake_tools(tmp_path: Path) -> Path:
    tool_dir = tmp_path / "fake-bin"
    tool_dir.mkdir(exist_ok=True)
    _write_executable(
        tool_dir / "uname",
        """
        #!/bin/sh
        case "$1" in
          -s) printf '%s\\n' "${FAKE_UNAME_S:-Linux}" ;;
          -m) printf '%s\\n' "${FAKE_UNAME_M:-x86_64}" ;;
          *) exit 1 ;;
        esac
        """,
    )
    _write_executable(
        tool_dir / "id",
        """
        #!/bin/sh
        [ "$1" = -u ] || exit 1
        printf '%s\n' "${FAKE_ID_U:-1000}"
        """,
    )
    _write_executable(
        tool_dir / "sudo",
        """
        #!/bin/sh
        printf '%s\n' "$*" >> "$FAKE_SUDO_LOG"
        exit 99
        """,
    )
    _write_executable(
        tool_dir / "curl",
        """
        #!/usr/bin/env python3
        import json
        import os
        import sys
        from pathlib import Path

        arguments = sys.argv[1:]
        url = next(argument for argument in arguments if argument.startswith("https://"))
        output = None
        for option in ("-o", "--output"):
            if option in arguments:
                output = Path(arguments[arguments.index(option) + 1])
                break
        log = os.environ.get("FAKE_CURL_LOG")
        if log:
            with Path(log).open("a", encoding="utf-8") as stream:
                stream.write(url + "\\n")
        sources = json.loads(os.environ["FAKE_CURL_MAP"])
        source = sources.get(url)
        if source is None:
            raise SystemExit("unexpected URL: " + url)
        content = Path(source).read_bytes()
        if output is None:
            sys.stdout.buffer.write(content)
        else:
            output.parent.mkdir(parents=True, exist_ok=True)
            output.write_bytes(content)
        """,
    )
    _write_executable(
        tool_dir / "ping",
        """
        #!/usr/bin/env python3
        import json
        import os
        import sys

        host = sys.argv[-1]
        latencies = json.loads(os.environ.get("FAKE_PING_LATENCIES", "{}"))
        latency = latencies.get(host)
        if latency is None:
            raise SystemExit("unexpected host: " + host)
        print(f"64 bytes from {host}: time={latency} ms")
        """,
    )
    return tool_dir


def _release_payload(
    version: str, platform_urls: dict[str, list[str]], channel: str = "stable"
) -> dict:
    return {
        "channels": {
            channel: {
                "version": version,
                "download_urls": platform_urls,
            }
        }
    }


def _write_json(path: Path, payload: dict) -> Path:
    path.write_text(json.dumps(payload), encoding="utf-8")
    return path


def _run_installer(
    tmp_path: Path,
    args: list[str],
    sources: dict[str, Path],
    *,
    system: str = "Linux",
    machine: str = "x86_64",
    ping_latencies: dict[str, float] | None = None,
    user_id: int = 1000,
) -> subprocess.CompletedProcess[str]:
    tool_dir = _make_fake_tools(tmp_path)
    temp_dir = tmp_path / "installer-tmp"
    temp_dir.mkdir(exist_ok=True)
    log_path = tmp_path / "curl.log"
    env = os.environ.copy()
    env.update(
        {
            "PATH": f"{tool_dir}{os.pathsep}{env['PATH']}",
            "FAKE_UNAME_S": system,
            "FAKE_UNAME_M": machine,
            "FAKE_ID_U": str(user_id),
            "FAKE_SUDO_LOG": str(tmp_path / "sudo.log"),
            "FAKE_CURL_MAP": json.dumps(
                {url: str(path) for url, path in sources.items()}
            ),
            "FAKE_CURL_LOG": str(log_path),
            "FAKE_PING_LATENCIES": json.dumps(
                ping_latencies
                if ping_latencies is not None
                else {"mirror.iscas.ac.cn": 5.0, "github.com": 20.0}
            ),
            "TMPDIR": str(temp_dir),
        }
    )
    return subprocess.run(
        [str(SCRIPT), *args],
        cwd=SCRIPT.parent,
        env=env,
        text=True,
        capture_output=True,
        check=False,
    )


def _urls(version: str, artifact: str) -> tuple[str, str]:
    asset = f"ruyi-{version}.{artifact}"
    return (
        f"https://mirror.iscas.ac.cn/ruyisdk/ruyi/tags/{version}/{asset}",
        f"https://github.com/ruyisdk/ruyi/releases/download/{version}/{asset}",
    )


@pytest.mark.parametrize(
    ("system", "machine", "platform", "artifact"),
    [
        ("Linux", "x86_64", "linux/x86_64", "amd64"),
        ("Linux", "aarch64", "linux/aarch64", "arm64"),
        ("Linux", "riscv64", "linux/riscv64", "riscv64"),
        ("Darwin", "arm64", "darwin/aarch64", "macos-arm64"),
        ("MINGW64_NT-10.0", "x86_64", "windows/x86_64", "windows-amd64.exe"),
    ],
)
def test_dry_run_resolves_supported_platforms(
    tmp_path: Path,
    system: str,
    machine: str,
    platform: str,
    artifact: str,
) -> None:
    version = "1.2.3"
    mirror_url, github_url = _urls(version, artifact)
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {platform: [github_url, mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
        system=system,
        machine=machine,
    )

    assert result.returncode == 0, result.stderr
    assert f"Selected platform: {platform}" in result.stdout
    assert f"Selected version: {version}" in result.stdout
    assert result.stdout.index(mirror_url) < result.stdout.index(github_url)
    assert not (tmp_path / "bin").exists()


@pytest.mark.parametrize("shell_name", ["bash", "zsh"])
def test_help_runs_in_supported_shells(shell_name: str) -> None:
    shell = shutil.which(shell_name)
    if shell is None:
        pytest.skip(f"{shell_name} is not installed")

    syntax = subprocess.run(
        [shell, "-n", str(SCRIPT)],
        cwd=SCRIPT.parent,
        text=True,
        capture_output=True,
        check=False,
    )
    assert syntax.returncode == 0, syntax.stderr

    result = subprocess.run(
        [shell, str(SCRIPT), "--help"],
        cwd=SCRIPT.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert "sh install.sh [OPTIONS]" in result.stdout
    assert (
        "curl --proto '=https' --tlsv1.2 -fL https://ruyisdk.org/install.sh"
        in result.stdout
    )
    assert "-fsSL" not in result.stdout
    assert "ruyi-install.sh" not in result.stdout
    assert "Default: /usr/local/bin" in result.stdout
    assert "--version" not in result.stdout
    assert "--sha256" not in result.stdout
    assert "--release-api-url" not in result.stdout


def test_download_commands_show_progress_without_custom_timeouts() -> None:
    source = SCRIPT.read_text(encoding="utf-8")

    for option in (
        "--silent",
        "--quiet",
        "--connect-timeout",
        "--max-time",
        "--timeout=",
        "--tries=",
    ):
        assert option not in source


def test_default_install_path_is_usr_local_bin(tmp_path: Path) -> None:
    version = "1.2.3"
    mirror_url, github_url = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [github_url, mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--dry-run"],
        {RELEASE_API_URL: release_file},
    )

    assert result.returncode == 0, result.stderr
    assert "Install path: /usr/local/bin/ruyi" in result.stdout


@pytest.mark.parametrize("primary_payload", [None, {}], ids=["unavailable", "invalid"])
def test_release_metadata_falls_back_to_ruyisdk_org(
    tmp_path: Path, primary_payload: dict | None
) -> None:
    version = "1.2.3"
    mirror_url, github_url = _urls(version, "amd64")
    fallback = _write_json(
        tmp_path / "fallback.json",
        _release_payload(version, {"linux/x86_64": [mirror_url, github_url]}),
    )
    sources = {FALLBACK_RELEASES_URL: fallback}
    if primary_payload is not None:
        sources[RELEASE_API_URL] = _write_json(
            tmp_path / "invalid-primary.json", primary_payload
        )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        sources,
    )

    assert result.returncode == 0, result.stderr
    assert f"Selected version: {version}" in result.stdout
    assert (tmp_path / "curl.log").read_text(encoding="utf-8").splitlines() == [
        RELEASE_API_URL,
        FALLBACK_RELEASES_URL,
    ]
    assert f"metadata from {RELEASE_API_URL} is unavailable or invalid" in result.stderr
    if primary_payload is not None:
        assert "channel stable is missing" in result.stderr


def _build_version_binary(tmp_path: Path, version: str) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("a C compiler is required for executable validation")
    source = tmp_path / "ruyi.c"
    binary = tmp_path / "ruyi.fixture"
    source.write_text(
        textwrap.dedent(
            f"""
            #include <stdio.h>
            #include <string.h>

            int main(int argc, char **argv) {{
                if (argc == 2 && strcmp(argv[1], "version") == 0) {{
                    puts("Ruyi {version}");
                    return 0;
                }}
                return 0;
            }}
            """
        ),
        encoding="utf-8",
    )
    subprocess.run([compiler, str(source), "-o", str(binary)], check=True)
    return binary


def test_api_urls_are_used_in_order_and_bad_download_is_skipped(tmp_path: Path) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, github_url = _urls(version, "amd64")
    bad_file = tmp_path / "bad.bin"
    bad_file.write_bytes(b"not a ruyi executable")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url, github_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin")],
        {
            RELEASE_API_URL: release_file,
            mirror_url: bad_file,
            github_url: binary,
        },
    )

    target = tmp_path / "bin" / "ruyi"
    assert result.returncode == 0, result.stderr
    assert target.exists()
    assert stat.S_IMODE(target.stat().st_mode) & 0o111 == 0o111
    assert target.read_bytes() == binary.read_bytes()
    assert "failed its version check" in result.stderr
    assert result.stdout.index(mirror_url) < result.stdout.index(github_url)
    assert (tmp_path / "curl.log").read_text(encoding="utf-8").splitlines()[-2:] == [
        mirror_url,
        github_url,
    ]
    assert "Ruyi 1.2.3" in result.stdout


def test_download_urls_are_sorted_by_ping_latency(tmp_path: Path) -> None:
    version = "1.2.3"
    mirror_dir = tmp_path / "mirror"
    github_dir = tmp_path / "github"
    mirror_dir.mkdir()
    github_dir.mkdir()
    mirror_binary = _build_version_binary(mirror_dir, version)
    github_binary = _build_version_binary(github_dir, version)
    mirror_url, github_url = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url, github_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin")],
        {
            RELEASE_API_URL: release_file,
            mirror_url: mirror_binary,
            github_url: github_binary,
        },
        ping_latencies={"mirror.iscas.ac.cn": 30.0, "github.com": 5.0},
    )

    target = tmp_path / "bin" / "ruyi"
    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == github_binary.read_bytes()
    assert (tmp_path / "curl.log").read_text(encoding="utf-8").splitlines() == [
        RELEASE_API_URL,
        github_url,
    ]
    assert "Ping github.com: 5.0 ms" in result.stdout
    assert "Ping mirror.iscas.ac.cn: 30.0 ms" in result.stdout


def test_existing_target_is_not_replaced(tmp_path: Path) -> None:
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "ruyi"
    target.symlink_to(tmp_path / "elsewhere")
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {},
    )

    assert result.returncode != 0
    assert "already exists; this installer does not perform upgrades" in result.stderr
    assert target.is_symlink()


def test_invalid_api_version_is_rejected(tmp_path: Path) -> None:
    mirror_url, _ = _urls("1.2", "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.2", {"linux/x86_64": [mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
    )

    assert result.returncode != 0
    assert "invalid semantic version: 1.2" in result.stderr


def test_untrusted_api_url_is_ignored(tmp_path: Path) -> None:
    version = "1.2.3"
    untrusted_url = "https://downloads.example.test/ruyi"
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [untrusted_url, mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
    )

    assert result.returncode == 0, result.stderr
    assert f"ignored unexpected download URL: {untrusted_url}" in result.stderr
    assert untrusted_url not in result.stdout


def test_legacy_macos_api_platform_key_is_supported(tmp_path: Path) -> None:
    version = "1.2.3"
    mirror_url, github_url = _urls(version, "macos-arm64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/macos-arm64": [mirror_url, github_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
        system="Darwin",
        machine="arm64",
    )

    assert result.returncode == 0, result.stderr
    assert "Selected platform: darwin/aarch64" in result.stdout


def test_testing_channel_is_selected_from_same_api(tmp_path: Path) -> None:
    version = "1.2.3-beta.1"
    mirror_url, github_url = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(
            version,
            {"linux/x86_64": [mirror_url, github_url]},
            channel="testing",
        ),
    )
    result = _run_installer(
        tmp_path,
        ["--channel", "testing", "--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
    )

    assert result.returncode == 0, result.stderr
    assert "Selected channel: testing" in result.stdout
    assert f"Selected version: {version}" in result.stdout


@pytest.mark.parametrize("option", ["--version", "--sha256", "--release-api-url"])
def test_removed_override_options_are_rejected(option: str, tmp_path: Path) -> None:
    result = subprocess.run(
        [str(SCRIPT), option, "value"],
        cwd=SCRIPT.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode != 0
    assert f"unknown option: {option}" in result.stderr


def test_noninteractive_system_install_requests_consent_after_validation(
    tmp_path: Path,
) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = "/proc/ruyi-installer-test"
    result = _run_installer(
        tmp_path,
        ["--install-dir", install_dir],
        {
            RELEASE_API_URL: release_file,
            mirror_url: binary,
        },
    )

    assert result.returncode != 0
    assert f"Install path: {install_dir}/ruyi" in result.stdout
    assert "requires interactive sudo consent" in result.stderr
    assert not (tmp_path / "sudo.log").exists()


def test_root_install_does_not_invoke_sudo(tmp_path: Path) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = "/proc/ruyi-installer-root-test"
    result = _run_installer(
        tmp_path,
        ["--install-dir", install_dir],
        {
            RELEASE_API_URL: release_file,
            mirror_url: binary,
        },
        user_id=0,
    )

    assert result.returncode != 0
    assert f"failed to create install directory: {install_dir}" in result.stderr
    assert "sudo" not in result.stderr
    assert not (tmp_path / "sudo.log").exists()
