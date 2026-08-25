# Development Guide

This is the entry point for contributors and coding agents working on Oh My
Ruyi. It explains where a change belongs, which boundaries it must preserve,
how to run the application, and how to verify a change. User-visible behavior
belongs in the [project README](../README.md); compact, durable agent rules
belong in [AGENTS.md](../AGENTS.md).

The guide is split by the questions a contributor normally asks. Read the
architecture document before changing ownership or data flow, the safety
document before touching storage/version/repository/destructive operations, and
the testing document before changing CI or packaging.

## Topic Map

| Topic | Read this when... |
| --- | --- |
| [Architecture](architecture.md) | You need module ownership, object relationships, state flow, signals, or thread boundaries. |
| [Operations and Safety](operations-and-safety.md) | You touch repositories, downloads, activation, first-use, storage, flashing, sudo, or trusted inputs. |
| [Development Workflows](development-workflows.md) | You add a preset, locale, worker, child process, adapter behavior, metadata, or Rich output. |
| [Testing and Packaging](testing-and-packaging.md) | You add tests, change fixtures, run CI, build wheels, or build release binaries. |

## Project Snapshot

Oh My Ruyi is a PySide6 frontend for the `ruyi` package manager. It imports
ruyi's Python APIs for metadata, package installation, repository configuration,
and device provisioning. It does not own board-specific metadata, package
resolution, or flashing strategy semantics.

The main runtime path is:

```text
oh_my_ruyi.__main__
  -> app.bootstrap
  -> locale + GlobalConfig + QtRuyiLogger
  -> ProvisionMainWindow
       -> controllers
       -> views and mixins
       -> workers / QProcess children
       -> infra facades
       -> ruyi APIs and external commands
```

The application has four top-level tabs:

1. Version Management
2. Repo Management
3. Device Provision
4. About

The Device Provision tab contains the eleven-step workflow documented in
[Architecture](architecture.md). The Version and first-use flows reuse the
same workers and dialogs; they do not maintain a second implementation of
download or activation.

## Prerequisites

- Python 3.11 or newer. CI currently covers Python 3.11 and 3.12.
- `uv` for environments, locked dependencies, and builds.
- A graphical Qt session for interactive use.
- The host Qt runtime libraries required by PySide6.

Set up the locked development environment:

```bash
uv sync --locked --group dev
```

Run the GUI from a graphical session:

```bash
uv run --locked oh-my-ruyi
uv run --locked python -m oh_my_ruyi
```

The GUI needs `DISPLAY` or `WAYLAND_DISPLAY`. Headless tests use:

```bash
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
```

The normal `ruyi` dependency comes from the configured package index. A local
ruyi checkout is injected only for intentional ruyi development:

```bash
uv run --with-editable /path/to/ruyi oh-my-ruyi
```

Do not edit `pyproject.toml` or `uv.lock` for a temporary editable checkout.

## Ownership Quick Reference

| Change | Owner | Focused tests |
| --- | --- | --- |
| Startup/config/locale | `app/bootstrap.py`, `i18n.py` | `test_i18n.py`, `test_smoke.py` |
| Wizard state/FSM | `core/state.py`, `core/state_machine.py`, `core/models.py` | `test_provision_wizard.py` |
| Provision download/preparation | `controllers/provision_controller.py` | `test_provision_wizard.py`, `test_ruyi_adapter.py` |
| Repository init/sync | `controllers/repo_controller.py` | `test_main_window.py`, `test_provision_wizard.py` |
| Metadata/config facade | `infra/ruyi_adapter.py`, `infra/repo_manager.py` | `test_ruyi_adapter.py`, `test_repo_manager.py` |
| Version lifecycle | `infra/version_manager.py`, `_version_management_mixin.py` | `test_version_manager.py`, `test_version_management_ui.py` |
| Storage topology/fingerprint | `infra/os_storage.py`, `_provision_wizard_mixin.py` | `test_os_storage.py`, `test_provision_wizard.py` |
| Provision pages and Qt transitions | `_provision_wizard_mixin.py`, `main_window.py` | `test_provision_wizard.py`, `test_main_window.py` |
| First-use orchestration | `first_use.py`, `_first_use_mixin.py` | `test_first_use.py`, `test_first_use_flow.py` |
| Rich/log output | `qt_logger.py`, `rich_output.py`, `qprocess_utils.py` | `test_smoke.py`, `test_repo_manager_tab.py` |
| Worker/thread lifecycle | `workers.py`, `worker_manager.py` | `test_smoke.py`, focused owner tests |
| Child commands/frozen dispatch | `processes/*.py`, `__main__.py` | `test_packaging.py`, release build |

For full responsibilities, call graphs, state transitions, and signal ownership,
read [Architecture](architecture.md). For the safety rules attached to these
owners, read [Operations and Safety](operations-and-safety.md).

## Required Contracts

These are intentionally summarized here. The detailed rationale and operation
sequences live in the linked topic documents and the concise rules in
`AGENTS.md`.

- Keep ruyi metadata, package, and strategy semantics in ruyi or the existing
  Qt-free adapter. Do not duplicate them in widgets.
- Keep repository I/O, downloads, package preparation, disk discovery,
  telemetry setup, and flashing off the Qt UI thread.
- Keep widget mutation and UI state transitions on the Qt thread.
- Preserve worker ownership, signal cleanup, cancellation, process-group
  termination, and late-signal identity checks.
- Keep `WizardState` and `ProvisionStateMachine` in the controller boundary;
  backward navigation must invalidate dependent state.
- Mutate repository TOML only through ruyi's `ConfigEditor`.
- Keep the built-in `ruyisdk` repository first and non-removable.
- Route Rich renderables, ANSI styles, links, progress, and carriage-return
  updates through the existing output boundary.
- Revalidate storage fingerprints and mount state at destructive boundaries.
- Treat release URLs, repository remotes, local metadata, and strategy plugins
  as trusted inputs. Custom release URLs use HTTPS but have no signature or
  checksum verification.

## Verification Entry Point

The complete command matrix, platform differences, mocks, wheel inspection,
and frozen release validation are in [Testing and Packaging](testing-and-packaging.md).
The short form is:

```bash
uv lock --check
uv run --locked ruff check oh_my_ruyi tests
uv run --locked ruff format --check oh_my_ruyi tests
uv run --locked python -m compileall -q oh_my_ruyi tests
QT_QPA_PLATFORM=offscreen uv run --locked python -m pytest -q
uv build
```

Before a release, also run the PyInstaller command in the testing document and
exercise its `-m oh_my_ruyi.processes.*` and `-m ruyi` dispatch paths.
