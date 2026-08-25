# Development Guide

This guide covers local development, architecture, testing, packaging, and
extension points for Oh My Ruyi. User-facing setup and operation remain in the
[project README](../README.md).

Detailed topic references:

- [Architecture](architecture.md) for ownership, compatibility imports, state,
  worker lifecycle, and output routing.
- [Development Workflows](development-workflows.md) for adding policies,
  widgets, workers, child processes, adapters, presets, and locales.
- [Operations And Safety](operations-and-safety.md) for storage, flashing,
  activation, first-use, repository, and localization invariants.
- [Testing And Packaging](testing-and-packaging.md) for test ownership, mocks,
  CI commands, wheels, and frozen builds.

## Documentation for Humans and AI Agents

This guide is the human-oriented development reference: it explains why the
project is structured as it is, how to set up a development environment, and how
to extend and verify the application.

The repository also contains a root-level [`AGENTS.md`](../AGENTS.md). Coding
agents can discover that file before making changes and use it as a compact map
of module ownership, architecture contracts, destructive-operation safeguards,
localization rules, and required checks. Agents should read both documents:
`AGENTS.md` is the pre-change checklist, while this guide supplies the detailed
context behind it.

When project conventions change, update the appropriate layer in the same
change. Put explanatory workflows here and put durable, actionable constraints
that an agent must know before editing in `AGENTS.md`. Avoid maintaining two
independent descriptions of the same implementation detail.

## Prerequisites

- Python 3.11 or 3.12.
- `uv` for dependency management, locked environments, and package builds.
- A graphical Qt session for interactive use.
- The Qt runtime libraries required by PySide6 on the host platform.

On Debian and Ubuntu, CI installs the Qt runtime libraries listed in
[`.github/workflows/ci.yml`](../.github/workflows/ci.yml). The separate
[Debian compatibility workflow](../.github/workflows/debian-compat.yml) tests
Debian 12 and 13 with the system Python and the xcb platform plugin.

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

- `app.py` initializes locale routing, creates ruyi's `GlobalConfig`, and starts
  `QApplication` and the main window.
- `main_window.py` owns the top-level tabs, version management, and the device
  provisioning state machine.
- `core/state.py` owns the Qt-free mutable wizard scratchpad and invalidation
  methods. The flat `state.py` file is a compatibility import.
- `core/first_use_policy.py` owns the pure first-launch eligibility predicate;
  `first_use.py` owns the setup dialog and re-exports the predicate.
- `core/formatting.py` owns shared byte-size formatting. Existing private
  helpers in storage and version views call it so their import paths remain
  stable.
- `core/repo_presets.py` owns immutable preset data; `repo_presets.py` remains a
  compatibility import.
- `ui/common.py` owns shared Qt constants, translated message boxes, semantic
  version table sorting, and the common table selection/header policy.
  `ui/version_dialogs.py`,
  `ui/repo_dialogs.py`, and `ui/first_use_dialog.py` own reusable dialogs;
  they expose only signals and display/state methods, never workers or I/O.
- `ui/version_tables.py` owns release and installed-version table rendering;
  the main window supplies data and theme brushes and keeps orchestration.
- `ui/theme.py` owns palette-derived semantic colors and stylesheet text;
  `main_window.py` only applies the stylesheet and keeps the palette wrapper
  for compatibility.
- `ui/repo_tables.py` owns repository table rendering; `RepoManagementTab`
  still owns selection, mutations, and update processes.
- `ui/provision_pages.py` owns provisioning page construction and callback
  wiring; `ProvisionMainWindow` keeps the returned widget references and owns
  all state transitions.
- `ui/version_manager_panels.py` owns the standalone ruyi version page and its
  panel controls; `ProvisionMainWindow` assigns the returned controls before
  refreshing data and keeps all release/activation orchestration.
- `ui/repo_page.py` owns repository panel construction and callback wiring;
  `RepoManagementTab` retains its old private builders as thin compatibility
  wrappers and owns repository mutations and QProcess lifecycle.
- `ui/about_page.py` owns the About page's read-only widget tree;
  `AboutTab` retains runtime version probes and telemetry calculation.
- `processes/environment.py` centralizes the common QProcess locale, Rich
  terminal, buffering, and telemetry flags. The caller remains responsible for
  creating and configuring its own QProcess.
- `repo_manager_tab.py` owns repository configuration and update interactions.
- `about_tab.py` reports application, bundled ruyi, PATH ruyi, and telemetry
  information.
- `core/state.py` contains the mutable state accumulated across provisioning
  steps; `state.py` is a compatibility import.
- `ruyi_facade.py` is the Qt-free boundary over imported ruyi provisioning APIs.
- `version_manager.py` handles release discovery, standalone binary downloads,
  activation, deactivation, deletion, PATH inspection, and telemetry setup.
- `repo_manager.py` reads repository configuration for display and applies
  mutations through ruyi's configuration editor.
- `host_storage.py` owns platform-specific disk discovery, mount checks, and
  device fingerprints.
- `worker_services.py` wraps repository, storage, release, activation, and
  telemetry operations in QObjects that run on QThreads. `workers.py` owns the
  flashing interception boundary and re-exports the service workers for
  compatibility; `worker_runtime.py` centralizes queued startup and cleanup.
- `qt_logger.py` and `rich_output.py` preserve ruyi's Rich output, links,
  progress updates, and operation-specific routing in Qt views.
- `i18n.py` coordinates application, Qt, imported ruyi, and subprocess locale
  selection.
- `ui/first_use_dialog.py` owns the non-modal setup step/status dialog;
  `first_use.py` keeps compatibility exports for the dialog and pure detection
  predicate from `core/first_use_policy.py`; `main_window.py` owns transitions
  and reuses existing version and repository operations.
- `processes/*.py` owns child-process command adapters. Flat child modules remain
  compatibility wrappers for existing `python -m` and QProcess callers.

## Threading and Process Model

Do not run repository I/O, release downloads, disk discovery, package work, or
flashing directly on the Qt UI thread.

Most blocking Python operations use workers from `worker_services.py`; the
flashing interception remains in `workers.py`. A worker emits a result or
failure signal and is moved to a fresh QThread by
`worker_runtime.start_worker()` through `run_worker_in_thread()`. The main
window owns cleanup and UI state changes; `worker_runtime.stop_thread()` gives
all worker owners the same quit-and-wait behavior.

Operations that need independent cancellation or native terminal behavior use
child processes:

- `processes/download_child.py` runs package download and installation.
- `processes/repo_update_child.py` runs one repository update.
- `processes/repo_news_child.py` reads or marks repository news.
- `version_manager.py` runs privileged activation helpers and ruyi's telemetry
  OOBE in a pseudo-terminal.

QProcess environments must use `apply_qprocess_locale()`. Standard subprocess
environments must include `locale_environment()` so GUI and ruyi output do not
select different languages.

## First-use Setup Flow

The first-use setup is offered only when all of these conditions hold:

1. ruyi's telemetry `installation.json` is absent.
2. No executable named `ruyi` outside the running Python environment resolves on
   `PATH`.
3. Oh My Ruyi's managed data directory is absent.

The first and third paths come from ruyi's XDG helper, so Linux defaults live
under `~/.local/` while macOS defaults live under `~/Library/Application Support/`.

`core.first_use_policy.should_offer_first_use_setup()` owns this predicate. It is
re-exported by `first_use.py` for compatibility. Do not replace it
with a separate completion marker: the file-system and PATH state are the
contract. The PATH check removes the directory containing `sys.executable` before
searching so the ruyi console script installed as Oh My Ruyi's Python dependency
does not suppress the setup; it must continue searching later PATH entries for a
real external installation. A cancelled or failed initial download must not
leave an empty managed data directory that suppresses the next launch's offer.

`FirstUseDialog` only renders current and remaining steps and exposes user
actions. `ProvisionMainWindow` owns the orchestration:

1. Fetch the existing release catalog and offer the newest compatible `stable`
   entry, falling back to another compatible channel when stable is unavailable.
2. Reuse `_VersionDownloadDialog`, `VersionDownloadWorker`, and
   `VersionActivationWorker` to download and activate the selected binary at the
   normal managed link. The user still chooses a URL and sees the normal download
   progress, retry, and cancellation behavior.
3. Switch to Repo Management and reuse
   `RepoManagementTab.choose_default_source_and_update()` to select and update
   the default `ruyisdk` source.
4. On a successful update, switch to About without starting device provisioning.

The user may skip the download or exit the setup. Exiting cancels an active
version download or repository update through their existing cancellation paths;
it must not weaken activation, backup, or process-cleanup behavior. Repository
updates launched by this flow use the normal `_RepoUpdateDialog` and repository
QProcess. The update dialog closes automatically after success; failures leave
its output available while the setup dialog offers retry or exit.

## Provisioning Flow

The GUI mirrors `ruyi device provision` while keeping each interaction in a Qt
page:

1. Initialize or sync the configured ruyi metadata repository.
2. Select a device, variant, and image combo from ruyi metadata.
3. Offer package version customization when ruyi reports useful alternatives.
4. Download and install package artifacts in `processes/download_child.py`.
5. Build a `PreparedProvision` from ruyi's strategy provider.
6. Collect and validate any required host block-device paths.
7. Display the strategy's pretend output and required commands.
8. Run the strategy through `FlashWorker`, forwarding plugin prompts to Qt.
9. Display the translated metadata post-install message and final status.

`WizardState` is invalidated when the user moves back to an earlier step. New
state must not survive if its inputs have changed.

## Repository Management

TOML is parsed directly only for ordered display and validation. Mutations must
go through ruyi's `ConfigEditor`; do not add a second TOML writer.

The built-in `ruyisdk` entry remains first and cannot be removed. Additional
repositories come from `core/repo_presets.py` (with `repo_presets.py` retained
as a compatibility import), start disabled, and retain their preset IDs and
names. Update and news output is rendered through the same Rich terminal view
used elsewhere in the application.

## Package Manager Versions

Release discovery first requests:

```text
https://api.ruyisdk.cn/releases/latest-pm
```

Invalid or unavailable responses fall back to:

```text
https://ruyisdk.org/data/api/api_ruyisdk_cn/releases_latest_pm.json
```

Downloaded binaries live under
`~/.local/share/oh-my-ruyi/versions`. The active version is derived from the
target of `/usr/local/bin/ruyi`; no duplicate activation state file is kept.

Activation and deactivation may run through a small privileged helper. Only
managed binaries and managed symlinks may be modified. Existing unmanaged paths
require user confirmation and are moved to numbered `.bak` files before
activation.

The first-use flow must use the same activation path and confirmation behavior;
it may not bypass the unmanaged-command backup check or sudo helper.

## Storage Safety

The GUI does not depend on `lsblk`. Linux discovery reads `/sys/block` and
`/dev`, while mount state comes from ruyi's `/proc/self/mounts` parser. macOS
discovery uses `diskutil` plist output and offers raw whole-disk paths.

The storage path selected by the user is not trusted by name alone. Its device
fingerprint is recorded at review time and checked again before flashing and at
each actual `dd` invocation. Mounted targets require explicit confirmation, and
Linux checks follow holder relationships for device-mapper, LUKS, LVM, and RAID
stacks. On macOS, formatted media uses UUID data from `diskutil`; unformatted
media falls back to its current I/O Registry entry ID, so reconnecting or
replacing the device requires selecting it again.

When adding a flashing path, preserve all of these checks. A UI confirmation is
not a substitute for revalidation immediately before the destructive command.

## Rich Output

Imported ruyi APIs may write strings, Rich renderables, links, progress output,
or carriage-return updates. Route output through `QtRuyiLogger` or a
`RichTextView`; do not flatten it to plain text before rendering.

Terminal output is tagged with an operation target such as `welcome`, `device`,
`download`, `flash`, or `fastboot`. This prevents delayed worker output from
appearing in a newer operation's view.

## Localization

The application currently routes Chinese translations for `zh_CN.UTF-8`.
Locale resolution follows gettext precedence:

1. `LANGUAGE`
2. `LC_ALL`
3. `LC_MESSAGES`
4. `LANG`

The locale is selected once at process startup. A locale is activated only when
Oh My Ruyi has an application catalog and ruyi supplies both its `argparse` and
`ruyi` gettext domains. Unsupported combinations are routed to English with
`LANGUAGE=C` for child processes.

Application strings use the gettext-style `_()` helper from `i18n.py`. Static
programmatic widget properties are translated by `translate_widget_tree()`;
dynamic text must call `_()` when it is created. Do not translate repository
IDs, URLs, paths, package atoms, package names, device names, or other external
data.

The current application catalog is `oh_my_ruyi/locales/zh_CN.json`. When adding
or changing a translatable template:

1. Keep placeholder names identical in source and translation.
2. Add the catalog entry before using the template.
3. Exercise dynamic and already-formatted template forms where applicable.
4. Update `tests/test_i18n.py` for routing, fallback, Qt, ruyi, or subprocess
   behavior changes.
5. Confirm the catalog is present in the built wheel.

Useful manual probes are:

```bash
LANGUAGE=zh_CN.UTF-8 uv run --locked oh-my-ruyi
LANGUAGE=zh_TW.UTF-8 uv run --locked oh-my-ruyi
```

The second command should remain in English until matching translation resources
exist in both projects.

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

For a focused UI smoke run:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_smoke.py
```

Locale tests intentionally launch isolated subprocesses because locale
initialization is process-wide and immutable after startup:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_i18n.py
```

Use `pytest-qt` for widget interactions and asynchronous signals. Keep network,
filesystem, privilege, and destructive-command boundaries mocked unless the test
is explicitly an integration test.

## CI and Packaging

The primary workflow tests Python 3.11 and 3.12 on Linux and macOS. It checks
the lockfile, Ruff, formatting, compilation, package construction, and the full
offscreen suite with verbose pytest output and a five-minute test-step timeout.
The manually triggered Debian workflow validates Debian 12 and 13, system Python,
offscreen tests, and the xcb plugin under Xvfb.

The wheel is built by Hatchling through `uv build`. Package files are selected
from `oh_my_ruyi`, including translation catalogs below `locales/`. After adding
a non-Python resource, inspect the wheel rather than assuming it was included.

Tag pushes run the PyInstaller workflow on Debian 12 and macOS 14 and create a
pre-release from both artifacts. The macOS artifact is not code-signed or
notarized. Device-provision testing on macOS is limited to `dd`-based storage
strategies because the macOS/fastboot toolchain cannot provide the device
identification required by fastboot-based ruyi strategies; this restriction is
outside the GUI implementation.

## Project Layout

```text
oh_my_ruyi/
  __main__.py           module entry point
  about_tab.py          runtime and telemetry information
  app.py                locale, config, QApplication, and window bootstrap
  core/                 Qt-free state and first-use policy
  processes/            cancellable package/repository/news subprocesses
  ui/                   reusable Qt helpers and version dialogs
  host_storage.py       disk discovery, mount checks, and fingerprints
  i18n.py               locale resolution and gettext-style helper
  locales/              application translation catalogs
  main_window.py        top-level tabs and provisioning flow
  qt_logger.py          ruyi logger bridge to Qt signals
  repo_manager.py       repository model and configuration mutations
  repo_manager_tab.py   repository management UI
  core/repo_presets.py  ordered repository and source presets
  repo_presets.py       compatibility import for preset data
  rich_output.py        safe Rich/ANSI rendering in Qt
  ruyi_facade.py        Qt-free imported ruyi API boundary
  version_manager.py    release and activation services
  worker_runtime.py     shared QThread startup and cleanup
  worker_services.py    repository, storage, release, and telemetry workers
  workers.py            flashing interception and compatibility exports
tests/
  test_i18n.py          locale routing and translated UI coverage
  test_smoke.py         construction, logger, and rendering smoke tests
  test_*                focused service and interaction tests
```

## Change Checklist

Before opening a pull request:

1. Keep domain logic in ruyi or the existing service/facade boundary, not Qt
   event handlers.
2. Keep blocking work off the UI thread.
3. Preserve cancellation, process cleanup, and storage revalidation paths.
4. Add focused tests proportional to the behavior and blast radius.
5. Run the full CI command set above.
6. Check `git diff` for generated files, local paths, and unrelated changes.
