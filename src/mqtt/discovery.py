"""Home Assistant MQTT Discovery for GMC Geiger counter."""

import json
import logging
from typing import Dict, Any

from ..models import DeviceInfo, MQTTConfig
from .client import MQTTClient


logger = logging.getLogger(__name__)


class HomeAssistantDiscovery:
    """
    Home Assistant MQTT Discovery implementation.

    Automatically registers sensors in Home Assistant via MQTT discovery protocol.
    See: https://www.home-assistant.io/integrations/mqtt/#mqtt-discovery
    """

    def __init__(
        self,
        mqtt_client: MQTTClient,
        config: MQTTConfig,
        device_info: DeviceInfo,
        device_id: str,
    ):
        """
        Initialize Home Assistant discovery.

        Args:
            mqtt_client: Connected MQTT client
            config: MQTT configuration
            device_info: Information about the GMC device
            device_id: Device identifier for topics
        """
        self.client = mqtt_client
        self.config = config
        self.device_info = device_info
        self.device_id = device_id

    def _get_device_dict(self) -> Dict[str, Any]:
        """
        Get device information dictionary for HA discovery.

        Returns:
            Device dictionary for discovery payloads
        """
        return {
            "identifiers": [f"gmc_geiger_{self.device_id}"],
            "name": f"GMC Geiger {self.device_info.model}",
            "model": self.device_info.model,
            "manufacturer": "GQ Electronics",
            "sw_version": self.device_info.version,
        }

    def publish_discovery(self) -> None:
        """
        Publish all discovery messages for Home Assistant.

        Creates sensors for:
        - Realtime CPM (counts per minute)
        - Realtime radiation level (µSv/h)
        - Average CPM
        - Average radiation level
        """
        logger.info("Publishing Home Assistant MQTT discovery messages...")

        # Publish CPM sensor (realtime)
        self._publish_cpm_sensor()

        # Publish radiation level sensor (realtime, µSv/h)
        self._publish_radiation_sensor()

        # Publish average CPM sensor
        self._publish_avg_cpm_sensor()

        # Publish average radiation level sensor
        self._publish_avg_radiation_sensor()

        logger.info("Home Assistant discovery complete")

    def _publish_cpm_sensor(self) -> None:
        """Publish discovery for realtime CPM sensor."""
        discovery_topic = (
            f"{self.config.homeassistant_prefix}/sensor/{self.device_id}/cpm/config"
        )

        state_topic = self.config.get_topic(self.device_id, "state")
        availability_topic = self.config.get_topic(self.device_id, "availability")

        payload = {
            "name": "CPM",
            "unique_id": f"{self.device_id}_cpm",
            "state_topic": state_topic,
            "value_template": "{{ value_json.cpm }}",
            "unit_of_measurement": "CPM",
            "icon": "mdi:radioactive",
            "state_class": "measurement",
            "device": self._get_device_dict(),
            "availability_topic": availability_topic,
        }

        self._publish_discovery_message(discovery_topic, payload)

    def _publish_radiation_sensor(self) -> None:
        """Publish discovery for realtime radiation level sensor (µSv/h)."""
        discovery_topic = (
            f"{self.config.homeassistant_prefix}/sensor/"
            f"{self.device_id}/radiation/config"
        )

        state_topic = self.config.get_topic(self.device_id, "state")
        availability_topic = self.config.get_topic(self.device_id, "availability")

        payload = {
            "name": "Radiation Level",
            "unique_id": f"{self.device_id}_radiation",
            "state_topic": state_topic,
            "value_template": "{{ value_json.usv_h }}",
            "unit_of_measurement": "µSv/h",
            "icon": "mdi:radioactive",
            "state_class": "measurement",
            "device_class": "irradiance",
            "device": self._get_device_dict(),
            "availability_topic": availability_topic,
        }

        self._publish_discovery_message(discovery_topic, payload)

    def _publish_avg_cpm_sensor(self) -> None:
        """Publish discovery for average CPM sensor."""
        discovery_topic = (
            f"{self.config.homeassistant_prefix}/sensor/{self.device_id}/cpm_avg/config"
        )

        state_topic = self.config.get_topic(self.device_id, "state_avg")
        availability_topic = self.config.get_topic(self.device_id, "availability")

        payload = {
            "name": "CPM (10-min avg)",
            "unique_id": f"{self.device_id}_cpm_avg",
            "state_topic": state_topic,
            "value_template": "{{ value_json.cpm_avg }}",
            "unit_of_measurement": "CPM",
            "icon": "mdi:radioactive",
            "state_class": "measurement",
            "device": self._get_device_dict(),
            "availability_topic": availability_topic,
        }

        self._publish_discovery_message(discovery_topic, payload)

    def _publish_avg_radiation_sensor(self) -> None:
        """Publish discovery for average radiation level sensor."""
        discovery_topic = (
            f"{self.config.homeassistant_prefix}/sensor/"
            f"{self.device_id}/radiation_avg/config"
        )

        state_topic = self.config.get_topic(self.device_id, "state_avg")
        availability_topic = self.config.get_topic(self.device_id, "availability")

        payload = {
            "name": "Radiation Level (10-min avg)",
            "unique_id": f"{self.device_id}_radiation_avg",
            "state_topic": state_topic,
            "value_template": "{{ value_json.usv_h_avg }}",
            "unit_of_measurement": "µSv/h",
            "icon": "mdi:radioactive",
            "state_class": "measurement",
            "device_class": "irradiance",
            "device": self._get_device_dict(),
            "availability_topic": availability_topic,
        }

        self._publish_discovery_message(discovery_topic, payload)

    def _publish_discovery_message(self, topic: str, payload: Dict[str, Any]) -> None:
        """
        Publish a single discovery message.

        Args:
            topic: Discovery topic
            payload: Discovery payload
        """
        try:
            self.client.publish(
                topic=topic,
                payload=json.dumps(payload),
                qos=1,
                retain=True,
            )
            logger.debug(f"Published discovery to {topic}")
        except Exception as e:
            logger.error(f"Failed to publish discovery to {topic}: {e}")

    def remove_discovery(self) -> None:
        """
        Remove discovery messages (publish empty payloads).

        This removes the sensors from Home Assistant.
        """
        logger.info("Removing Home Assistant discovery messages...")

        sensors = ["cpm", "radiation", "cpm_avg", "radiation_avg"]
        for sensor in sensors:
            discovery_topic = (
                f"{self.config.homeassistant_prefix}/sensor/"
                f"{self.device_id}/{sensor}/config"
            )
            try:
                self.client.publish(
                    topic=discovery_topic,
                    payload="",
                    qos=1,
                    retain=True,
                )
                logger.debug(f"Removed discovery for {sensor}")
            except Exception as e:
                logger.error(f"Failed to remove discovery for {sensor}: {e}")
