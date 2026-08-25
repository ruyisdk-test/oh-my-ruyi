"""Application and frozen child-process entry point."""

from __future__ import annotations

import importlib
import sys


_CHILD_MODULES = {
    "oh_my_ruyi.processes.download_child",
    "oh_my_ruyi.processes.repo_news_child",
    "oh_my_ruyi.processes.repo_update_child",
    "oh_my_ruyi.processes.version_activation_child",
}


def _run_embedded_command(argv: list[str]) -> int | None:
    """Dispatch ``QProcess`` commands when ``sys.executable`` is frozen."""
    if len(argv) < 3 or argv[1] != "-m":
        return None

    module_name = argv[2]
    if module_name in _CHILD_MODULES:
        command_argv = [argv[0], *argv[3:]]
        module = importlib.import_module(module_name)
        main = getattr(module, "main")
    elif module_name == "ruyi":
        command_argv = ["ruyi", *argv[3:]]
        module = importlib.import_module("ruyi.__main__")
        main = getattr(module, "entrypoint")
    else:
        return None

    original_argv = sys.argv
    sys.argv = command_argv
    try:
        try:
            result = main(command_argv[1:]) if module_name in _CHILD_MODULES else main()
        except SystemExit as exc:
            result = exc.code
    finally:
        sys.argv = original_argv
    if result is None:
        return 0
    return result if isinstance(result, int) else 1


def main(argv: list[str] | None = None) -> int:
    argv = sys.argv if argv is None else argv
    if (result := _run_embedded_command(argv)) is not None:
        return result
    from oh_my_ruyi.app import run

    return run(argv)


if __name__ == "__main__":
    sys.exit(main())
