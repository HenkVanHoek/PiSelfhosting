import os
import sys

from src.utils.resource_utils import resource_path


def test_resource_path_in_dev_mode():
    """
    Tests if the resource_path function returns the correct path when not running
    in a PyInstaller bundle (i.e., in a normal development/test environment).
    """
    # Arrange
    # The `resource_path` function calculates an absolute path from the project root.
    # Its logic is based on the location of the `resource_utils.py` file.
    # To verify its output, we must determine the project root from this test's location

    # Get the directory containing this test file (e.g., .../tests)
    current_test_dir = os.path.dirname(os.path.abspath(__file__))

    # The project root is one level up from the 'tests' directory.
    project_root = os.path.dirname(current_test_dir)

    relative_path_to_test = os.path.join("my_folder", "my_file.txt")

    # The expected full path is the project root joined with the relative path.
    expected_path = os.path.join(project_root, relative_path_to_test)

    # Act
    actual_path = resource_path(relative_path_to_test)

    # Assert
    assert actual_path == expected_path


def test_resource_path_in_pyinstaller_mode(monkeypatch):
    """
    Tests if the resource_path function returns the correct path when
    simulating a PyInstaller environment.
    """
    # Arrange: Mock the sys attributes that PyInstaller sets when running as a bundle.
    # We use monkeypatch to set these attributes only for the duration of this test.
    # The `raising=False` argument allows creating the attribute if it doesn't exist.
    temp_bundle_dir = "/tmp/_MEI12345"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", temp_bundle_dir, raising=False)

    relative = os.path.join("my_folder", "my_file.txt")
    expected_path = os.path.join(temp_bundle_dir, relative)

    # Act: Call the function.
    actual_path = resource_path(relative)

    # Assert: Check if the function correctly used the _MEIPASS path.
    assert actual_path == expected_path
