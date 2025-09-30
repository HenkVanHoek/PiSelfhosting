# src/utils/resource_utils.py
import os
import sys


def resource_path(relative_path):
    """Get absolute path to a resource, works for dev and for PyInstaller"""
    try:
        # PyInstaller creates a temp folder and stores path in _MEIPASS.
        # The # noinspection comment tells the PyCharm linter to ignore this specific
        # warning, as this is the officially documented way to get the path.
        # noinspection PyProtectedMember
        base_path = sys._MEIPASS
    except AttributeError:
        # An AttributeError will be raised if _MEIPASS does not exist, which means
        # we are not running in a PyInstaller bundle. We are in development.
        base_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

    return os.path.join(base_path, relative_path)


# START OF FIX: Add function to provide global template context for Jinja
def get_global_template_context():
    """
    Provides the required context variables for the base Jinja templates
    to access global macros and placeholder values (like DOTENV).
    """
    # NOTE: This is the minimal set required to prevent the 'DOTENV'
    # is undefined error during editor_app rendering.
    return {
        "DOTENV": {},
        "CONFIG_BASE_PATH": "/default/path",
    }


# END OF FIX: Add function to provide global template context for Jinja
