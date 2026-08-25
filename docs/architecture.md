# Architecture

This document describes the code as it exists after the compatibility-preserving
module split. It is intentionally more concrete than a generic layered-design
description: every boundary below has a current owner and a known test seam.

## Runtime Shape

```text
oh_my_ruyi.__main__
  -> app.py
      -> i18n.py
      -> GlobalConfig + QtRuyiLogger
      -> main_window.py
          -> first_use.py / repo_manager_tab.py / about_tab.py
          -> ui/{common,version_dialogs,repo_dialogs,first_use_dialog,version_tables}.py
          -> worker_services.py / workers.py -> worker_runtime.py
          -> host_storage.py / repo_manager.py / ruyi_facade.py / version_manager.py
          -> QProcess child modules in processes/
```

The application is deliberately not a clean-room implementation of ruyi. The
installed ruyi package owns metadata schemas, package resolution, repository
semantics, and strategy plugins. Oh My Ruyi owns presentation, orchestration,
and the boundary checks required before invoking those APIs.

## Package Map

| Path | Responsibility | Must not own |
| --- | --- | --- |
| `app.py` | Process startup, locale initialization, `QApplication`, config construction | Feature state or repository mutations |
| `main_window.py` | Top-level tabs, wizard transitions, version controls, first-use orchestration | Ruyi metadata rules or a second download implementation |
| `core/state.py` | Mutable provisioning scratch state and invalidation methods | Qt widgets, I/O, network, flashing |
| `core/first_use_policy.py` | Pure first-launch eligibility predicate and PATH filtering | Dialogs, downloads, activation |
| `core/formatting.py` | Qt-free byte-size formatting shared by storage and version views | UI state or filesystem access |
| `core/repo_presets.py` | Immutable repository/source preset data | TOML writes or repository I/O |
| `ui/common.py` | Shared Qt constants, translated message-box adapter, semantic version table item, and table setup policy | Application state |
| `ui/version_dialogs.py`, `ui/repo_dialogs.py`, `ui/first_use_dialog.py` | Reusable Qt dialogs with narrow signal/data contracts | Starting workers or changing filesystem state |
| `ui/version_tables.py` | Reusable release/local-version table rendering and selection preservation | Catalog fetching, activation, or application state |
| `ui/theme.py` | Palette-to-semantic-color mapping and stylesheet generation | Runtime state, workers, or data I/O |
| `ui/repo_tables.py` | Repository preset/configuration table rendering and protected-entry hints | Repository mutations or update processes |
| `worker_services.py` | Repository, storage, release, activation, and telemetry QObject workers | Widget mutation or thread ownership outside its worker |
| `workers.py` | Flash interception plus compatibility exports for all worker classes | Duplicating service workers or changing their patch seams |
| `worker_runtime.py` | Queued worker start and shared thread cleanup | Business operations |
| `host_storage.py` | Disk discovery, topology, mount checks, fingerprints | Qt state or flashing commands |
| `ruyi_facade.py` | Qt-free calls into ruyi provisioning APIs | Reimplementation of ruyi algorithms |
| `repo_manager.py` | Ordered TOML display and `ConfigEditor` mutations | A second TOML writer |
| `version_manager.py` | Release catalog, downloads, activation, PATH and telemetry services | Qt dialogs or widget state |
| `qt_logger.py`, `rich_output.py` | Rich/ANSI output routing and rendering | Flattening output before the view |
| `processes/*.py` | Blocking child-process command adapters | Qt objects or GUI state |

## Compatibility Modules

The old flat module names are part of the current test and subprocess surface.
These files are intentionally thin:

```text
state.py            -> core.state.WizardState
download_child.py   -> processes.download_child.main
repo_update_child.py -> processes.repo_update_child.main
repo_news_child.py  -> processes.repo_news_child.main
```

They are not alternate implementations. New code should import the package
path when it owns the feature; external callers may continue using the flat
path until a release-specific deprecation decision is made. In particular,
the GUI may keep old `python -m oh_my_ruyi.*` command strings because existing
installations and tests rely on them. The wrappers forward to the same function
and do not alter arguments, environment, or exit codes.

The high-risk service modules (`host_storage.py`, `ruyi_facade.py`, and
`version_manager.py`) remain at their established paths for now. Their tests
monkeypatch module globals such as platform probes and ruyi classes; moving
them without a deliberate compatibility adapter would change the patch target
and could silently weaken safety checks. They are already coherent service
boundaries, so a future move must be driven by a concrete caller and a focused
regression test.

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

`main_window.py` remains a large coordinator because it owns all cross-feature
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
The version download, repository source/update, and first-use dialogs meet that
rule. The service workers meet it because they only retain operation inputs and
emit results; `workers.py` re-exports their original names for callers and
tests. Wizard pages do not yet: they share dozens of fields and transition
methods, so moving them wholesale would increase coupling rather than improve
readability.

## Worker Lifecycle

Workers are `QObject` instances with a `run()` slot and result/failure signals.
`worker_runtime.start_worker()` performs the only supported startup sequence:

1. Create a fresh `QThread`.
2. Move the worker to that thread.
3. Connect `thread.started` to the worker slot with a queued connection.
4. Start the thread.

The owning Qt object stores both references and cleans them after the matching
operation completes. `worker_runtime.stop_thread()` applies the established
quit-and-wait cleanup contract. The worker itself never edits widgets.

Package downloads, repository updates, and repository news use QProcess child
commands when independent process-group cancellation is required. The child
sets its own ruyi environment, performs the blocking call, and returns a normal
exit code. The parent classifies output by operation identity before displaying
it.

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
user input. Keep the public flat import path when existing tests or subprocess
commands use it, and add a focused test before changing a signal or invalidation
contract.
