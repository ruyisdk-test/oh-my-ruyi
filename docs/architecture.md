# Architecture

This document describes the code as it exists after the classified module split.
It is intentionally more concrete than a generic layered-design
description: every boundary below has a current owner and a known test seam.

## Runtime Shape

```text
oh_my_ruyi.__main__
  -> gui/app.py
      -> runtime/i18n.py
      -> GlobalConfig + QtRuyiLogger
      -> gui/main_window.py
          -> gui/first_use.py / gui/repo_manager_tab.py / gui/about_tab.py
          -> ui/{common,version_dialogs,repo_dialogs,first_use_dialog,version_tables,provision_pages,provision_content,storage_rows,wizard_shell,version_manager_panels,repo_page,about_page}.py
          -> runtime/worker_services.py / runtime/workers.py -> runtime/worker_runtime.py
          -> services/host_storage.py / services/repo_manager.py / services/ruyi_facade.py / services/version_manager.py
          -> QProcess child modules and environment adapter in processes/
```

The application is deliberately not a clean-room implementation of ruyi. The
installed ruyi package owns metadata schemas, package resolution, repository
semantics, and strategy plugins. Oh My Ruyi owns presentation, orchestration,
and the boundary checks required before invoking those APIs.

## Package Map

| Path | Responsibility | Must not own |
| --- | --- | --- |
| `gui/app.py` | Process startup, locale initialization, `QApplication`, config construction | Feature state or repository mutations |
| `gui/main_window.py` | Top-level tabs, wizard transitions, version controls, first-use orchestration | Ruyi metadata rules or a second download implementation |
| `gui/about_tab.py`, `gui/first_use.py`, `gui/repo_manager_tab.py` | Feature-specific Qt views and orchestration | Domain rules outside their owning service |
| `core/state.py` | Mutable provisioning scratch state and invalidation methods | Qt widgets, I/O, network, flashing |
| `core/first_use_policy.py` | Pure first-launch eligibility predicate and PATH filtering | Dialogs, downloads, activation |
| `core/formatting.py` | Qt-free byte-size formatting shared by storage and version views | UI state or filesystem access |
| `core/repo_presets.py` | Immutable repository/source preset data | TOML writes or repository I/O |
| `ui/common.py` | Shared Qt constants, translated message-box adapter, semantic version table item, and table setup policy | Application state |
| `ui/version_dialogs.py`, `ui/repo_dialogs.py`, `ui/first_use_dialog.py` | Reusable Qt dialogs with narrow signal/data contracts | Starting workers or changing filesystem state |
| `ui/version_tables.py` | Reusable release/local-version table rendering and selection preservation | Catalog fetching, activation, or application state |
| `ui/theme.py` | Palette-to-semantic-color mapping and stylesheet generation | Runtime state, workers, or data I/O |
| `ui/repo_tables.py` | Repository preset/configuration table rendering and protected-entry hints | Repository mutations or update processes |
| `ui/provision_pages.py` | Provisioning wizard page construction and callback wiring | Wizard state transitions, workers, repository or storage I/O |
| `ui/version_manager_panels.py` | Standalone ruyi version page and panel construction | Release discovery, downloads, activation, or version state |
| `ui/repo_page.py` | Repository management panel construction and intent wiring | Repository state, TOML mutation, or update processes |
| `ui/about_page.py` | About page presentation construction | Runtime probes, telemetry queries, or subprocesses |
| `ui/provision_content.py` | Shared entity-list, package-list, and version-selection rendering | Ruyi lookups, wizard state, storage or flashing operations |
| `ui/storage_rows.py` | Storage target selector and mounted-warning row construction | Disk discovery, fingerprints, mount validation, or flashing |
| `ui/wizard_shell.py` | Provisioning sidebar, summary, page stack, and navigation construction | Wizard transitions, invalidation, workers, or feature-tab behavior |
| `runtime/worker_services.py` | Repository, storage, release, activation, and telemetry QObject workers | Widget mutation or thread ownership outside its worker |
| `runtime/workers.py` | Flash interception and worker coordination | Duplicating service workers or changing their patch seams |
| `runtime/worker_runtime.py` | Queued worker start and shared thread cleanup | Business operations |
| `services/host_storage.py` | Disk discovery, topology, mount checks, fingerprints | Qt state or flashing commands |
| `services/ruyi_facade.py` | Qt-free calls into ruyi provisioning APIs | Reimplementation of ruyi algorithms |
| `services/repo_manager.py` | Ordered TOML display and `ConfigEditor` mutations | A second TOML writer |
| `services/version_manager.py` | Release catalog, downloads, activation, PATH and telemetry services | Qt dialogs or widget state |
| `runtime/qt_logger.py`, `runtime/rich_output.py` | Rich/ANSI output routing and rendering | Flattening output before the view |
| `processes/*.py` | Blocking child-process command adapters | Qt objects or GUI state |
| `processes/environment.py` | Shared locale, Rich terminal, buffering, and telemetry environment mutations | Process lifecycle or business operations |

## Package Root

The package root contains only the two package-level files:

```text
oh_my_ruyi/__init__.py   package metadata
oh_my_ruyi/__main__.py  `python -m oh_my_ruyi` application entry point
```

All implementation modules live under `gui/`, `services/`, `runtime/`,
`core/`, `ui/`, and `processes/`. Tests and new code import those canonical
paths directly. Child process modules are internal QProcess targets, not
additional public command entry points.

## Frozen Entry

PyInstaller uses `oh_my_ruyi/__main__.py` as the application script. In a
frozen binary, `sys.executable` is the GUI executable itself, so the normal
QProcess arguments for a child module cannot be handed to a Python interpreter.
`_run_embedded_command()` dispatches those internal commands in-process:

- names in `_CHILD_MODULES` import and call the corresponding `processes/`
  entry point with its remaining arguments;
- `-m ruyi` imports `ruyi.__main__` and calls `entrypoint` with `sys.argv[0]`
  set to `ruyi`, preserving ruyi's command-line mode detection;
- unknown `-m` arguments fall through to normal GUI startup.

Every new child process must be registered in `_CHILD_MODULES`, collected by
`oh-my-ruyi.spec`, and covered by the packaging tests and a frozen smoke check.

## State Ownership

`WizardState` is a mutable, per-window scratchpad. It is not persistent user
data. The following derived-value relationships are important:

```text
repository -> mr -> device -> variant -> combo -> pkg_atoms
                                             -> prepared
                                                  -> host_blkdev_map + fingerprints
                                                       -> flash_ret + postinst_msg
```

`WizardState.clear_prepared()` clears the prepared plan and storage values while
leaving the package atoms, flash result, and post-install message for the caller
to handle. `reset_selection()` clears device-dependent choices and the prepared
plan while retaining the loaded repository. `reset_for_repository()` also drops
`mr`, the flash result, and the post-install message. `reset_for_restart()`
returns to device selection while retaining `mr` and the existing post-install
message, matching the original page transition behavior.

The main window still controls when these operations happen. The state object
only makes the invalidation atomic and reusable. A backward navigation or
repository change must never leave a prepared plan or a storage fingerprint
that was calculated for different inputs.

## Main-Window Regions

`gui/main_window.py` remains a large coordinator because it owns all cross-feature
transitions. Its methods are grouped by responsibility:

1. Construction and close/cancellation policy.
2. First-use setup and repository-change reactions.
3. Version-management tab and its workers/dialog.
4. Repository/provision initialization.
5. Wizard navigation and downstream invalidation.
6. Device, variant, image, package, storage, review, flash, and done pages.
7. Output routing and small lifecycle helpers.

The extraction rule is conservative: a class or function may move when it has a
small signal/data contract and no hidden access to the window's mutable state.
The version download, repository source/update, first-use dialog, and
provisioning page factory meet that rule. The service workers meet it because
they only retain operation inputs and emit results; `runtime/workers.py` exposes
their worker classes with the flashing boundary. The page factory returns the
widgets that the coordinator updates later; it does not move the wizard state
machine out of `gui/main_window.py`.

## Worker Lifecycle

Workers are `QObject` instances with a `run()` slot and result/failure signals.
`runtime/worker_runtime.start_worker()` performs the only supported startup sequence:

1. Create a fresh `QThread`.
2. Move the worker to that thread.
3. Connect `thread.started` to the worker slot with a queued connection.
4. Start the thread.

The owning Qt object stores both references and cleans them after the matching
operation completes. `runtime/worker_runtime.stop_thread()` applies the established
quit-and-wait cleanup contract. The worker itself never edits widgets.

Package downloads, repository updates, and repository news use QProcess child
commands when independent process-group cancellation is required. The child
sets its own ruyi environment, performs the blocking call, and returns a normal
exit code. The parent classifies output by operation identity before displaying
it.

The parent-side QProcess environment is configured by
`processes/environment.py`. The owning module still creates the
`QProcessEnvironment` and owns the process object; the helper only applies the
shared locale/output flags and keeps those module-level construction seams
available to tests.

## Output Routing

`QtRuyiLogger` emits both structured log records and terminal text. Terminal
text carries a target (`welcome`, `device`, `download`, `flash`, or `fastboot`).
`RichTextView` consumes Rich renderables, ANSI styles, OSC-8 links, carriage
returns, and erase controls. A delayed signal from an old operation must not be
allowed to append to a new target.

## Extension Rule

When adding behavior, first identify the owner in the table above. Add a pure
service function or adapter method when the behavior is domain-facing; add a
worker or child process when it blocks; add a widget only for rendering and
user input. Import the owning canonical module directly, and add a focused test
before changing a signal or invalidation contract.
