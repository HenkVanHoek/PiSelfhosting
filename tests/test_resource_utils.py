# tests/test_resource_utils.py
import os
import sys

# Since 'src' is in your pythonpath (from pyproject.toml), you can import directly.
from utils.resource_utils import resource_path


def test_resource_path_in_dev_mode():
    """
    Tests if the resource_path function returns the correct path when
    running in a normal development environment (i.e., sys._MEIPASS is not set).
    """
    # Arrange: Define a relative path and determine the expected absolute path.
    project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))
    relative = os.path.join("my_folder", "my_file.txt")
    expected_path = os.path.join(project_root, relative)

    # Act: Call the function.
    actual_path = resource_path(relative)

    # Assert: Check if the actual path matches the expected path.
    assert actual_path == expected_path


def test_resource_path_in_pyinstaller_mode(mocker):
    """
    Tests if the resource_path function returns the correct path when
    simulating a PyInstaller environment by setting sys._MEIPASS.
    """
    # Arrange: Mock the sys._MEIPASS attribute. We use mocker.patch.object
    # with `create=True` because this attribute does not normally exist.
    temp_bundle_dir = "/tmp/_MEI12345"
    mocker.patch.object(sys, "_MEIPASS", temp_bundle_dir, create=True)

    relative = os.path.join("my_folder", "my_file.txt")
    expected_path = os.path.join(temp_bundle_dir, relative)

    # Act: Call the function.
    actual_path = resource_path(relative)

    # Assert: Check if the function correctly used the _MEIPASS path.
    assert actual_path == expected_path
