"""Privileged activation/deactivation subprocess entry point.

Launched through ``sudo -S`` by the activation and deactivation workers when
the parent of the managed ``/usr/local/bin/ruyi`` link is not user-writable.
It prints a single JSON object describing the resulting activation state.
"""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path

from ..infra.version_manager import activate_version, deactivate_version


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="version_activation_child")
    subparsers = parser.add_subparsers(dest="action", required=True)
    activate_parser = subparsers.add_parser("activate")
    activate_parser.add_argument("binary", type=Path)
    activate_parser.add_argument("directory", type=Path)
    activate_parser.add_argument("link", type=Path)
    activate_parser.add_argument("--backup-unmanaged", action="store_true")
    deactivate_parser = subparsers.add_parser("deactivate")
    deactivate_parser.add_argument("directory", type=Path)
    deactivate_parser.add_argument("link", type=Path)
    args = parser.parse_args(argv)
    if args.action == "activate":
        result = activate_version(
            args.binary,
            args.directory,
            link=args.link,
            backup_unmanaged=args.backup_unmanaged,
        )
        payload = {
            "target": os.fspath(result.state.target) if result.state.target else None,
            "version": result.state.version,
            "backup_path": (
                os.fspath(result.backup_path) if result.backup_path else None
            ),
        }
    else:
        state = deactivate_version(args.directory, link=args.link)
        payload = {"target": None, "version": state.version, "backup_path": None}
    print(json.dumps(payload))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
