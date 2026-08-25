# Architecture

This document describes the internal design of Oh My Ruyi. It is intentionally
more detailed than the root `AGENTS.md`: it explains why boundaries exist, how
objects communicate, what state is invalidated, and which file owns each
workflow. When a change crosses one of these boundaries, update the owner and
its focused tests together.

## Runtime Layers

The dependency direction is:

```text
app/bootstrap.py
  -> ui/views/main_window.py
       -> controllers
       -> ui/views and ui/widgets
       -> workers / processes
       -> infra
       -> ruyi APIs and host commands
```

The `core` package is Qt-free and contains state/models/protocols used by the
controller and infrastructure layers. `infra` is the boundary around imported
ruyi APIs, filesystem/configuration rules, release management, and platform
storage. `ui` displays results and requests operations. `workers` and
`processes` isolate blocking work.

The application is not an MVC implementation with a separate view model layer.
There is no `app/services`, `viewmodels`, or second state store in the current
layout. `ProvisionController.state` is the single provisioning scratchpad.

## Entry Points

### Normal Python entry

`oh_my_ruyi/__main__.py` exposes `main(argv=None)`. In a normal interpreter it
imports `oh_my_ruyi.app.run`, which is implemented in `app/bootstrap.py`.
`app/bootstrap.py` performs these steps in order:

1. Resolve and initialize the process-wide locale.
2. Create ruyi's `EnvGlobalModeProvider` from `os.environ` and `sys.argv`.
3. Create `LogEmitter` and `QtRuyiLogger`.
4. Load and localize `GlobalConfig`.
5. Create `QApplication` and install Qt standard-control translations.
6. Create and show `ProvisionMainWindow`.
7. Enter `app.exec()`.

The configuration loader passed to the window reloads ruyi configuration after
repository changes. It must use the same logger and locale policy as startup;
do not create a second global mode or logger in a view.

### Frozen entry

PyInstaller uses `oh_my_ruyi/__main__.py` as a script. In a frozen binary,
`sys.executable` is the GUI executable itself, so normal subprocess arguments
such as `-m oh_my_ruyi.processes.download_child` cannot invoke a Python module
normally. `_run_embedded_command()` handles these arguments in-process:

- child module names listed in `_CHILD_MODULES` are imported and called with
  their remaining argv;
- `-m ruyi` imports `ruyi.__main__` and calls its `entrypoint` with `sys.argv[0]
  set to `ruyi`, so ruyi does not mistake `oh-my-ruyi` for a toolchain mux;
- unknown `-m` arguments fall through to normal GUI startup rather than being
  silently interpreted as an internal command.

Every new child process must be added to `_CHILD_MODULES`, collected by the
PyInstaller spec, and covered by `tests/test_packaging.py` plus a frozen build
smoke check.

## Main Window Composition

`ProvisionMainWindow` uses this method resolution order:

```text
ProvisionWizardMixin
VersionManagementMixin
FirstUseMixin
QMainWindow
```

`ui/views/main_window.py` is a composition and signal-wiring module. It owns:

- `ProvisionController` and `RepoController` instances;
- the four top-level tabs;
- the stacked provisioning pages and summary area;
- global busy aggregation and close handling;
- operation-targeted log routing;
- the shared paths/configuration used by About and Version Management.

It should not contain ruyi metadata traversal, package resolution, TOML
mutation, disk topology logic, or direct destructive commands. A new workflow
belongs in a controller, worker, child process, or existing facade; the window
then connects its result signal to a Qt slot.

The window's busy state includes all of these sources:

- its local worker runner;
- version-management workers;
- fastboot QProcess;
- `ProvisionController` download/preparation state;
- `RepoController` init/sync state;
- repository tab update/news QProcesses.

This aggregation is used to disable repository edits, wizard navigation, and
other operations while a conflicting operation is active. Do not add a local
boolean that duplicates this list without updating `_is_busy()` and
`_has_external_busy_operation()`.

## Controllers

### ProvisionController

`controllers/provision_controller.py` owns:

- `WizardState`;
- `ProvisionStateMachine`;
- package download QProcess;
- `ProvisionPreparationWorker`;
- operation busy signals and download output.

The package path is:

```text
start_download()
  -> download_child QProcess
  -> download_output(bytes)
  -> download_finished(success, message)
  -> ProvisionPreparationWorker
  -> preparation_finished(prepared)
     or preparation_failed(message)
```

The controller emits download success before preparation completes so the UI
can change the status text to “Preparing flash plan...”. It keeps
`busy_changed=True` during both phases. Only `preparation_finished` makes the
download step usable and advances to Storage or Review.

Starting a new download clears `state.prepared`, storage paths, fingerprints,
and previous flash result. This prevents a newly downloaded/customized package
set from reusing a plan prepared for an earlier selection.

The controller does not own fastboot checks, storage discovery, or the Flash
worker. Those operations remain in the provisioning view because their result
is coupled directly to visible page controls and interactive prompts.

### RepoController

`controllers/repo_controller.py` owns only blocking metadata initialization and
sync:

```text
start_repo_init(config) -> RepoInitWorker -> ruyi_adapter.ensure_repo()
start_repo_sync(config, mr) -> RepoSyncWorker -> ruyi_adapter.sync_repo()
```

It exposes `init_finished`, `init_failed`, `sync_finished`, `sync_failed`, and
`busy_changed`. The main window connects these signals once during construction.
The provisioning mixin must not connect the same signal every time the user
clicks Update metadata.

Repository configuration edits and remote update/news processes are owned by
`RepoManagementTab`; do not move them into `RepoController` unless the child
process ownership and cancellation contract is redesigned together.

## Core State and FSM

### WizardState

`core/state.py` defines the only mutable provisioning scratchpad:

| Field | Producer | Consumers | Invalidated by |
| --- | --- | --- | --- |
| `mr` | repo init/sync | selection pages, adapter | repository config change |
| `device` | Device page | Variant page | back to Welcome |
| `variant` | Variant page | Combo page | back to Device |
| `combo` | Combo page | package pages | back to Variant |
| `pkg_atoms` | combo/version pages | download/preparation | combo/version change |
| `prepared` | preparation worker | Storage/Review/Flash | package or combo change |
| `host_blkdev_map` | Storage page | Review/Flash | storage/package change |
| `host_blkdev_fingerprints` | Storage page | FlashWorker | storage/package change |
| `flash_ret` | FlashWorker | Flash/Done recovery | review/storage change |
| `postinst_msg` | adapter after flash | Done page | combo/restart |

Use `reset_from_category()`, `reset_from_device()`,
`reset_from_variant()`, and `reset_from_combo()` instead of manually clearing a
subset of fields. If a new state field is dependent on a selection, add it to
the appropriate reset method and add a stale-state test.

### ProvisionStateMachine

The eleven steps are:

```text
0 Welcome    1 Device    2 Variant    3 Combo
4 Versions   5 Packages  6 Download  7 Storage
8 Review     9 Flash     10 Done
```

`set_step()` calls `invalidate_downstream()` before moving backward. The FSM
also tracks UI-only flags:

- `versions_visited` controls whether the version customization page is
  revisitable;
- `download_ok` controls access to Storage/Review;
- `download_recoverable` exposes resume/reselect/start-over controls;
- `flash_recoverable` exposes retry/review/start-over controls.

The FSM decides whether a step is logically openable. The view decides how to
render it and when a button can be clicked. Do not bypass `can_open_step()` by
enabling a sidebar item directly.

## Ruyi Adapter

`infra/ruyi_adapter.py` is intentionally free of Qt imports. It translates
ruyi data to `core.models` and keeps ruyi-specific calls out of widgets.

### Repository boundary

`use_provision_repo()` filters to active `ruyisdk` only. `ensure_repo()` and
`sync_repo()` use that filtered `CompositeRepo`; third-party repositories remain
available to the repository manager but do not silently participate in device
provisioning.

### Selection boundary

`list_devices()`, `list_variants()`, and `list_combos()` traverse ruyi entity
relationships and return sorted application choices. The UI stores the choice
object and its ruyi entity; it does not inspect `entity.data` for domain rules.

### Package version boundary

`list_package_version_selections()` mirrors the TUI rules for slug atoms,
expression atoms, prereleases, known issues, upstream versions, and exact
version atoms. If ruyi changes these rules, update the facade and its focused
tests rather than adding special cases to the version page.

### Preparation boundary

`PreparedProvision` contains:

- `strategies`: `(package_atom, PackageProvisionStrategy)` pairs sorted by
  descending priority;
- `pkg_part_maps`: package atom to image partition map;
- `all_parts`: unique partition kinds found in package maps;
- `requested_host_blkdevs`: unique host partitions requested by strategies;
- `needed_cmds`: external commands declared by strategies.

`compute_pretend_steps()`, `missing_cmds()`, and
`needs_fastboot_confirmation()` consume this object. Keep its fields coherent
with `FlashWorker`, the Review page, and state-machine tests when ruyi changes.

## UI Mixins

### ProvisionWizardMixin

Owns page construction and provisioning interaction:

- page widgets and accessibility names;
- device/variant/combo/version selection;
- download status/log handling;
- Storage discovery, target selection, mounted confirmation, and fingerprint
  capture;
- Review pretend output and command availability;
- fastboot check QProcess;
- FlashWorker prompt routing, cancellation, output, and recovery.

The mixin may call facade methods that are quick and Qt-free, but it must not
call `ensure_repo()`, `sync_repo()`, `prepare_provision()`, `list_disks()`,
package installation, or flashing directly on the UI thread. It requests these
through controllers/workers.

### VersionManagementMixin

Owns the Version Management tab and connects:

```text
VersionCatalogWorker
VersionDownloadDialog -> VersionDownloadWorker
VersionActivationWorker
VersionDeactivationWorker
VersionDeleteWorker
TelemetrySetupWorker
```

The mixin owns only UI state such as selected table rows, operation status,
dialogs, and retry presentation. Filesystem and network rules stay in
`version_manager.py`; all worker cleanup goes through the version runner.

### FirstUseMixin

First-use is orchestration, not a second implementation of any operation. It:

1. waits for the normal release catalog;
2. opens the normal VersionDownloadDialog;
3. starts the normal activation worker;
4. opens the normal repository source dialog and update QProcess;
5. switches to About after successful repository update.

`_first_use_active` gates late callbacks. `_first_use_cancelled` prevents a
late activation success from starting telemetry after the user exits. A failed
or cancelled download must clean an otherwise empty managed data directory.

## Widgets and Output

### QtRuyiLogger and LogEmitter

`QtRuyiLogger` wraps ruyi/Rich output and emits both plain log signals and
terminal output. `LogEmitter` is a separate QObject to avoid mixing ruyi's
logger class hierarchy with Qt's QObject metaclass.

Terminal output carries an operation target such as `welcome`, `device`,
`download`, `flash`, `fastboot`, or `pm`. The target prevents delayed output
from a completed operation appearing in a newly selected page.

### RichTextView

Use the correct input API:

- `feed_bytes(bytes, final=False)` for QProcess/subprocess chunks;
- `feed_text(str, final=False)` for text terminal streams;
- `append_rich(renderable)` for Rich renderables;
- `append_plain_status(str)` for non-terminal status messages.

The view maintains incremental UTF-8 decoding, split escape sequences, ANSI
styles, OSC8 links, carriage-return replacement, backspace handling, and
palette replay. Do not call `strip_terminal_controls()` before feeding primary
output; that destroys styles and progress semantics.

### QProcess environment

`configure_qprocess_environment()` is the shared setup for child processes. It
sets normalized locale, unbuffered Python output, ruyi telemetry opt-out for
GUI-owned operations, Rich terminal variables, and merged channels. Raw
`subprocess` calls must copy `os.environ` and merge `locale_environment()`.

## Workers and Processes

Workers are QObject instances moved to fresh QThreads by
`WorkerTaskRunner.run_worker()`. A worker:

1. stores only immutable inputs or a reference to the controller-owned state it
   needs;
2. performs blocking work in `run()`;
3. emits `finished`, `failed`, `cancelled`, progress, prompt, or output signals;
4. never creates or mutates widgets;
5. allows the runner to quit the thread and delete the worker.

Use a child process instead of a worker when the operation needs independent
process-group cancellation, an interactive terminal, or isolation from a
native command. Every child has `main(argv)` and a direct `__main__` guard.

When adding either type, add tests for success, failure, cancellation (if
supported), repeated start protection, late signals, and cleanup. See the
workflow and testing documents for templates and commands.
