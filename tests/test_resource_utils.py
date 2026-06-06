# tests/test_resource_utils.py

import sys
from pathlib import Path

from src.utils.resource_utils import resource_path


def test_resource_path_in_dev_mode():
    """Tests if the resource_path function returns the correct path when not running

    in a PyInstaller bundle (i.e., in a normal development/test environment).
    """
    # Arrange
    # The `resource_path` function calculates an absolute path from the project root.
    # Its logic is based on the location of the `resource_utils.py` file.
    # To verify its output, we must determine the project root from this test's location

    # Get the directory containing this test file (e.g., .../tests)
    current_test_dir = Path(__file__).resolve().parent

    # The project root is one level up from the 'tests' directory.
    project_root = current_test_dir.parent

    relative_path_to_test = Path("my_folder") / "my_file.txt"

    # The expected full path is the project root joined with the relative path.
    expected_path = project_root / relative_path_to_test

    # Act
    actual_path = resource_path(str(relative_path_to_test))

    # Assert
    assert str(actual_path) == str(expected_path)


def test_resource_path_in_pyinstaller_mode(monkeypatch):
    """Tests if the resource_path function returns the correct path when

    simulating a PyInstaller environment.
    """
    # Arrange: Mock the sys attributes that PyInstaller sets when running as a bundle.
    # We use monkeypatch to set these attributes only for the duration of this test.
    # The `raising=False` argument allows creating the attribute if it doesn't exist.
    temp_bundle_dir = "/tmp/_MEI12345"
    monkeypatch.setattr(sys, "frozen", True, raising=False)
    monkeypatch.setattr(sys, "_MEIPASS", temp_bundle_dir, raising=False)

    relative = "my_folder/my_file.txt"
    expected_path = str(Path(temp_bundle_dir) / relative)

    # Act: Call the function.
    actual_path = resource_path(relative)

    # Assert: Check if the function correctly used the _MEIPASS path.
    assert str(actual_path) == expected_path
