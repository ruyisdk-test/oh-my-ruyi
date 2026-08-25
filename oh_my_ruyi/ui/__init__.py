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
from .repo_tables import populate_repository_tables
from .provision_pages import ProvisionPageWidgets, build_provision_pages
from .version_dialogs import VersionDownloadDialog
from .version_tables import (
    populate_available_versions_table,
    populate_installed_versions_table,
    set_row_foreground,
)
from .theme import stylesheet_for_colors, theme_colors

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
    "populate_repository_tables",
    "ProvisionPageWidgets",
    "build_provision_pages",
    "populate_available_versions_table",
    "populate_installed_versions_table",
    "set_row_foreground",
    "stylesheet_for_colors",
    "theme_colors",
    "message_box",
]
