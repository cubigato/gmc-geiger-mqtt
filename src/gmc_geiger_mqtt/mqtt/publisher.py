"""MQTT publisher for GMC Geiger counter readings."""

import json
import logging

from ..models import AggregatedReading, DeviceInfo, MQTTConfig, Reading
from .client import MQTTClient

logger = logging.getLogger(__name__)


class MQTTPublisher:
    """
    Publisher for GMC Geiger counter readings via MQTT.

    Handles publishing of:
    - Realtime CPM readings
    - Aggregated readings (averages over time windows)
    - Device information
    - Availability status
    """

    def __init__(
        self,
        mqtt_client: MQTTClient,
        config: MQTTConfig,
        device_info: DeviceInfo,
        conversion_factor: float = 0.0065,
    ):
        """
        Initialize MQTT publisher.

        Args:
            mqtt_client: Connected MQTT client
            config: MQTT configuration
            device_info: Information about the GMC device
            conversion_factor: CPM to µSv/h conversion factor
        """
        self.client = mqtt_client
        self.config = config
        self.device_info = device_info
        self.conversion_factor = conversion_factor

        # Determine device ID from serial or use fallback
        self.device_id = self._get_device_id()

        logger.info(f"MQTT Publisher initialized for device: {self.device_id}")

    def _get_device_id(self) -> str:
        """
        Get device identifier for MQTT topics.

        Uses serial number if available, otherwise falls back to model name.

        Returns:
            Device identifier suitable for MQTT topics
        """
        if self.device_info.serial:
            return self.device_info.serial.lower()

        # Fallback: use model name (sanitized)
        model = self.device_info.model.lower().replace(" ", "_").replace("-", "_")
        return model

    def publish_availability(self, online: bool = True) -> None:
        """
        Publish availability status.

        Args:
            online: True for online, False for offline
        """
        topic = self.config.get_topic(self.device_id, "availability")
        payload = "online" if online else "offline"

        try:
            self.client.publish(
                topic=topic,
                payload=payload,
                qos=1,
                retain=self.config.retain_availability,
            )
            logger.debug(f"Published availability: {payload}")
        except Exception as e:
            logger.error(f"Failed to publish availability: {e}")

    def publish_device_info(self) -> None:
        """Publish device information (retained message)."""
        topic = self.config.get_topic(self.device_id, "info")

        payload = {
            "model": self.device_info.model,
            "firmware": self.device_info.version,
            "serial": self.device_info.serial,
            "manufacturer": "GQ Electronics",
        }

        try:
            self.client.publish(
                topic=topic,
                payload=json.dumps(payload),
                qos=self.config.qos_info,
                retain=self.config.retain_info,
            )
            logger.info(f"Published device info to {topic}")
        except Exception as e:
            logger.error(f"Failed to publish device info: {e}")

    def publish_realtime(self, reading: Reading) -> None:
        """
        Publish realtime CPM reading.

        Args:
            reading: Current reading from device
        """
        topic = self.config.get_topic(self.device_id, "state")

        payload = {
            "cpm": reading.cpm,
            "usv_h": round(reading.to_usv_per_hour(self.conversion_factor), 4),
            "timestamp": reading.timestamp.isoformat(),
            "unit": "CPM",
        }

        try:
            self.client.publish(
                topic=topic,
                payload=json.dumps(payload),
                qos=self.config.qos_realtime,
                retain=False,
            )
            logger.debug(f"Published realtime: CPM={reading.cpm}")
        except Exception as e:
            logger.error(f"Failed to publish realtime reading: {e}")

    def publish_aggregated(self, aggregated: AggregatedReading) -> None:
        """
        Publish aggregated reading (average over time window).

        Args:
            aggregated: Aggregated reading data
        """
        topic = self.config.get_topic(self.device_id, "state_avg")

        payload = aggregated.to_dict(self.conversion_factor)

        try:
            self.client.publish(
                topic=topic,
                payload=json.dumps(payload),
                qos=self.config.qos_aggregate,
                retain=False,
            )
            logger.info(
                f"Published aggregated: "
                f"CPM avg={aggregated.cpm_avg:.1f}, "
                f"min={aggregated.cpm_min}, "
                f"max={aggregated.cpm_max}, "
                f"samples={aggregated.sample_count}"
            )
        except Exception as e:
            logger.error(f"Failed to publish aggregated reading: {e}")

    def startup(self) -> None:
        """
        Perform startup sequence.

        Publishes:
        - Availability (online)
        - Device information
        """
        logger.info("Starting MQTT publisher...")
        self.publish_availability(online=True)
        self.publish_device_info()

    def shutdown(self) -> None:
        """
        Perform shutdown sequence.

        Publishes:
        - Availability (offline)
        """
        logger.info("Shutting down MQTT publisher...")
        self.publish_availability(online=False)
