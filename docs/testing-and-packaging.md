# Testing and Packaging

This document is the verification matrix for Oh My Ruyi. It explains what each
check proves, which boundaries must be mocked, how asynchronous Qt tests are
structured, and how to inspect wheel and frozen release artifacts.

## Test Environment

The supported development interpreters are Python 3.11 and 3.12. CI runs both
on Linux and macOS. The project uses `uv.lock`; normal contributor verification
must use `--locked`.

Headless Qt tests require:

```bash
QT_QPA_PLATFORM=offscreen
```

`tests/conftest.py` sets this default and pins `LANGUAGE`, `LANG`, `LC_ALL`, and
`LC_MESSAGES` to `C`. Locale behavior is tested in isolated subprocesses in
`tests/test_i18n.py`, because `i18n.initialize()` is process-wide and immutable
after first use.

The shared `window` fixture creates a real `QApplication`, a `GlobalConfig`,
`QtRuyiLogger`, temporary version/config paths, and an offscreen
`ProvisionMainWindow`. It disables the About bundled probe unless the About
test explicitly owns that behavior.

## Verification Matrix

| Command | Purpose | Typical scope |
| --- | --- | --- |
| `uv lock --check` | Ensure lockfile matches project metadata | Dependency/source changes |
| `uv run --locked ruff check oh_my_ruyi tests` | Lint/import/name errors | Every code change |
| `uv run --locked ruff format --check oh_my_ruyi tests` | Formatting contract | Every code change |
| `uv run --locked python -m compileall -q oh_my_ruyi tests` | Syntax/bytecode compilation | Every code change |
| `QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q` | Full Qt and boundary suite | Before commit |
| `uv build` | Hatchling sdist/wheel construction | Packaging/resource changes and before commit |
| PyInstaller command below | Frozen release build | Release entry/process/dependency changes |

The normal pre-commit command set is:

```bash
uv lock --check
uv run --locked ruff check oh_my_ruyi tests
uv run --locked ruff format --check oh_my_ruyi tests
uv run --locked python -m compileall -q oh_my_ruyi tests
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
uv build
```

## Focused Test Map

### Smoke and threading

`tests/test_smoke.py` covers package imports, logger signal routing, Rich
renderables/links, ANSI chunking/progress, main-window construction, fastboot
argument formatting, and `WorkerTaskRunner` thread ownership.

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_smoke.py
```

The worker-thread test must verify `QThread.currentThread()` is not the Qt
application thread and that active thread references are cleared after finish.

### Provisioning and main-window interactions

`tests/test_provision_wizard.py` covers:

- sidebar navigation and downstream invalidation;
- page sizing/accessibility/theme behavior;
- download log byte streams and carriage-return progress;
- package preparation and transitions to Storage/Review;
- fastboot success/failure/device-output handling;
- storage selection, async discovery and refresh preservation;
- mounted confirmation and fingerprint replacement;
- FlashWorker cancellation, command validation, and preflight checks;
- Rich Review and prompt rendering;
- Flash recovery/retry/review/start-over.

`tests/test_main_window.py` covers tab composition, repository init busy state,
disabled default repo handling, empty metadata details, and provision-update
start timing.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_provision_wizard.py tests/test_main_window.py
```

### Core infrastructure

`tests/test_os_storage.py` covers Linux holder relationships, mounted source
parsing, Btrfs groups, Linux fingerprints, macOS diskutil/APFS topology,
IORegistry fallback, malformed plist handling, sorting, and platform hints.

`tests/test_ruyi_adapter.py` covers active `ruyisdk` filtering, repository
isolation, sync reload, missing default repo failure, and the real
`PreparedProvision` strategy-field contract.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_os_storage.py tests/test_ruyi_adapter.py
```

### Repository UI and child processes

`tests/test_repo_manager.py` covers config parsing, ConfigEditor mutations,
default-repo ordering/protection, source validation, and preset rules.

`tests/test_repo_manager_tab.py` covers table interactions, dialog validation,
repository update child arguments/output/cancellation, news actions, and
external busy state.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_repo_manager.py tests/test_repo_manager_tab.py
```

### Version and first-use flows

`tests/test_version_manager.py` covers release parsing/catalog fallback,
architecture detection, atomic downloads, response cancellation, activation
backup naming, managed/unmanaged link behavior, deletion safeguards, PATH
inspection, and telemetry commands.

`tests/test_version_management_ui.py` covers available/installed tables, URL
selection/retry/cancel, architecture filtering, activation/deactivation/delete,
unmanaged backup confirmation, PATH status, telemetry choices, and status
rendering.

`tests/test_first_use.py` covers the offer predicate and first-use dialog.
`tests/test_first_use_flow.py` covers catalog selection, skip, download/activate
reuse, repository update completion, exit cancellation, and activation cancel.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_first_use.py tests/test_first_use_flow.py \
  tests/test_version_manager.py tests/test_version_management_ui.py
```

### Localization and packaging metadata

`tests/test_i18n.py` uses isolated subprocesses to verify locale precedence,
catalog gating, normalized locale names, Qt translations, ruyi output,
QProcess environment, Rich progress, dynamic placeholders, and unsupported
locale fallback.

`tests/test_packaging.py` checks project identity, registry ruyi dependency,
absence of machine-local lockfile paths, wheel resource expectations, and the
frozen `__main__` dispatcher argument contract.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_i18n.py tests/test_packaging.py
```

## Mocking Rules

Unit and UI tests must mock these boundaries unless the test is explicitly an
integration test:

- network requests and release downloads;
- Git repository operations and metadata updates;
- sudo/password prompts and privileged helpers;
- `/usr/local/bin/ruyi` and managed version directories;
- disk discovery, mount topology, and fingerprints;
- `dd`, `fastboot`, shell commands, and process groups;
- telemetry network/PTY operations.

Use `tmp_path` for filesystem state. Use `monkeypatch` at the module where the
code under test resolves the dependency. For QProcess tests, use a temporary
executable script and wait with `qtbot.waitUntil()` for process completion.
Never let tests write a real device or the host's activation path.

## Asynchronous Test Rules

Starting a worker or QProcess does not mean the operation is complete. Tests
must wait for the result signal or an observable state change:

```python
window._populate_storage()
qtbot.waitUntil(lambda: window._worker is None, timeout=1000)
```

When checking a refresh operation, first wait for the initial discovery before
starting the second one. When checking a cancellation, assert both the immediate
UI state and the eventual worker/process cleanup.

Tests that call a worker's private callback directly should still cover the
real worker path elsewhere. In particular, do not mock `prepare_provision()` in
every provisioning test; at least one adapter test must construct the real
`PreparedProvision` shape.

## Wheel Inspection

Build the wheel:

```bash
uv build
```

At minimum inspect that the wheel contains:

```text
oh_my_ruyi/__main__.py
oh_my_ruyi/locales/zh_CN.json
```

For a local check:

```bash
python - <<'PY'
from pathlib import Path
import zipfile

wheel = sorted(Path("dist").glob("*.whl"))[-1]
with zipfile.ZipFile(wheel) as archive:
    names = set(archive.namelist())
required = {"oh_my_ruyi/__main__.py", "oh_my_ruyi/locales/zh_CN.json"}
missing = required - names
if missing:
    raise SystemExit(f"missing wheel resources: {sorted(missing)}")
print(f"checked {wheel}")
PY
```

If a resource is added, inspect the built wheel rather than relying only on
source-tree imports.

## PyInstaller Release Build

The tag workflow builds a one-file executable on Debian and macOS. The command
is:

```bash
uv run --locked --with pyinstaller pyinstaller --clean --onefile \
  oh-my-ruyi.spec
```

The spec sets the project path, collects application resources, includes every
`oh_my_ruyi.processes` child module selected dynamically by the frozen
dispatcher, and explicitly includes `_cffi_backend`, which is required by
pygit2/cffi and is not reliably inferred from dynamic ruyi imports.

Use temporary `--workpath`, `--distpath`, and `--specpath` directories while
testing locally so generated specs/build output do not enter the repository.

## Frozen Runtime Smoke Tests

After building, run a helper that does not require a real repository:

```bash
QT_QPA_PLATFORM=offscreen ./dist/oh-my-ruyi \
  -m oh_my_ruyi.processes.version_activation_child --help
```

The tag workflow runs additional frozen checks before uploading artifacts. It
checks `-m ruyi version`, the activation child, repository child argument
validation, and a GUI process that remains alive for the smoke interval. A
`ModuleNotFoundError` from any dynamic child import fails the workflow.

Exercise ruyi's version query through the same dispatcher:

```bash
QT_QPA_PLATFORM=offscreen ./dist/oh-my-ruyi -m ruyi version
```

The expected result is a version report or a normal ruyi configuration error,
not a recursive GUI launch, `ModuleNotFoundError`, or PyInstaller import error.
The version query uses argv0 `ruyi` internally so ruyi does not enter toolchain
mux mode.

## CI and Platform Differences

`.github/workflows/ci.yml` runs lint, format, compilation, wheel build, and the
offscreen suite on Linux/macOS and Python 3.11/3.12. The tag workflow builds
release binaries with Python 3.12 on Debian 12 and macOS 14.

The separate Debian compatibility workflow, if present, uses system Python and
xcb rather than the offscreen test setup. Native Windows storage flashing is
not a supported CI scenario; WSL2 behavior is covered by platform guards and
manual validation.

PyInstaller may report an optional missing Qt image-format library on a local
Linux host. Distinguish that environment warning from fatal missing Python
modules or failure of the frozen child-dispatch smoke tests.

## Pre-Commit Checklist

Before committing:

1. Run the focused tests for the owning boundary.
2. Run lint, format, compile, lock, and full offscreen tests.
3. Run `uv build` when Python resources, entrypoints, or metadata change.
4. Run the PyInstaller build and frozen helper smoke tests for release/entrypoint
   changes.
5. Inspect `git diff --check` and `git status --short`.
6. Do not stage `build/`, generated specs, `dist/`, local paths, secrets, or
   unrelated user changes.
