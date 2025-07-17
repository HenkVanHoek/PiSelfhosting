# src/config_tools/config_manager.py
import configparser
import logging

logger = logging.getLogger(__name__)


class ConfigManager:
    """Manages reading and writing of configuration settings."""

    def __init__(self, env_file=".env"):
        """
        Initializes the ConfigManager.

        Args:
            env_file (str, optional): The path to the .env file.
                                      Defaults to ".env" in the project root.
        """
        self.env_file = env_file

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
