import unittest
from unittest.mock import patch, mock_open
import json

from managers.component_manager import ComponentManager


class TestComponentManager(unittest.TestCase):
    """Unit tests for the ComponentManager class."""

    def setUp(self):
        """Prepare common mock data for tests."""
        self.mock_metadata_content = {
            "_piselfhosting": {
                "components_order": ["portainer", "homarr"]
            },
            "portainer": {"name": "Portainer", "has_configuration": True},
            "homarr": {"name": "Homarr", "has_configuration": True},
            "unconfigured_service": {"name": "No Config Service",
                                     "has_configuration": False}
        }
        self.mock_variables_content = {
            "variables": [
                {"name": "HOMARR_HTTP_PORT", "default": 7575}
            ]
        }

    @patch("pathlib.Path.exists", return_value=True)
    def test_initialization_and_enrichment(self, _mock_exists):
        """Verify that the manager enriches components with variables correctly."""
        mock_metadata_json = json.dumps(self.mock_metadata_content)
        mock_variables_json = json.dumps(self.mock_variables_content)

        m_open = mock_open()
        m_open.side_effect = [
            unittest.mock.mock_open(read_data=mock_metadata_json).return_value,
            unittest.mock.mock_open(read_data=mock_variables_json).return_value,
            unittest.mock.mock_open(read_data=mock_variables_json).return_value,
        ]

        with patch("builtins.open", m_open):
            manager = ComponentManager(
                metadata_file="/fake/path/config/components_metadata.json")

        homarr_details = manager.get_component_details("homarr")
        self.assertIn("required_variables", homarr_details)
        self.assertEqual(len(homarr_details["required_variables"]), 1)
        # --- FIX: Access the first element of the list before the key ---
        self.assertEqual(homarr_details["required_variables"][0]["name"],
                         "HOMARR_HTTP_PORT")

    @patch("pathlib.Path.exists", return_value=False)
    def test_get_all_components_sorted(self, _mock_exists):
        """Test that components are returned in the correct master order."""
        mock_metadata_json = json.dumps(self.mock_metadata_content)
        with patch("builtins.open", mock_open(read_data=mock_metadata_json)):
            manager = ComponentManager(
                metadata_file="/fake/path/config/components_metadata.json")

        all_components = manager.get_all_components()

        self.assertEqual(len(all_components), 3)
        # --- FIX: Access the first element of the list before the key ---
        self.assertEqual(all_components[0]['id'], 'portainer')
        self.assertEqual(all_components[1]['id'], 'homarr')
        self.assertEqual(all_components[2]['id'], 'unconfigured_service')


if __name__ == '__main__':
    unittest.main()