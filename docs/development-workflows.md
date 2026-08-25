# Development Workflows

This document explains how to extend the project without crossing its existing
ownership boundaries. Each workflow lists the owning files, the expected
implementation sequence, and the focused checks to run.

## Local Environment

Create the locked development environment:

```bash
uv sync --locked --group dev
```

Run the GUI:

```bash
uv run --locked oh-my-ruyi
uv run --locked python -m oh_my_ruyi
```

For local ruyi development without changing project dependency metadata:

```bash
uv run --with-editable /path/to/ruyi oh-my-ruyi
```

The GUI requires a graphical Qt session. Use `QT_QPA_PLATFORM=offscreen` for
tests, not for normal interactive flashing. On Windows, native storage
flashing is unsupported; use WSL2 and attach devices with `usbipd`/`usbip`.

## Local Ruyi Development

The application consumes ruyi's public/internal Python APIs for:

- `GlobalConfig` and repository configuration;
- package atoms and package installation;
- metadata entity traversal;
- provision strategy providers;
- telemetry and release behavior.

When changing ruyi itself:

1. Make the ruyi change in its own checkout.
2. Run Oh My Ruyi with `uv run --with-editable /path/to/ruyi ...`.
3. Compare the relevant CLI flow, usually `ruyi device provision`.
4. Update only the Oh My Ruyi adapter/controller boundary if the GUI needs a
   different presentation.
5. Do not copy ruyi domain rules into a widget to compensate for a missing API.
6. Run adapter, provisioning interaction, and full tests.

`tests/test_packaging.py` protects the normal registry dependency and rejects
machine-local ruyi paths in the lockfile. Do not make a local editable checkout
permanent unless dependency resolution is intentionally part of the change.

## Local Metadata Development

Point ruyi at an absolute metadata tree containing at least:

```text
entities/device/
entities/device-variant/
entities/image-combo/
```

The configuration shape is:

```toml
[repo]
local = "/absolute/path/to/metadata-tree"
```

Use the same metadata with both CLI and GUI:

```bash
uv run --locked ruyi update --repo ruyisdk
uv run --locked ruyi device provision
uv run --locked oh-my-ruyi
```

The GUI's Device page intentionally reports available entity types when the
active repository lacks provisioning entities. Do not add fallback board data
to the GUI; fix or update the ruyi metadata instead.

Repository config behavior belongs to:

- `infra/repo_manager.py` for parsing/display/mutations;
- `ui/views/repo_manager_tab.py` for dialogs and controls;
- `controllers/repo_controller.py` for blocking init/sync;
- `processes/repo_update_child.py` and `repo_news_child.py` for cancellable
  native commands.

## Adding a Repository Preset

Add extra presets in `core/repo_presets.py`. A preset contains a stable ID, a
stable display name, and one or more `RepoSource` options. Keep additional
presets separate from the built-in `ruyisdk` source presets.

Example shape:

```python
RepoPreset(
    "stable-addon-id",
    "Stable addon",
    (
        RepoSource(
            remote="https://example.com/repository.git",
            branch="main",
        ),
    ),
)
```

Rules:

- ID and name are external identifiers; do not rename them casually.
- The first source is the default when a preset is added.
- Additional repositories start disabled.
- Local sources must be absolute paths.
- The built-in `ruyisdk` remains first and cannot be removed.
- Mutations go through ruyi `ConfigEditor`; do not write TOML directly.
- Enabling an active repository can trigger the normal update process.

Run:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_repo_manager.py tests/test_repo_manager_tab.py
```

Add tests for stable identifiers, duplicate handling, default disabled state,
absolute local path validation, enable/update behavior, and default-repository
protection.

## Adding a Locale

The application catalog is a JSON resource under `oh_my_ruyi/locales/`. To add
a locale:

1. Add `<locale>.json` with English source strings as keys.
2. Keep named placeholders exactly identical, including `{version}`, `{path}`,
   `{repo_id}`, and `{package}`.
3. Use `_()` for dynamic strings at creation time.
4. Let `translate_widget_tree()` handle static programmatic properties.
5. Do not translate URLs, paths, repository IDs, package atoms, package names,
   device names, or other external data.
6. Confirm ruyi provides both `argparse.mo` and `ruyi.mo` for the normalized
   locale.
7. Test in an isolated subprocess because locale initialization is process-wide.

Locale resolution uses `LANGUAGE`, `LC_ALL`, `LC_MESSAGES`, then `LANG`; an
encoding suffix such as `.UTF-8` is normalized away. Use:

```bash
LANGUAGE=zh_CN.UTF-8 uv run --locked oh-my-ruyi
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_i18n.py tests/test_packaging.py
```

The locale must reach all layers: Qt standard controls, application strings,
ruyi logger/config, QProcess environments, and raw subprocess environments.
After adding a non-Python resource, run `uv build` and inspect the wheel.

## Adding a Worker

Use a worker for blocking Python work that should run in a QThread. The basic
pattern is:

```python
class ExampleWorker(_BaseWorker):
    def __init__(self, input_value) -> None:
        super().__init__()
        self._input_value = input_value

    @Slot()
    def run(self) -> None:
        try:
            self.finished.emit(do_blocking_work(self._input_value))
        except Exception as exc:  # noqa: BLE001
            self._fail(exc)
```

Implementation checklist:

1. Keep the worker Qt-object-only; never create or mutate a widget.
2. Emit `finished` with the domain result or `failed` with a formatted message.
3. Add `cancelled` and `request_cancel()` when cancellation is meaningful.
4. Make cancellation close network responses or terminate child processes;
   setting a flag alone is insufficient for blocking I/O.
5. Export the worker from `workers/__init__.py` if a controller/view imports it
   through the package.
6. Start it through `WorkerTaskRunner.run_worker()`.
7. Connect result signals in the controller/view's Qt thread.
8. Add success, failure, cancellation, repeated-start, late-signal, and thread
   cleanup tests.

`WorkerTaskRunner` owns the QThread references, connects worker completion to
`thread.quit()`, deletes worker/thread after completion, and removes references
when the thread finishes. Do not create a parallel thread manager.

## Adding a Child Process

Use a child process when the operation needs independent process-group
cancellation, an external command, native terminal behavior, or isolation from
native libraries. A child module should have:

```python
    ...


if __name__ == "__main__":
    raise SystemExit(main())
```

Unix child processes that may spawn descendants should create their own process
group. Validate input paths and action names before touching the filesystem.
Initialize locale/config/logger in the child, and route output through the
parent's configured QProcess environment.

When adding a child:

1. Add the module under `processes/`.
2. Use `configure_qprocess_environment()` on the Qt side.
3. Register its fully qualified name in `__main__._CHILD_MODULES`.
4. Add the child to `_CHILD_MODULES`; the shared PyInstaller spec collects all
   `oh_my_ruyi.processes` submodules.
5. Add normal interpreter and frozen dispatcher tests.
6. Check process identity in the parent before consuming late output/results.

`processes/__init__.py` deliberately does not eagerly import child modules.
Keep it lightweight so a single helper does not initialize every ruyi/pygit2
dependency.

## Modifying the Provisioning Facade

Provisioning changes start in `infra/ruyi_adapter.py`, not in a widget. Keep
the facade Qt-free and delegate domain semantics to ruyi.

For a new metadata field or strategy behavior:

1. Confirm the ruyi API and CLI behavior.
2. Add/adjust a Qt-free adapter function or model conversion.
3. Update `PreparedProvision` consumers together: state, Review, FlashWorker,
   and state-machine predicates.
4. Preserve strategy priority ordering and first-nonzero return behavior.
5. Preserve Rich/plugin output and operation targets.
6. Add adapter tests with a small fake repository/strategy boundary.
7. Add provisioning UI tests for success, failure, stale state, and recovery.

`PreparedProvision` currently contains sorted strategy pairs, package partition
maps, all partition kinds, requested host block devices, and required commands.
Do not create a second preparation object in the UI.

## Modifying Storage or Flashing

Storage changes require a safety-first review:

1. Update platform discovery/topology in `infra/os_storage.py`.
2. Keep discovery in `StorageDiscoveryWorker` on every platform.
3. Record fingerprints at Storage commit.
4. Preserve UI revalidation before Flash where it is safe and fast.
5. Preserve `FlashWorker` preflight and per-`dd` validation.
6. Preserve explicit mounted-device confirmation.
7. Add tests for missing devices, changed fingerprints, new mounts, unknown
   topology, holder relationships, and cancellation.

Run at least:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_os_storage.py tests/test_provision_wizard.py tests/test_main_window.py
```

Never validate only by path string or by a prior UI checkbox. The destructive
command boundary must independently fail closed.

## Debugging Rich Output

Set `RUYI_DEBUG=1` to expose ruyi debug details:

```bash
RUYI_DEBUG=1 uv run --locked oh-my-ruyi
```

Use operation targets `welcome`, `device`, `download`, `flash`, `fastboot`, and
`pm`. For primary output:

- use `RichTextView.feed_bytes()` for bytes;
- use `feed_text()` for decoded terminal text;
- use `append_rich()` for Rich renderables;
- use `append_plain_status()` only for status/error summaries.

Do not flatten Rich output before it reaches the output widget. Do not call
`strip_terminal_controls()` on the primary stream. Flush with `final=True` when
a process finishes. Preserve ANSI links, progress, carriage-return updates,
and merged stdout/stderr ordering.

## Adding Tests for a Change

Choose tests by boundary rather than by file size:

- core state/FSM behavior: state-machine/provisioning tests;
- Qt interaction: pytest-qt tests with `window` fixture;
- worker lifecycle: `test_smoke.py` or owner-focused tests;
- ruyi facade: `test_ruyi_adapter.py` with fake ruyi objects;
- disk safety: `test_os_storage.py` plus provisioning UI tests;
- version lifecycle: `test_version_manager.py` plus version UI tests;
- child/frozen packaging: `test_packaging.py` plus actual build smoke.

Mock network, privilege, disk devices, subprocesses, external commands, and
destructive operations by default. Use isolated subprocesses for locale tests.
When a path is asynchronous, wait for the worker result rather than asserting
immediately after starting it.
