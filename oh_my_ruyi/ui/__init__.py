"""Reusable Qt-facing presentation helpers.

The main window remains the owner of application state and transitions.  This
package contains widgets that have a small, well-defined contract and can be
used by the version and first-use flows without duplicating their behavior.
"""

from .common import (
    FASTBOOT_PROGRAM,
    STORAGE_FINGERPRINT_ROLE,
    STORAGE_MOUNTED_ROLE,
    VersionTableItem,
    configure_table,
    message_box,
)
from .first_use_dialog import FirstUseDialog, SETUP_STEPS
from .repo_dialogs import RepoSourceDialog, RepoUpdateDialog
from .version_dialogs import VersionDownloadDialog

__all__ = [
    "FASTBOOT_PROGRAM",
    "FirstUseDialog",
    "SETUP_STEPS",
    "STORAGE_FINGERPRINT_ROLE",
    "STORAGE_MOUNTED_ROLE",
    "VersionDownloadDialog",
    "VersionTableItem",
    "configure_table",
    "RepoSourceDialog",
    "RepoUpdateDialog",
    "message_box",
]
