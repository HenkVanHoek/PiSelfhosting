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
