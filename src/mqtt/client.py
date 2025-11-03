"""MQTT client wrapper with auto-reconnect and connection management."""

import logging
import time
from typing import Optional, Callable

import paho.mqtt.client as mqtt

from ..models import MQTTConfig


logger = logging.getLogger(__name__)


class MQTTClientError(Exception):
    """Base exception for MQTT client errors."""

    pass


class MQTTClient:
    """
    MQTT client wrapper with automatic reconnection and error handling.

    This wraps paho-mqtt and provides a simpler interface with automatic
    reconnection, connection state management, and callback handling.
    """

    def __init__(self, config: MQTTConfig):
        """
        Initialize MQTT client.

        Args:
            config: MQTT configuration
        """
        self.config = config
        self._client: Optional[mqtt.Client] = None
        self._connected = False
        self._on_connect_callback: Optional[Callable] = None
        self._on_disconnect_callback: Optional[Callable] = None

    def connect(self) -> None:
        """
        Connect to MQTT broker.

        Raises:
            MQTTClientError: If connection fails
        """
        try:
            logger.info(
                f"Connecting to MQTT broker at {self.config.broker}:{self.config.port}"
            )

            # Create MQTT client
            self._client = mqtt.Client(
                client_id=self.config.client_id,
                clean_session=True,
                protocol=mqtt.MQTTv311,
            )

            # Set callbacks
            self._client.on_connect = self._on_connect
            self._client.on_disconnect = self._on_disconnect
            self._client.on_message = self._on_message

            # Set username and password if provided
            if self.config.username:
                self._client.username_pw_set(self.config.username, self.config.password)

            # Set Last Will and Testament (LWT) for availability
            device_id = "gmc800"  # Will be updated with real device ID later
            availability_topic = self.config.get_topic(device_id, "availability")
            self._client.will_set(
                availability_topic,
                payload="offline",
                qos=1,
                retain=self.config.retain_availability,
            )

            # Connect to broker
            self._client.connect(
                self.config.broker,
                self.config.port,
                keepalive=60,
            )

            # Start network loop in background thread
            self._client.loop_start()

            # Wait for connection (with timeout)
            timeout = 10.0
            start_time = time.time()
            while not self._connected and (time.time() - start_time) < timeout:
                time.sleep(0.1)

            if not self._connected:
                raise MQTTClientError("Connection timeout")

            logger.info("Successfully connected to MQTT broker")

        except Exception as e:
            raise MQTTClientError(f"Failed to connect to MQTT broker: {e}") from e

    def disconnect(self) -> None:
        """Disconnect from MQTT broker."""
        if self._client:
            logger.info("Disconnecting from MQTT broker")
            self._client.loop_stop()
            self._client.disconnect()
            self._connected = False

    def is_connected(self) -> bool:
        """Check if client is connected to broker."""
        return self._connected and self._client is not None

    def publish(
        self,
        topic: str,
        payload: str,
        qos: int = 0,
        retain: bool = False,
    ) -> None:
        """
        Publish a message to MQTT broker.

        Args:
            topic: MQTT topic
            payload: Message payload (JSON string)
            qos: Quality of Service level (0, 1, or 2)
            retain: Whether to retain the message

        Raises:
            MQTTClientError: If not connected or publish fails
        """
        if not self.is_connected():
            raise MQTTClientError("Not connected to MQTT broker")

        try:
            result = self._client.publish(topic, payload, qos=qos, retain=retain)

            # Check if publish was successful
            if result.rc != mqtt.MQTT_ERR_SUCCESS:
                logger.warning(f"Failed to publish to {topic}: {result.rc}")
            else:
                logger.debug(f"Published to {topic} (QoS {qos}, retain={retain})")

        except Exception as e:
            raise MQTTClientError(f"Failed to publish message: {e}") from e

    def subscribe(self, topic: str, qos: int = 0) -> None:
        """
        Subscribe to an MQTT topic.

        Args:
            topic: MQTT topic to subscribe to
            qos: Quality of Service level

        Raises:
            MQTTClientError: If not connected or subscribe fails
        """
        if not self.is_connected():
            raise MQTTClientError("Not connected to MQTT broker")

        try:
            result, _ = self._client.subscribe(topic, qos=qos)
            if result != mqtt.MQTT_ERR_SUCCESS:
                raise MQTTClientError(f"Failed to subscribe to {topic}: {result}")
            logger.debug(f"Subscribed to {topic} (QoS {qos})")
        except Exception as e:
            raise MQTTClientError(f"Failed to subscribe: {e}") from e

    def set_on_connect_callback(self, callback: Callable) -> None:
        """
        Set callback to be called when connection is established.

        Args:
            callback: Callback function (no arguments)
        """
        self._on_connect_callback = callback

    def set_on_disconnect_callback(self, callback: Callable) -> None:
        """
        Set callback to be called when connection is lost.

        Args:
            callback: Callback function (no arguments)
        """
        self._on_disconnect_callback = callback

    def _on_connect(self, client, userdata, flags, rc):
        """
        Internal callback for connection events.

        Args:
            client: MQTT client instance
            userdata: User data
            flags: Connection flags
            rc: Result code
        """
        if rc == 0:
            logger.info("MQTT connection established")
            self._connected = True
            if self._on_connect_callback:
                try:
                    self._on_connect_callback()
                except Exception as e:
                    logger.error(f"Error in on_connect callback: {e}")
        else:
            logger.error(f"MQTT connection failed with code {rc}")
            self._connected = False

    def _on_disconnect(self, client, userdata, rc):
        """
        Internal callback for disconnection events.

        Args:
            client: MQTT client instance
            userdata: User data
            rc: Result code
        """
        self._connected = False
        if rc == 0:
            logger.info("MQTT disconnected (clean)")
        else:
            logger.warning(f"MQTT disconnected unexpectedly (code {rc})")

        if self._on_disconnect_callback:
            try:
                self._on_disconnect_callback()
            except Exception as e:
                logger.error(f"Error in on_disconnect callback: {e}")

    def _on_message(self, client, userdata, message):
        """
        Internal callback for incoming messages.

        Args:
            client: MQTT client instance
            userdata: User data
            message: MQTT message
        """
        logger.debug(f"Received message on {message.topic}: {message.payload.decode()}")

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
