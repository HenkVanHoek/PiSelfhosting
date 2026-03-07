# tests/test_setup_manager.py
import unittest
from pathlib import Path
from unittest.mock import MagicMock

from src.managers.component_reader import ComponentReader
from src.managers.setup_manager import SetupManager


class TestSetupManager(unittest.TestCase):
    """
    Test suite for the refactored SetupManager.
    """

    def setUp(self):
        """Set up the test environment with a temporary path."""
        self.mock_reader = MagicMock(spec=ComponentReader)
        self.test_dir = Path("./tmp_setup_test")
        self.setup_manager = SetupManager(
            component_manager=self.mock_reader, output_dir=self.test_dir
        )

    def tearDown(self):
        """Clean up temporary directory after tests."""
        if self.test_dir.exists():
            import shutil

            shutil.rmtree(self.test_dir)

    def test_initialize_environment_creates_directories(self):
        """Test if the manager creates the base and log directories."""
        success = self.setup_manager.initialize_environment()

        self.assertTrue(success)
        self.assertTrue(self.test_dir.exists())
        self.assertTrue((self.test_dir / "logs").exists())

    def test_verify_component_setup_success(self):
        """Test component verification when it exists in metadata."""
        self.mock_reader.get_component_details.return_value = {"name": "Test"}

        result = self.setup_manager.verify_component_setup("existing-app")

        self.assertTrue(result)
        self.mock_reader.get_component_details.assert_called_with("existing-app")

    def test_get_setup_report(self):
        """Verify the structure of the setup report."""
        self.mock_reader.get_all_components.return_value = {"a": {}, "b": {}}

        # Initialize first to set status to ready
        self.setup_manager.initialize_environment()
        report = self.setup_manager.get_setup_report()

        self.assertEqual(report["status"], "ready")
        self.assertEqual(report["components_available"], 2)
        self.assertIn("base_path", report)
