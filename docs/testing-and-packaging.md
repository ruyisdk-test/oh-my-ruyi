# Testing And Packaging

Tests are organized by ownership rather than by widget size. The suite uses
offscreen Qt and mocks external boundaries so a refactor can prove behavior
without requiring a live metadata checkout, network, sudo, USB device, or raw
disk.

## Test Map

| Test file | Main contract |
| --- | --- |
| `test_smoke.py` | Imports, construction, worker thread start, logger and Rich rendering |
| `test_i18n.py` | Locale precedence, catalogs, Qt text and subprocess environment |
| `test_core_first_use_policy.py` | Qt-free first-use eligibility predicate |
| `test_core_state.py` | Qt-free state invalidation and compatibility imports |
| `test_first_use.py` | First-use setup dialog and Qt integration |
| `test_host_storage.py` | Linux/macOS discovery, holders, mounts, fingerprints |
| `test_version_manager.py` | Release parsing, downloads, activation, paths, telemetry |
| `test_repo_manager.py` | Config parsing, presets, `ConfigEditor` mutations |
| `test_repo_manager_tab.py` | Repository dialogs, QProcess cancellation and news |
| `test_ruyi_facade_repo.py` | Qt-free ruyi boundary and display adapters |
| `test_main_window_interactions.py` | Cross-step state, first-use reuse, storage and flash safeguards |

New pure policy tests belong beside their owner. New reusable Qt widgets need
construction/signal tests. A change to a shared worker or adapter deserves both
success and failure coverage; add cancellation/stale-state coverage when that
path exists.

## Local Commands

Use the locked environment in normal development:

```bash
uv sync --locked --group dev
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q tests/test_smoke.py
uv lock --check
uv run --locked ruff check oh_my_ruyi tests
uv run --locked ruff format --check oh_my_ruyi tests
uv run --locked python -m compileall -q oh_my_ruyi tests
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
uv build
```

If `uv` cannot write its cache, set a project-local cache directory or repair
the environment before treating the failure as a code regression. Do not edit
the lockfile merely to make a local environment work.

For locale changes run:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_i18n.py tests/test_packaging.py
```

For storage/flashing changes run the storage tests and the relevant interaction
tests before the complete suite.

## Mock Boundaries

Mock network responses in release tests, `shutil.which` and XDG paths in
first-use tests, `diskutil`/`/sys`/mount data in storage tests, `sudo` and
subprocess creation in activation/flash tests, and ruyi repository objects in
facade tests. Keep monkeypatch targets at the owning module: moving a function
to a different module can make a test patch the wrong global and is therefore a
behavioral change.

## Async Test Pattern

Use `pytest-qt`'s `qtbot` for signals and QProcess/QThread completion. Assert
that a worker runs off the QApplication thread and that its thread reference
is cleaned. For QProcess cancellation, assert `SIGTERM`, the bounded kill
fallback, output collection, and final classification. Avoid sleeps; wait on a
signal or a state predicate with a timeout.

## Wheel And Frozen Builds

Hatchling packages the complete `oh_my_ruyi` package, including `core/`,
`processes/`, `ui/`, and `locales/`. Inspect the wheel after `uv build`:

```bash
unzip -l dist/*.whl | rg 'oh_my_ruyi/(core|processes|ui|locales)'
```

The flat child wrappers are included because existing command paths remain
supported. A PyInstaller build must collect package submodules and the ruyi
package. After building, exercise the child entry points in a disposable
configuration; never point a frozen smoke test at a real activation link or
block device.

## Failure Triage

Classify failures before changing code:

- import/compile failure: stale relative import after a move;
- missing fixture/dependency: environment issue, report it separately;
- signal timeout: worker/process ownership or cleanup regression;
- wrong patched behavior: module-global compatibility break;
- changed output: locale/Rich target routing regression;
- storage test failure: fail-closed safety behavior, never relax the check.

Always inspect `git diff --check`, generated files, package contents, and the
final module map before completing a refactor.
