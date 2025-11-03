"""Configuration loader for GMC Geiger MQTT bridge."""

import logging
import os
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

from .models import DeviceConfig, MQTTConfig


logger = logging.getLogger(__name__)


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""

    pass


class Config:
    """Application configuration manager."""

    def __init__(self, config_path: Optional[str] = None):
        """
        Initialize configuration.

        Args:
            config_path: Path to config file. If None, uses default locations.
        """
        self.config_path = config_path or self._find_config_file()
        self._data: Dict[str, Any] = {}
        self.load()

    def _find_config_file(self) -> str:
        """
        Find the configuration file in default locations.

        Returns:
            Path to config file

        Raises:
            ConfigError: If no config file is found
        """
        # Search locations in order of priority
        search_paths = [
            "config.yaml",
            "config.yml",
            os.path.expanduser("~/.config/gmc-geiger-mqtt/config.yaml"),
            "/etc/gmc-geiger-mqtt/config.yaml",
        ]

        for path in search_paths:
            if os.path.isfile(path):
                logger.info(f"Found config file at: {path}")
                return path

        raise ConfigError(
            f"No configuration file found. Searched: {', '.join(search_paths)}"
        )

    def load(self) -> None:
        """
        Load configuration from file.

        Raises:
            ConfigError: If config file cannot be loaded or is invalid
        """
        try:
            logger.info(f"Loading configuration from: {self.config_path}")
            with open(self.config_path, "r") as f:
                self._data = yaml.safe_load(f) or {}
        except FileNotFoundError:
            raise ConfigError(f"Config file not found: {self.config_path}")
        except yaml.YAMLError as e:
            raise ConfigError(f"Invalid YAML in config file: {e}")
        except Exception as e:
            raise ConfigError(f"Failed to load config: {e}")

        self._validate()

    def _validate(self) -> None:
        """
        Validate the configuration data.

        Raises:
            ConfigError: If configuration is invalid
        """
        # Check required sections
        if "device" not in self._data:
            raise ConfigError("Missing required 'device' section in config")

        device_config = self._data["device"]
        if "port" not in device_config:
            raise ConfigError("Missing required 'device.port' in config")

        # Validate device port exists (if it's a device file)
        port = device_config["port"]
        if port.startswith("/dev/") and not os.path.exists(port):
            logger.warning(f"Device port {port} does not exist (yet)")

    def get_device_config(self) -> DeviceConfig:
        """
        Get device configuration.

        Returns:
            DeviceConfig object
        """
        device_data = self._data.get("device", {})
        return DeviceConfig(
            port=device_data.get("port"),
            baudrate=device_data.get("baudrate", 115200),
            timeout=device_data.get("timeout", 5.0),
        )

    def get_logging_config(self) -> Dict[str, Any]:
        """
        Get logging configuration.

        Returns:
            Dictionary with logging settings
        """
        return self._data.get(
            "logging",
            {
                "level": "INFO",
                "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
            },
        )

    def get_sampling_config(self) -> Dict[str, Any]:
        """
        Get sampling configuration.

        Returns:
            Dictionary with sampling settings
        """
        return self._data.get("sampling", {"interval": 60, "window_size": 10})

    def get_mqtt_config(self) -> MQTTConfig:
        """
        Get MQTT configuration.

        Returns:
            MQTTConfig object
        """
        mqtt_data = self._data.get("mqtt", {})
        return MQTTConfig(
            enabled=mqtt_data.get("enabled", False),
            broker=mqtt_data.get("broker", "localhost"),
            port=mqtt_data.get("port", 1883),
            username=mqtt_data.get("username") or None,
            password=mqtt_data.get("password") or None,
            client_id=mqtt_data.get("client_id", "gmc-geiger-mqtt"),
            topic_prefix=mqtt_data.get("topic_prefix", "gmc/geiger"),
            qos_realtime=mqtt_data.get("qos_realtime", 0),
            qos_aggregate=mqtt_data.get("qos_aggregate", 1),
            qos_info=mqtt_data.get("qos_info", 1),
            retain_info=mqtt_data.get("retain_info", True),
            retain_availability=mqtt_data.get("retain_availability", True),
            homeassistant_discovery=mqtt_data.get("homeassistant_discovery", False),
            homeassistant_prefix=mqtt_data.get("homeassistant_prefix", "homeassistant"),
        )

    def get_conversion_factor(self) -> float:
        """
        Get CPM to µSv/h conversion factor.

        Returns:
            Conversion factor
        """
        conversion_data = self._data.get("conversion", {})
        return conversion_data.get("cpm_to_usv_factor", 0.0065)

    def get(self, key: str, default: Any = None) -> Any:
        """
        Get a configuration value by key.

        Args:
            key: Configuration key (supports dot notation, e.g., 'device.port')
            default: Default value if key not found

        Returns:
            Configuration value or default
        """
        keys = key.split(".")
        value = self._data

        for k in keys:
            if isinstance(value, dict):
                value = value.get(k)
                if value is None:
                    return default
            else:
                return default

        return value if value is not None else default

    def __getitem__(self, key: str) -> Any:
        """Get configuration value using dictionary syntax."""
        value = self.get(key)
        if value is None:
            raise KeyError(f"Configuration key not found: {key}")
        return value

    def __repr__(self) -> str:
        """String representation of config."""
        return f"Config(path={self.config_path})"
