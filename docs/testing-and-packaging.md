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
| `test_core_state.py` | Qt-free state invalidation |
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

Hatchling packages the complete `oh_my_ruyi` package, including the classified
implementation packages `gui/`, `services/`, `runtime/`, `core/`,
`processes/`, `ui/`, and `locales/`. Inspect the wheel after `uv build`:

```bash
unzip -l dist/*.whl | rg 'oh_my_ruyi/(gui|services|runtime|core|processes|ui|locales)'
```

The package root contains only the package entry files. Child process modules
are canonical package submodules. A PyInstaller build must collect package
submodules and the ruyi package. The release build uses the checked-in spec:

```bash
uv run --locked --with pyinstaller pyinstaller --clean \
  oh-my-ruyi.spec
```

The spec sets the project path, collects application resources, includes every
`oh_my_ruyi.processes` child selected by the frozen dispatcher, and explicitly
includes `_cffi_backend`, which is required by pygit2/cffi and is not reliably
inferred from dynamic ruyi imports. After building, exercise a child entry
point with invalid arguments and query ruyi in a disposable configuration;
never point a frozen smoke test at a real activation link or block device:

```bash
QT_QPA_PLATFORM=offscreen ./dist/oh-my-ruyi \
  -m oh_my_ruyi.processes.repo_update_child --help
QT_QPA_PLATFORM=offscreen ./dist/oh-my-ruyi -m ruyi version
```

The first command should produce the child usage error rather than opening a
second GUI; the second should produce a version report or a normal ruyi
configuration error, not a recursive GUI launch or import error.

The tag workflow runs additional frozen checks before uploading artifacts. It
checks `-m ruyi version`, the activation child, repository child argument
validation, and a GUI process that remains alive for the smoke interval. A
`ModuleNotFoundError` from any dynamic child import fails the workflow.

## Failure Triage

Classify failures before changing code:

- import/compile failure: stale relative import after a move;
- missing fixture/dependency: environment issue, report it separately;
- signal timeout: worker/process ownership or cleanup regression;
- wrong patched behavior: stale import or wrong module-global patch target;
- changed output: locale/Rich target routing regression;
- storage test failure: fail-closed safety behavior, never relax the check.

Always inspect `git diff --check`, generated files, package contents, and the
final module map before completing a refactor.
