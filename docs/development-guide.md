# Development Guide

This guide covers local development, architecture, testing, packaging, and
extension points for Oh My Ruyi. User-facing setup and operation remain in the
[project README](../README.md).

## Documentation for Humans and AI Agents

This is the human-oriented development reference. It explains the project
structure and how to extend and verify the application.

The root-level [`AGENTS.md`](../AGENTS.md) is the compact pre-change context
for coding agents. It records module ownership, architecture contracts,
destructive-operation safeguards, localization rules, and required checks.
Keep explanatory workflows here and durable, actionable constraints in
`AGENTS.md`; avoid maintaining two independent descriptions of one detail.

## Prerequisites

- Python 3.11 or 3.12.
- `uv` for dependency management, locked environments, and package builds.
- A graphical Qt session for interactive use.
- The Qt runtime libraries required by PySide6 on the host platform.

On Debian and Ubuntu, CI installs the Qt runtime libraries listed in
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml). The separate Debian
compatibility workflow tests Debian 12 and 13 with the system Python and the
xcb platform plugin.

## Environment Setup

Create the locked development environment:

```bash
uv sync --locked --group dev
```

Run the application from a graphical session:

```bash
uv run --locked oh-my-ruyi
```

The equivalent module entry point is:

```bash
uv run --locked python -m oh_my_ruyi
```

The `ruyi` dependency normally comes from the configured Python package index.
A sibling source checkout is not required. To test an intentional local ruyi
change without modifying `pyproject.toml` or `uv.lock`, run:

```bash
uv run --with-editable /path/to/ruyi oh-my-ruyi
```

## Architecture

Oh My Ruyi is a programmatic PySide6 application. It imports ruyi's Python
APIs for metadata, configuration, package installation, and provisioning rather
than reproducing those domain rules in the GUI.

The main boundaries are:

- `app/bootstrap.py` initializes locale routing, creates ruyi's global
  configuration, and starts `QApplication` and the main window.
- `app/services/` contains application-facing services used by controllers and
  views.
- `controllers/` coordinates repository and provisioning workflows.
- `ui/views/main_window.py` owns the top-level tabs and provisioning flow.
- `ui/views/repo_manager_tab.py` owns repository configuration and update
  interactions; `ui/views/about_tab.py` reports runtime information.
- `core/state.py`, `core/state_machine.py`, and `core/models.py` contain the
  mutable provisioning state, transitions, and domain models.
- `infra/ruyi_adapter.py` is the Qt-free boundary over imported ruyi
  provisioning APIs.
- `infra/version_manager.py` handles release discovery, standalone binary
  downloads, activation, deactivation, deletion, PATH inspection, and
  telemetry setup.
- `infra/repo_manager.py` reads repository configuration for display and
  applies mutations through ruyi's configuration editor.
- `infra/os_storage.py` owns platform-specific disk discovery, mount checks,
  and device fingerprints.
- `workers/` wraps blocking operations in QObjects that run on QThreads;
  `processes/` contains isolated child-process entry points.
- `ui/widgets/qt_logger.py` and `ui/widgets/rich_output.py` preserve ruyi's
  Rich output, links, progress updates, and operation-specific routing.
- `i18n.py` coordinates application, Qt, imported ruyi, and subprocess locale
  selection.

## Threading and Process Model

Do not run repository I/O, release downloads, disk discovery, package work, or
flashing directly on the Qt UI thread.

Most blocking Python operations use workers from `workers/workers.py`. A worker
emits a result or failure signal and is moved to a fresh QThread by the worker
manager. The owning controller or view performs cleanup and UI state changes on
the Qt thread.

Operations needing independent cancellation or native terminal behavior use
child processes, including package download and installation, repository
updates and news, and version activation helpers.

QProcess environments must use `apply_qprocess_locale()`. Standard subprocess
environments must include `locale_environment()` so GUI and ruyi output do not
select different languages.

## First-use Setup Flow

The first-use setup is offered only when all of these conditions hold:

1. Ruyi's telemetry `installation.json` is absent.
2. No executable named `ruyi` outside the running Python environment resolves
   on `PATH`.
3. Oh My Ruyi's managed data directory is absent.

The predicate in `ui/views/first_use.py` uses ruyi's XDG helper for the first
and third paths. Linux defaults live under `~/.local/`; macOS defaults live
under `~/Library/Application Support/`. The PATH check ignores the directory
containing `sys.executable` so this application's bundled console script does
not suppress setup, while still searching later PATH entries for an external
installation. A failed or cancelled initial download must not leave an empty
managed data directory that suppresses the next offer.

`FirstUseDialog` renders steps and exposes user actions. The main-window flow
reuses the normal version download, activation, and repository update paths:

1. Fetch the release catalog and offer the newest compatible stable entry,
   falling back to another compatible channel when stable is unavailable.
2. Reuse `_VersionDownloadDialog` and the version workers for download and
   activation, including URL selection, progress, retry, cancellation, and
   unmanaged-path backup confirmation.
3. Switch to Repository Management and use its default `ruyisdk` source update.
4. After a successful update, switch to About without starting provisioning.

The user may skip the download or exit setup. Exiting cancels active work
through the existing cancellation paths and does not weaken process cleanup or
privilege safeguards.

## Provisioning Flow

The GUI mirrors `ruyi device provision` while keeping each interaction in a Qt
page:

1. Initialize or sync the configured ruyi metadata repository.
2. Select a device, variant, and image combo from ruyi metadata.
3. Customize package versions when useful alternatives exist.
4. Download and install package artifacts.
5. Build a `PreparedProvision` from ruyi's strategy provider.
6. Collect and validate required host block-device paths.
7. Display the strategy's pretend output and required commands.
8. Run the strategy through the flash worker, forwarding plugin prompts to Qt.
9. Display the translated post-install message and final status.

`WizardState` is invalidated when the user moves back to an earlier step. New
state must not survive if its inputs have changed.

## Repository Management

TOML is parsed directly only for ordered display and validation. Mutations must
go through ruyi's `ConfigEditor`; do not add a second TOML writer.

The built-in `ruyisdk` entry remains first and cannot be removed. Additional
repositories come from `core/repo_presets.py`, start disabled, and retain their
preset IDs and names. Update and news output is rendered through the same Rich
terminal view used elsewhere in the application.

## Storage Safety

The selected storage path is not trusted by name alone. Its fingerprint is
recorded at review time and checked again before flashing and at each actual
`dd` invocation. Mounted targets require explicit confirmation, and Linux
checks follow holder relationships for device-mapper, LUKS, LVM, and RAID
stacks. A UI confirmation is not a substitute for revalidation at the
destructive command boundary.

## Rich Output

Imported ruyi APIs may write strings, Rich renderables, links, progress output,
or carriage-return updates. Route output through `QtRuyiLogger` or a
`RichTextView`; do not flatten it to plain text before rendering.

Terminal output is tagged with an operation target such as `welcome`, `device`,
`download`, `flash`, or `fastboot`. This prevents delayed worker output from
appearing in a newer operation's view.

## Localization

The application currently routes Chinese translations for `zh_CN.UTF-8`.
Locale resolution follows gettext precedence: `LANGUAGE`, `LC_ALL`,
`LC_MESSAGES`, then `LANG`. A locale is activated only when Oh My Ruyi has an
application catalog and ruyi supplies both required gettext domains.

Application strings use the gettext-style `_()` helper from `i18n.py`. Static
programmatic widget properties are translated by `translate_widget_tree()`;
dynamic text must call `_()` when it is created. Do not translate repository
IDs, URLs, paths, package atoms, package names, device names, or other external
data. Keep placeholder names identical in source and translation, and update
`tests/test_i18n.py` for routing or subprocess behavior changes.

## Local Metadata Development

Point ruyi at a metadata tree containing `device`, `device-variant`, and
`image-combo` entities:

```toml
[repo]
local = "/absolute/path/to/ruyinews"
```

Use an absolute path. The GUI reloads the same repository configuration and
metadata objects used by the CLI, so validate metadata behavior with both the
GUI and `ruyi device provision`.

## Tests and Quality Checks

Run the same core checks as CI:

```bash
uv lock --check
uv run --locked ruff check oh_my_ruyi tests
uv run --locked ruff format --check oh_my_ruyi tests
uv run --locked python -m compileall -q oh_my_ruyi tests
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
uv build
```

For focused UI and locale runs:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_smoke.py
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_i18n.py
```

Use `pytest-qt` for widget interactions and asynchronous signals. Keep network,
filesystem, privilege, and destructive-command boundaries mocked unless a test
is explicitly an integration test.

## CI, Packaging, and Project Layout

CI tests Python 3.11 and 3.12 on Linux and macOS, checking the lockfile, Ruff,
formatting, compilation, package construction, and the full offscreen suite.
The wheel is built by Hatchling through `uv build`; inspect it after adding a
non-Python resource rather than assuming the resource was included.

The main package layout is:

```text
oh_my_ruyi/
  app/            application bootstrap and services
  controllers/    workflow coordination
  core/           domain models, state, and presets
  infra/          ruyi, repository, version, and storage boundaries
  processes/      isolated child-process entry points
  ui/             views, viewmodels, widgets, and styles
  workers/        QThread workers and lifecycle management
tests/            focused service, UI, and integration-boundary tests
```

## Change Checklist

Before opening a pull request:

1. Keep domain logic in ruyi or the existing service/facade boundary, not Qt
   event handlers.
2. Keep blocking work off the UI thread.
3. Preserve cancellation, process cleanup, and storage revalidation paths.
4. Add focused tests proportional to behavior and blast radius.
5. Run the full CI command set above.
6. Check `git diff` for generated files, local paths, and unrelated changes.