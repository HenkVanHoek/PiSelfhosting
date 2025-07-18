import configparser
import logging
import os
import sys

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages configuration settings and paths."""

    def __init__(self):
        """
        Initializes the ConfigManager with fixed paths used in the application.
        """
        self.project_root = self._get_project_root()
        self.base_templates_path = "component_templates"

        # Log initialization details
        logger.info("ConfigManager initialized:")

        run_mode = (
            "PyInstaller bundle" if getattr(sys, "frozen", False) else "Development"
        )
        logger.info(f"Running mode: {run_mode}")
        logger.info(f"Project root: {self.project_root}")
        logger.info(f"Base templates path: {self.base_templates_path}")

        templates_full_path = os.path.join(self.project_root, self.base_templates_path)
        logger.info(f"Full base templates path: {templates_full_path}")

        # Verify templates directory exists
        if os.path.exists(templates_full_path):
            logger.info(f"Templates directory exists at: {templates_full_path}")
            # List first level of template directories
            try:
                templates = os.listdir(templates_full_path)
                logger.info("Available component templates: %s", ", ".join(templates))
            except Exception as e:
                logger.warning(f"Could not list templates directory: {e}")
        else:
            logger.warning(f"Templates directory not found at: {templates_full_path}")

    @staticmethod
    def _get_project_root():
        """
        Returns the correct root path whether running from source or as a
        PyInstaller bundle.

        Returns:
            str: Absolute path to the project root
        """
        if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
            # Running in a PyInstaller bundle
            # noinspection PyProtectedMember
            root_path = sys._MEIPASS
            logger.info(f"Running from PyInstaller bundle. MEIPASS path: {root_path}")
        else:
            # Running in development
            root_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            logger.info(f"Running in development mode. Project root: {root_path}")
        return root_path

    def get_component_template_path(self, component_id: str) -> str:
        """
        Returns the absolute template path for a specific component.
        Ensures cross-platform compatibility and correct resolution whether
        running from source or in a PyInstaller bundle.

        Args:
            component_id: The ID of the component to get the template path for.

        Returns:
            str: Absolute path to the component's template directory
        """
        template_path = os.path.join(
            self.project_root, self.base_templates_path, component_id
        )
        logger.info(f"Resolving template path for component '{component_id}':")
        logger.info(f"  - Absolute path: {template_path}")

        # Verify the specific component template directory exists
        if os.path.exists(template_path):
            logger.info("  - Template directory exists")
            try:
                template_contents = os.listdir(template_path)
                logger.info("  - Available templates: %s", ", ".join(template_contents))
            except Exception as e:
                logger.warning(f"  - Could not list template directory contents: {e}")
        else:
            logger.warning(f"  - Template directory not found at: {template_path}")

        return template_path

    @staticmethod
    def load_settings_from_ini(ini_filepath):
        """
        Loads settings from a given .ini file.

        Args:
            ini_filepath (str): The path to the .ini configuration file.

        Returns:
            dict: A dictionary of the settings loaded from the file.
        """
        try:
            config = configparser.ConfigParser()
            config.read(ini_filepath)
            if "settings" in config:
                logger.info(f"Successfully loaded settings from {ini_filepath}")
                return dict(config["settings"])
            else:
                logger.warning(f"'settings' section not found in {ini_filepath}")
                return {}
        except Exception as e:
            logger.error(f"Failed to load settings from {ini_filepath}: {e}")
            return {}

    def update_env_file(self, settings):
        """
        Updates the .env file with the given settings.
        Creates the file if it doesn't exist.

        Args:
            settings (dict): A dictionary of key-value pairs to write to the .env file.
        """
        try:
            # This is a simple implementation. For more complex use cases,
            # a library like python-dotenv might be better to preserve comments etc.
            with open(self.env_file, "a") as f:
                for key, value in settings.items():
                    # Ensure keys are uppercase, a common convention for .env files
                    f.write(f"{key.upper()}={value}\n")
            logger.info(f"Successfully updated .env file at {self.env_file}")
        except Exception as e:
            logger.error(f"Failed to update .env file: {e}")
