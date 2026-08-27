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
| `test_ruyi_facade_repo.py` | Qt-free repository selection and synchronization boundary |
| `test_ruyi_facade_provisioning.py` | Host-supported image, variant, and device filtering |
| `test_ruyi_compatibility.py` | Real installed ruyi API and first-use CLI upgrade contracts |
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

## Ruyi Upgrade Compatibility

The locked matrix proves the application against the exact `ruyi` version in
`uv.lock`; it cannot detect a breaking release that still satisfies the
dependency range in `pyproject.toml`. The `ruyi-compatibility` CI job therefore
resolves only `ruyi` to the newest compatible release, including prereleases,
and runs the complete suite on Python 3.12. The rewritten lockfile exists only
inside that CI checkout and is never committed by the job.

`tests/test_ruyi_compatibility.py` is the focused upgrade tripwire. Unlike the
facade's branch-oriented unit tests, it must use the installed ruyi objects and
entry points rather than monkeypatching them:

1. A deterministic in-memory repository supplies real
   `BoundPackageManifest` objects, entity relationships, and side-effect-free
   plugin functions. The test exercises ruyi's atom parsing, version lookup,
   `ProvisionStrategyProvider`, strategy resolution, partition maps, pretend
   output, and flash dispatch through `services/ruyi_facade.py`.
2. A missing package goes through the real `do_install_atoms` entry point and
   fails before any download, which checks the imported installation call
   contract without network or filesystem mutation.
3. The installed `ruyi` console script runs in a real pseudo-terminal for all
   three first-use telemetry choices. Every XDG root is temporary, repository
   access is disabled, and `pm_telemetry_url` is empty, so prompt ordering and
   persisted modes are tested without reading user state or uploading data.

Run the focused gate in the normal locked environment with:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q \
  tests/test_ruyi_compatibility.py
```

To reproduce the latest-compatible job, use a disposable checkout because the
first command intentionally rewrites its `uv.lock`:

```bash
uv lock --upgrade-package ruyi --prerelease allow
uv sync --locked --python 3.12 --group dev
uv run --locked python -c \
  "import importlib.metadata; print(importlib.metadata.version('ruyi'))"
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
```

When this gate fails after a ruyi release, first identify the changed imported
API or CLI protocol. Update the facade or first-use adapter deliberately and
retain coverage for both the locked and candidate versions; do not replace the
real ruyi symbol with a stub merely to make the upgrade gate pass.

## Mock Boundaries

Mock network responses in release tests, `shutil.which` and XDG paths in
first-use tests, `diskutil`/`/sys`/mount data in storage tests, `sudo` and
subprocess creation in activation/flash tests, and ruyi repository objects in
facade tests. The explicit exception is `test_ruyi_compatibility.py`, whose
ruyi imports must remain real while its data and side-effect boundaries stay
local. Keep monkeypatch targets at the owning module: moving a function to a
different module can make a test patch the wrong global and is therefore a
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
