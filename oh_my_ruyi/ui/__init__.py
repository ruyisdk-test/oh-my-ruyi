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
from .about_page import AboutWidgets, build_about_page
from .first_use_dialog import FirstUseDialog, SETUP_STEPS
from .provision_content import (
    build_version_selection_rows,
    clear_layout_widgets,
    populate_choice_list,
    populate_package_list,
)
from .repo_dialogs import RepoSourceDialog, RepoUpdateDialog
from .repo_page import (
    ConfiguredPanelWidgets,
    PresetPanelWidgets,
    build_configured_panel,
    build_preset_panel,
)
from .repo_tables import populate_repository_tables
from .provision_pages import ProvisionPageWidgets, build_provision_pages
from .version_dialogs import VersionDownloadDialog
from .version_manager_panels import (
    VersionManagerPanelWidgets,
    build_version_manager_tab,
)
from .version_tables import (
    populate_available_versions_table,
    populate_installed_versions_table,
    set_row_foreground,
)
from .theme import stylesheet_for_colors, theme_colors

__all__ = [
    "FASTBOOT_PROGRAM",
    "AboutWidgets",
    "build_about_page",
    "build_version_selection_rows",
    "clear_layout_widgets",
    "FirstUseDialog",
    "SETUP_STEPS",
    "STORAGE_FINGERPRINT_ROLE",
    "STORAGE_MOUNTED_ROLE",
    "VersionDownloadDialog",
    "VersionManagerPanelWidgets",
    "build_version_manager_tab",
    "VersionTableItem",
    "configure_table",
    "RepoSourceDialog",
    "RepoUpdateDialog",
    "ConfiguredPanelWidgets",
    "PresetPanelWidgets",
    "build_configured_panel",
    "build_preset_panel",
    "populate_choice_list",
    "populate_package_list",
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
