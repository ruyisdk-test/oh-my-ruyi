"""Pure first-launch eligibility checks.

The policy is kept independent of Qt so it can be tested with temporary paths
and an injected ``which`` implementation.  The dialog only renders the result
and the main window still owns the setup operations.
"""

from __future__ import annotations

import os
import shutil
import sys
from pathlib import Path
from typing import Callable


def should_offer_first_use_setup(
    telemetry_installation: Path,
    managed_data_directory: Path,
    *,
    path: str | None = None,
    runtime_executable: Path | None = None,
    which: Callable[..., str | None] = shutil.which,
) -> bool:
    """Return whether telemetry, PATH, and managed-data prerequisites are clear."""
    return (
        not Path(telemetry_installation).exists()
        and _find_external_ruyi(
            path=path,
            runtime_executable=runtime_executable,
            which=which,
        )
        is None
        and not Path(managed_data_directory).exists()
    )


def _find_external_ruyi(
    *,
    path: str | None,
    runtime_executable: Path | None,
    which: Callable[..., str | None],
) -> str | None:
    """Find ``ruyi`` outside the scripts directory of the running Python env."""
    runtime_executable = (
        Path(sys.executable) if runtime_executable is None else Path(runtime_executable)
    )
    runtime_scripts = runtime_executable.parent.resolve(strict=False)
    search_path = os.environ.get("PATH", os.defpath) if path is None else path
    external_directories = [
        entry
        for entry in search_path.split(os.pathsep)
        if Path(entry or os.curdir).expanduser().resolve(strict=False)
        != runtime_scripts
    ]
    if not external_directories:
        return None
    return which("ruyi", path=os.pathsep.join(external_directories))


__all__ = ["should_offer_first_use_setup"]
