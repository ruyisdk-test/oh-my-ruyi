"""Child process entry points for isolated execution."""

from .download_child import main as download_child_main
from .repo_news_child import main as repo_news_child_main
from .repo_update_child import main as repo_update_child_main
from .version_activation_child import main as version_activation_child_main

__all__ = [
    "download_child_main",
    "repo_news_child_main",
    "repo_update_child_main",
    "version_activation_child_main",
]
