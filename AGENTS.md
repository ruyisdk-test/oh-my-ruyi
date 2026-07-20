# Agent Development Context

This is the first-pass context for coding agents working in this repository.
Read it before inspecting or changing code. The
[Development Guide](docs/development-guide.md) is the detailed, human-oriented
reference, and the [README](README.md) defines user-facing behavior.

## Project Snapshot

- `oh-my-ruyi` is a programmatic PySide6 frontend for the `ruyi` package
  manager. It manages ruyi versions and repositories and drives device
  provisioning from ruyi metadata.
- The GUI imports ruyi's Python APIs. Keep metadata, package, and provisioning
  domain rules in ruyi or behind the existing Qt-free facade; do not duplicate
  them in widgets.
- Python 3.11 and 3.12 are tested in CI. Dependencies, locked environments, and
  builds use `uv`; Hatchling builds the package.
- Headless Qt tests require `QT_QPA_PLATFORM=offscreen`.
- User-visible behavior belongs in `README.md`; contributor explanations belong
  in `docs/development-guide.md`; durable agent constraints belong here.

## Start Here

Before a general change, read:

1. `README.md` for the promised user behavior.
2. `docs/development-guide.md` for setup, architecture, and workflows.
3. The owning module and its focused tests.

Use this map to find the owning boundary:

- Application bootstrap and locale initialization: `oh_my_ruyi/app.py`.
- Top-level tabs, version UI, and provisioning state machine:
  `oh_my_ruyi/main_window.py`.
- Mutable provisioning selections and invalidation: `oh_my_ruyi/state.py`.
- Qt-free ruyi provisioning boundary: `oh_my_ruyi/ruyi_facade.py`.
- QThread workers, flashing interception, cancellation, and privileged helpers:
  `oh_my_ruyi/workers.py`.
- Repository model and mutations: `oh_my_ruyi/repo_manager.py`.
- Repository UI and update/news processes: `oh_my_ruyi/repo_manager_tab.py`,
  `oh_my_ruyi/repo_update_child.py`, and `oh_my_ruyi/repo_news_child.py`.
- Release discovery, downloads, activation, PATH state, and telemetry:
  `oh_my_ruyi/version_manager.py`.
- Disk discovery, mount topology, and target fingerprints:
  `oh_my_ruyi/host_storage.py`.
- Rich and ruyi output routing: `oh_my_ruyi/qt_logger.py` and
  `oh_my_ruyi/rich_output.py`.
- Locale routing and translation helpers: `oh_my_ruyi/i18n.py` and
  `oh_my_ruyi/locales/zh_CN.json`.
- Tests: `tests/test_<owning_module>.py`; cross-window flows are mainly in
  `tests/test_main_window_interactions.py` and construction/rendering coverage
  is in `tests/test_smoke.py`.

## Architecture Contracts

- Do not run repository I/O, downloads, disk discovery, package work, telemetry
  setup, or flashing on the Qt UI thread. Follow the existing QObject/QThread
  or child-process pattern for the owning feature.
- Workers emit results or failures. UI state and widget mutation stay on the Qt
  thread. Preserve thread ownership, signal cleanup, cancellation, and process
  termination when changing asynchronous paths.
- `main_window.py` owns provisioning transitions. Moving back to an earlier
  step invalidates dependent `WizardState`; stale prepared or storage state
  must not survive changed inputs.
- `ruyi_facade.py` stays free of Qt imports. It mirrors ruyi's provisioning APIs
  without becoming a second implementation of ruyi.
- Repository TOML may be parsed for ordered display and validation, but all
  mutations go through ruyi's `ConfigEditor`. Do not introduce another writer.
- Keep the built-in `ruyisdk` repository first and non-removable. Preset IDs and
  names are external identifiers and must remain stable.
- Route imported ruyi/Rich output through `QtRuyiLogger` or `RichTextView`.
  Preserve renderables, links, progress, ANSI styles, and carriage-return
  updates instead of flattening them to plain text.
- Preserve operation output targets such as `welcome`, `device`, `download`,
  `flash`, and `fastboot`; they prevent delayed output from leaking into a new
  operation's view.

## Destructive and Privileged Operations

- Storage paths are untrusted. Preserve fingerprint checks at review time,
  immediately before flashing, and at each actual `dd` invocation.
- Mounted targets require explicit confirmation. Linux checks must continue to
  follow holder relationships for device-mapper, LUKS, LVM, and RAID stacks.
- Discovery or topology failure must fail closed. A UI confirmation never
  replaces revalidation at the destructive command boundary.
- Activation and deactivation may use sudo helpers. They may modify only managed
  binaries and managed symlinks. Existing unmanaged paths require confirmation
  and a numbered `.bak` backup.
- Tests must mock network, privilege, and destructive-command boundaries unless
  a test is explicitly an integration test.

## Localization Contract

- Use gettext-style `_()` from `oh_my_ruyi.i18n`; there is no application
  `tr()` helper.
- Locale selection occurs once at process startup. Resolution uses `LANGUAGE`,
  `LC_ALL`, `LC_MESSAGES`, then `LANG`.
- The current application catalog is `oh_my_ruyi/locales/zh_CN.json`. Chinese is
  routed for `zh_CN.UTF-8` only when both Oh My Ruyi and ruyi provide the needed
  resources. Unsupported combinations remain in English.
- Dynamic user-visible text calls `_()` when created. Static programmatic widget
  properties may be translated with `translate_widget_tree()` after construction.
- Keep placeholder names identical in source and translation. Do not translate
  repository IDs, URLs, paths, package atoms, package names, device names, or
  other external data.
- QProcess environments use `apply_qprocess_locale()`. Standard subprocess
  environments include `locale_environment()` so GUI and ruyi output agree.
- Locale tests use isolated subprocesses because initialization is process-wide
  and immutable after startup. Confirm new catalogs are present in the wheel.

## Change Strategy

- Make the smallest change at the existing ownership boundary. Avoid unrelated
  refactors, parallel abstractions, compatibility shims without a concrete
  consumer, or new persistent state not required by the task.
- Follow current Qt widgets, signals, object ownership, and service APIs.
- Add focused tests proportional to risk. Include failure, cancellation, stale
  state, or cleanup cases when the changed path has them.
- Do not edit `uv.lock` unless dependency resolution is intentionally changing.
- Do not revert unrelated worktree changes. Inspect the final diff for generated
  files, absolute local paths, secrets, and accidental metadata churn.

## Verification

Run the narrowest relevant test while iterating. Before completing a code
change, run the full CI-equivalent checks unless the task's scope makes a check
irrelevant; report anything not run.

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q <focused-tests>
uv lock --check
uv run --locked ruff check oh_my_ruyi tests
uv run --locked ruff format --check oh_my_ruyi tests
uv run --locked python -m compileall -q oh_my_ruyi tests
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
uv build
```

For localization changes, always include:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_i18n.py tests/test_packaging.py
```

For storage or flashing changes, run at least the storage tests and the relevant
main-window interaction tests before the full suite.

## Keeping This File Current

Update `AGENTS.md` in the same change when a durable architecture boundary,
safety invariant, module owner, localization rule, or required verification
command changes. Keep explanations for humans in the Development Guide and keep
this file concise, imperative, and optimized for pre-change agent context.
