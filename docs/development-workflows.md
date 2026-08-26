# Development Workflows

This document is a practical guide for extending the refactored tree without
reintroducing mixed responsibilities. Read [Architecture](architecture.md)
before moving ownership and [Operations and Safety](operations-and-safety.md)
before touching storage, activation, repositories, or flashing.

## Adding a Pure Policy

Put a decision that needs no Qt, ruyi network state, or filesystem mutation in
`core/`. Give it explicit inputs and injectable system boundaries. The
first-use predicate is the model:

```python
should_offer_first_use_setup(
    telemetry_installation,
    managed_data_directory,
    path=..., runtime_executable=..., which=...
)
```

The GUI module imports the policy for its setup flow. Tests should exercise the
policy with `tmp_path`, a synthetic PATH, and a fake `which`; they should not
need a `QApplication`.

## Adding a Reusable Widget

Use `ui/` when a widget has a narrow data/signal contract and does not need to
know the main window's state machine. A reusable widget should:

- translate dynamic strings at creation time;
- expose signals for user intent rather than calling workers directly;
- own only its child widgets and temporary display state;
- preserve retry, cancellation, and failure output if it starts a visual flow;
- have construction and signal tests in `tests/test_smoke.py` or a focused UI test.

`ui/version_dialogs.py` is the reference; `ui/repo_dialogs.py` and
`ui/first_use_dialog.py` follow the same rule. The main window supplies data,
connects intent signals, and decides what success or failure means. Dialogs
never call blocking service functions such as
`version_manager.download_release()`.

The provisioning wizard follows the same boundary through
`ui/provision_pages.py`: its factory receives callbacks, creates pages, and
returns a typed widget bundle. Keep provisioning state, invalidation, and
worker starts in `gui/main_window.py`.

Do not move a wizard page merely because it is long. If a page reads or writes
many `ProvisionMainWindow` fields, first extract a pure formatter or a helper
with an explicit input/result object. A broad mixin or a second controller can
make navigation harder to follow.

## Adding a Worker

Add a service worker to `runtime/worker_services.py` when it only retains
operation inputs and emits a result; keep the flashing interception in
`runtime/workers.py`. `runtime/workers.py` exposes the service worker classes
alongside the flashing worker. Use `runtime/worker_runtime.start_worker()`
through the existing `run_worker_in_thread()` wrapper. A worker must:

1. keep all blocking ruyi, filesystem, network, and subprocess work in `run()`;
2. catch operational exceptions and emit `failed` with a user-facing message;
3. expose cancellation through an event and terminate the owned process when
   necessary;
4. emit no widget mutation and no direct `QMessageBox` call;
5. leave thread cleanup to the owning Qt object.

For a new worker, add at least one success/failure test and a cancellation test
when it owns a stream or process. Use mocked boundaries; do not download a
release or write a block device in a unit test.

## Adding a Child Process

Create a small module in `processes/` with `main(argv: list[str] | None)` and a
`__main__` guard. Validate arguments and paths before importing expensive ruyi
modules. Set the XDG environment required by the supplied config path, create
the correct ruyi logger/config, perform exactly one operation, and return its
integer exit code.

The parent invokes the canonical `oh_my_ruyi.processes.<name>` module directly.
These are internal QProcess commands, not separate public application entry
points. When the application is frozen, `oh_my_ruyi.__main__` dispatches the
same names in-process.

When adding a child:

1. Add the module under `processes/`.
2. Use `configure_qprocess_environment()` on the Qt side.
3. Register its fully qualified name in `__main__._CHILD_MODULES`.
4. The shared `oh-my-ruyi.spec` collects all `oh_my_ruyi.processes`
   submodules for the frozen dispatcher.
5. Add normal-interpreter and frozen-dispatch tests.
6. Check process identity in the parent before consuming late output/results.

The package root must not gain a wrapper merely to mirror a moved file.

## Adding an Adapter Function

Use `services/ruyi_facade.py` for Qt-free provisioning calls. The adapter should mirror
ruyi's API shape and return small dataclasses where the UI needs stable display
fields. Do not copy metadata rules, package resolution, or strategy algorithms
into the adapter. If ruyi already exposes the operation, delegate to it.

For repository configuration use `services/repo_manager.py`; read TOML for ordered
display/validation only and mutate through ruyi's `ConfigEditor`.

## Adding a Repository Preset

Add the preset to `core/repo_presets.py` with a stable ID and display name. Keep the built-in
`ruyisdk` source first and non-removable. Presets start disabled. Add a
focused test for ordering, source selection, and removal protection in
`tests/test_repo_manager.py` or `tests/test_repo_manager_tab.py`.

## Adding a Locale String

Use `_()` from `runtime/i18n.py`. Dynamic messages are translated when built; static
widget properties can be translated by `translate_widget_tree()`. Keep source
and catalog placeholder names identical. Never translate paths, URLs, package
atoms, repository IDs, device names, or command output.

Locale initialization is process-wide. Test routing in an isolated subprocess,
and include both the application catalog and ruyi's required domains before
enabling a locale. Confirm `locales/zh_CN.json` is inside the wheel.

## Keeping The Package Root Clean

Implementation belongs in the classified package that owns the boundary:
`gui/`, `services/`, `runtime/`, `core/`, `ui/`, or `processes/`. The package
root contains only `__init__.py` and `__main__.py`; do not add a second copy or
an alias at the root when moving a module.

When moving a module, search for ordinary imports and internal command strings
such as `python -m oh_my_ruyi.processes.<name>`, then update them to the
canonical path.

## Refactoring Checklist

Before editing:

1. Read `README.md`, `docs/development-guide.md`, this document, and the owner.
2. Search tests for monkeypatch targets and `python -m` command strings.
3. Identify whether the code is pure, Qt-facing, blocking, or destructive.
4. Prefer a move with direct canonical imports over duplicate implementations.

After editing:

1. Compile the package and inspect import paths.
2. Run the focused owner tests with `QT_QPA_PLATFORM=offscreen`.
3. Run Ruff, formatting, the full suite, and the build when dependencies are
   available.
4. Inspect the diff for generated files, stale imports, and accidental path
   changes.
5. Update `AGENTS.md` when an ownership or safety rule changed.
