from __future__ import annotations

import json
import os
import shlex
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
INSTALLER_URL = "https://ruyisdk.org/install.sh"


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
        if [ "${1:-}" = -u ] && [ "$#" -ge 2 ]; then
            user=$2
            shift 2
            [ "${1:-}" = -H ] && shift
            FAKE_SUDO_EFFECTIVE_USER=$user
            export FAKE_SUDO_EFFECTIVE_USER
            exec "$@"
        fi
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
                output = arguments[arguments.index(option) + 1]
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
        if output is None or output == "-":
            sys.stdout.buffer.write(content)
        else:
            output = Path(output)
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


def _release_payload(version: str, platform_urls: dict[str, list[str]]) -> dict:
    return {
        "channels": {
            "stable": {
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
    sudo_user: str | None = None,
    binary_magic: str | None = None,
    script_path: Path | None = None,
    interactive_answers: str | None = None,
    input_text: str | None = "y\ny\n",
) -> subprocess.CompletedProcess[str]:
    tool_dir = _make_fake_tools(tmp_path)
    if binary_magic is not None:
        _write_executable(
            tool_dir / "od",
            f"#!/bin/sh\nprintf '%s\\n' {shlex.quote(binary_magic)}\n",
        )
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
    if sudo_user is not None:
        env["SUDO_USER"] = sudo_user
    env.pop("FAKE_SUDO_EFFECTIVE_USER", None)
    command = [str(script_path or SCRIPT), *args]
    if interactive_answers is not None:
        terminal = shutil.which("script")
        if sys.platform != "linux" or terminal is None:
            pytest.skip("interactive installer test requires util-linux script")
        command = [terminal, "-qefc", shlex.join(command), "/dev/null"]
        input_text = interactive_answers
    return subprocess.run(
        command,
        cwd=SCRIPT.parent,
        env=env,
        text=True,
        input=input_text,
        capture_output=True,
        check=False,
        timeout=10,
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
    assert "-v                     Show the installer version" in result.stdout
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
    assert "--channel" not in result.stdout
    assert "RUYI_CHANNEL" not in result.stdout
    assert "--upgrade [HELPER]" not in result.stdout


@pytest.mark.parametrize("shell_name", ["sh", "bash", "zsh"])
@pytest.mark.parametrize("option", ["-v", "--version"])
def test_version_options_report_release_date(shell_name: str, option: str) -> None:
    shell = shutil.which(shell_name)
    if shell is None:
        pytest.skip(f"{shell_name} is not installed")

    result = subprocess.run(
        [shell, str(SCRIPT), option],
        cwd=SCRIPT.parent,
        text=True,
        capture_output=True,
        check=False,
    )

    assert result.returncode == 0, result.stderr
    assert result.stdout == "20260831\n"
    assert result.stderr == ""


def test_metadata_downloads_are_silent_but_binary_downloads_show_progress() -> None:
    source = SCRIPT.read_text(encoding="utf-8")
    fetch_start = source.index("fetch() {")
    fetch_end = source.index("warn_if_path_missing() {")
    fetch_source = source[fetch_start:fetch_end]

    assert "-fsSL" in fetch_source
    assert "-fL" in fetch_source
    assert "-q -O -" in fetch_source
    assert "OVERWRITE" not in source
    assert 'fetch "$release_url" | extract_urls' in source
    assert 'fetch "$url" "$BINARY_FILE"' in source

    for option in (
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


def test_privacy_policy_must_be_accepted_before_metadata_download(
    tmp_path: Path,
) -> None:
    version = "1.2.3"
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--dry-run"],
        {RELEASE_API_URL: release_file},
        input_text="n\n",
    )

    assert result.returncode != 0
    assert "privacy policy not accepted" in result.stderr
    assert not (tmp_path / "curl.log").exists()


def test_existing_target_requires_overwrite_confirmation(tmp_path: Path) -> None:
    version = "1.2.3"
    old_dir = tmp_path / "old"
    new_dir = tmp_path / "new"
    old_dir.mkdir()
    new_dir.mkdir()
    old_binary = _build_version_binary(old_dir, "1.2.2")
    new_binary = _build_version_binary(new_dir, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "ruyi"
    shutil.copy2(old_binary, target)
    old_contents = target.read_bytes()

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {RELEASE_API_URL: release_file, mirror_url: new_binary},
        input_text="y\ny\ny\n",
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == new_binary.read_bytes()
    assert target.read_bytes() != old_contents


def test_declining_target_confirmation_stops_before_metadata_download(
    tmp_path: Path,
) -> None:
    version = "1.2.3"
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "ruyi"
    target.write_bytes(b"existing")

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {RELEASE_API_URL: release_file},
        input_text="y\nn\n",
    )

    assert result.returncode != 0
    assert "installation cancelled" in result.stderr
    assert target.read_bytes() == b"existing"
    assert not (tmp_path / "curl.log").exists()


def test_declining_new_target_confirmation_stops_before_metadata_download(
    tmp_path: Path,
) -> None:
    version = "1.2.3"
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin")],
        {RELEASE_API_URL: release_file},
        input_text="y\nn\n",
    )

    assert result.returncode != 0
    assert "installation cancelled" in result.stderr
    assert not (tmp_path / "curl.log").exists()


def _build_version_binary(
    tmp_path: Path, version: str, *, expected_user: str | None = None
) -> Path:
    compiler = shutil.which("cc")
    if compiler is None:
        pytest.skip("a C compiler is required for executable validation")
    source = tmp_path / "ruyi.c"
    binary = tmp_path / "ruyi.fixture"
    expected_user_literal = (
        json.dumps(expected_user) if expected_user is not None else "NULL"
    )
    source.write_text(
        textwrap.dedent(
            f"""
            #include <stdio.h>
            #include <string.h>
            #include <stdlib.h>

            int main(int argc, char **argv) {{
                if (argc == 2 && strcmp(argv[1], "version") == 0) {{
                    const char *expected_user = {expected_user_literal};
                    if (expected_user != NULL) {{
                        const char *actual_user = getenv("FAKE_SUDO_EFFECTIVE_USER");
                        if (actual_user == NULL
                            || strcmp(actual_user, expected_user) != 0) {{
                            return 2;
                        }}
                    }}
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


def test_sudo_version_check_runs_as_invoking_user(tmp_path: Path) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version, expected_user="alice")
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin")],
        {RELEASE_API_URL: release_file, mirror_url: binary},
        user_id=0,
        sudo_user="alice",
    )

    assert result.returncode == 0, result.stderr
    assert (tmp_path / "bin" / "ruyi").read_bytes() == binary.read_bytes()
    assert "-u alice -H env RUYI_TELEMETRY_OPTOUT=1" in (
        tmp_path / "sudo.log"
    ).read_text(encoding="utf-8")
    assert "RUYI_FORCE_ALLOW_ROOT" not in SCRIPT.read_text(encoding="utf-8")


def _prepare_upgrade_tree(
    tmp_path: Path, current_version: str, *, expected_user: str | None = None
) -> tuple[Path, Path]:
    install_dir = tmp_path / "managed"
    install_dir.mkdir()
    current_dir = tmp_path / "current"
    current_dir.mkdir()
    current_binary = _build_version_binary(
        current_dir, current_version, expected_user=expected_user
    )
    if current_binary.read_bytes()[:4] != b"\x7fELF":
        pytest.skip("ruyi-upgrade only supports ELF binaries")
    target = install_dir / "ruyi"
    shutil.copy2(current_binary, target)
    target.chmod(0o755)
    helper = install_dir / "ruyi-upgrade"
    shutil.copy2(SCRIPT, helper)
    helper.chmod(0o755)
    return helper, target


def test_sudo_upgrade_version_checks_run_as_invoking_user(tmp_path: Path) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3", expected_user="alice")
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_binary = _build_version_binary(new_dir, "1.3.0", expected_user="alice")
    mirror_url, _ = _urls("1.3.0", "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.3.0", {"linux/x86_64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        [],
        {RELEASE_API_URL: release_file, mirror_url: new_binary},
        script_path=helper,
        user_id=0,
        sudo_user="alice",
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == new_binary.read_bytes()


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


@pytest.mark.parametrize("script_source", ["local", "download"])
def test_install_can_store_an_upgrade_helper(
    tmp_path: Path, script_source: str
) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = tmp_path / "bin"
    installer = SCRIPT
    installer_source = tmp_path / "unexpected-installer-download"
    if script_source == "download":
        installer = tmp_path / "pipe-runner"
        _write_executable(
            installer,
            f'#!/bin/sh\nexec sh -c {shlex.quote(SCRIPT.read_text(encoding="utf-8"))} sh "$@"\n',
        )
        installer_source = SCRIPT

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {
            RELEASE_API_URL: release_file,
            mirror_url: binary,
            INSTALLER_URL: installer_source,
        },
        script_path=installer,
        interactive_answers="y\ny\ny\n",
    )

    assert result.returncode == 0, result.stderr
    assert (install_dir / "ruyi").exists()
    helper = install_dir / "ruyi-upgrade"
    assert helper.read_bytes() == SCRIPT.read_bytes()
    curl_log = (tmp_path / "curl.log").read_text(encoding="utf-8")
    assert (INSTALLER_URL in curl_log) == (script_source == "download")


def test_existing_upgrade_helper_requires_overwrite_confirmation(
    tmp_path: Path,
) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    helper = install_dir / "ruyi-upgrade"
    helper.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
    helper.chmod(0o755)

    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {RELEASE_API_URL: release_file, mirror_url: binary},
        input_text="y\ny\ny\n",
    )

    assert result.returncode == 0, result.stderr
    assert helper.read_bytes() == SCRIPT.read_bytes()
    assert f"Overwrite {helper}?" in result.stderr
    source = SCRIPT.read_text(encoding="utf-8")
    assert source.index(
        "confirm_install_target\nconfirm_upgrade_helper"
    ) < source.index("fetch_release_data ||")


@pytest.mark.parametrize("entry_point", ["helper", "option"])
def test_ruyi_upgrade_entry_points_update_without_recursing(
    tmp_path: Path, entry_point: str
) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3")
    args: list[str] = []
    if entry_point == "option":
        helper = helper.with_name("upgrade-helper")
        helper.with_name("ruyi-upgrade").rename(helper)
        args = ["--upgrade"]
    helper_content = helper.read_bytes()
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_binary = _build_version_binary(new_dir, "1.3.0")
    mirror_url, github_url = _urls("1.3.0", "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.3.0", {"linux/x86_64": [mirror_url, github_url]}),
    )

    result = _run_installer(
        tmp_path,
        args,
        {
            RELEASE_API_URL: release_file,
            mirror_url: new_binary,
        },
        script_path=helper,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == new_binary.read_bytes()
    assert helper.read_bytes() == helper_content
    assert "Ruyi 1.3.0 was installed successfully" in result.stdout


def test_ruyi_upgrade_uses_stable_for_prerelease_current_binary(
    tmp_path: Path,
) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3-beta.1")
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_binary = _build_version_binary(new_dir, "1.2.3")
    mirror_url, _ = _urls("1.2.3", "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.2.3", {"linux/x86_64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        [],
        {
            RELEASE_API_URL: release_file,
            mirror_url: new_binary,
        },
        script_path=helper,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == new_binary.read_bytes()


@pytest.mark.parametrize("new_version", ["1.2.3", "1.2.2"])
def test_ruyi_upgrade_skips_when_api_version_is_not_newer(
    tmp_path: Path, new_version: str
) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3")
    original = target.read_bytes()
    mirror_url, _ = _urls(new_version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(new_version, {"linux/x86_64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        [],
        {RELEASE_API_URL: release_file},
        script_path=helper,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == original
    assert "no upgrade is needed" in result.stdout
    assert (tmp_path / "curl.log").read_text(encoding="utf-8").splitlines() == [
        RELEASE_API_URL
    ]


def test_ruyi_upgrade_accepts_macho_target(tmp_path: Path) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3")
    new_dir = tmp_path / "new"
    new_dir.mkdir()
    new_binary = _build_version_binary(new_dir, "1.3.0")
    mirror_url, _ = _urls("1.3.0", "macos-arm64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.3.0", {"darwin/aarch64": [mirror_url]}),
    )

    result = _run_installer(
        tmp_path,
        [],
        {RELEASE_API_URL: release_file, mirror_url: new_binary},
        system="Darwin",
        machine="arm64",
        binary_magic="cf fa ed fe",
        script_path=helper,
    )

    assert result.returncode == 0, result.stderr
    assert target.read_bytes() == new_binary.read_bytes()


def test_ruyi_upgrade_requires_a_supported_target_before_fetching_metadata(
    tmp_path: Path,
) -> None:
    install_dir = tmp_path / "managed"
    install_dir.mkdir()
    target = install_dir / "ruyi"
    target.write_bytes(b"not a supported binary")
    helper = install_dir / "ruyi-upgrade"
    shutil.copy2(SCRIPT, helper)
    helper.chmod(0o755)

    result = _run_installer(
        tmp_path,
        [],
        {},
        script_path=helper,
    )

    assert result.returncode != 0
    assert "upgrade target is not an ELF or Mach-O executable" in result.stderr
    assert not (tmp_path / "curl.log").exists()


def test_upgrade_flag_with_any_script_name_ignores_install_directory(
    tmp_path: Path,
) -> None:
    helper, target = _prepare_upgrade_tree(tmp_path, "1.2.3")
    explicit_helper = helper.with_name("upgrade-helper")
    helper.rename(explicit_helper)
    explicit_helper.chmod(0o755)
    mirror_url, _ = _urls("1.3.0", "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload("1.3.0", {"linux/x86_64": [mirror_url]}),
    )
    other_dir = tmp_path / "other"
    result = _run_installer(
        tmp_path,
        [
            "--upgrade",
            "--install-dir",
            str(other_dir),
            "--dry-run",
        ],
        {RELEASE_API_URL: release_file},
        script_path=explicit_helper,
    )

    assert result.returncode == 0, result.stderr
    assert f"Install path: {target}" in result.stdout
    assert str(other_dir) not in result.stdout
    assert target.exists()
    assert not other_dir.exists()


def test_upgrade_attached_value_is_rejected(
    tmp_path: Path,
) -> None:
    result = _run_installer(tmp_path, ["--upgrade=/tmp/helper"], {})

    assert result.returncode != 0
    assert "unknown option: --upgrade=/tmp/helper" in result.stderr


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


def test_existing_symlink_is_replaced_after_confirmation(tmp_path: Path) -> None:
    version = "1.2.3"
    binary = _build_version_binary(tmp_path, version)
    mirror_url, _ = _urls(version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/x86_64": [mirror_url]}),
    )
    install_dir = tmp_path / "bin"
    install_dir.mkdir()
    target = install_dir / "ruyi"
    target.symlink_to(tmp_path / "elsewhere")
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(install_dir)],
        {RELEASE_API_URL: release_file, mirror_url: binary},
        input_text="y\ny\n",
    )

    assert result.returncode == 0, result.stderr
    assert not target.is_symlink()
    assert target.read_bytes() == binary.read_bytes()


@pytest.mark.parametrize(
    "invalid_version", ["1.2", "1.2.3-beta.1", "1.2.3+build"]
)
def test_invalid_api_version_is_rejected(
    tmp_path: Path, invalid_version: str
) -> None:
    mirror_url, _ = _urls(invalid_version, "amd64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(invalid_version, {"linux/x86_64": [mirror_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file},
    )

    assert result.returncode != 0
    assert f"invalid semantic version: {invalid_version}" in result.stderr


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


def test_legacy_macos_api_platform_key_is_rejected(tmp_path: Path) -> None:
    version = "1.2.3"
    mirror_url, github_url = _urls(version, "macos-arm64")
    release_file = _write_json(
        tmp_path / "release.json",
        _release_payload(version, {"linux/macos-arm64": [mirror_url, github_url]}),
    )
    result = _run_installer(
        tmp_path,
        ["--install-dir", str(tmp_path / "bin"), "--dry-run"],
        {RELEASE_API_URL: release_file, FALLBACK_RELEASES_URL: release_file},
        system="Darwin",
        machine="arm64",
    )

    assert result.returncode != 0
    assert "platform darwin/aarch64 is missing" in result.stderr
    assert not (tmp_path / "bin").exists()


@pytest.mark.parametrize("option", ["--channel", "--sha256", "--release-api-url"])
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
