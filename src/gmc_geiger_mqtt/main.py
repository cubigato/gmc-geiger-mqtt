"""Main entry point for GMC Geiger MQTT bridge.

Supports two modes:
- Test mode: Read from device and log to console
- Service mode: Read from device, aggregate, and publish via MQTT
"""

import logging
import signal
import sys
import time
from typing import Optional

from .config import Config, ConfigError
from .gmc_device import GMCDevice, GMCDeviceError
from .mqtt import HomeAssistantDiscovery, MQTTClient, MQTTPublisher
from .processing import MovingAverageAggregator

# Global flag for graceful shutdown
shutdown_requested = False


def signal_handler(signum, frame):
    """Handle shutdown signals gracefully."""
    global shutdown_requested
    logger = logging.getLogger(__name__)
    logger.info(f"Received signal {signum}, initiating shutdown...")
    shutdown_requested = True


def setup_logging(config: Config) -> None:
    """Configure logging based on config settings."""
    logging_config = config.get_logging_config()

    level_name = logging_config.get("level", "INFO")
    level = getattr(logging, level_name.upper(), logging.INFO)

    log_format = logging_config.get(
        "format", "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
    )

    logging.basicConfig(level=level, format=log_format)


def test_device_reading(config: Config) -> int:
    """
    Test mode: Read from the device and log readings to console.

    Args:
        config: Application configuration

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    logger = logging.getLogger(__name__)

    device_config = config.get_device_config()
    logger.info("Starting GMC Geiger test mode")
    logger.info(f"Device: {device_config.port} @ {device_config.baudrate} baud")

    try:
        with GMCDevice(device_config) as device:
            logger.info("=" * 70)
            logger.info(f"Connected to device: {device.device_info}")
            logger.info("=" * 70)
            logger.info("")
            logger.info("Starting continuous reading mode (Ctrl+C to stop)...")
            logger.info("=" * 70)

            reading_count = 0

            while True:
                try:
                    # Read CPM value
                    reading = device.get_cpm()
                    reading_count += 1

                    # Log the reading
                    logger.info(
                        f"[{reading_count:4d}] {reading.timestamp.strftime('%H:%M:%S')} | "
                        f"CPM: {reading.cpm:4d} | "
                        f"µSv/h: {reading.to_usv_per_hour():.4f}"
                    )

                    # Wait before next reading
                    time.sleep(2.0)

                except GMCDeviceError as e:
                    logger.error(f"Error reading from device: {e}")
                    time.sleep(5.0)  # Wait longer on error

    except KeyboardInterrupt:
        logger.info("")
        logger.info("=" * 70)
        logger.info(f"Stopped by user. Total readings: {reading_count}")
        logger.info("=" * 70)
        return 0

    except GMCDeviceError as e:
        logger.error(f"Device error: {e}")
        return 1

    except Exception as e:
        logger.exception(f"Unexpected error: {e}")
        return 1


def service_mode(config: Config) -> int:
    """
    Service mode: Read from device, aggregate, and publish via MQTT.

    Args:
        config: Application configuration

    Returns:
        Exit code (0 for success, non-zero for failure)
    """
    global shutdown_requested
    logger = logging.getLogger(__name__)

    device_config = config.get_device_config()
    mqtt_config = config.get_mqtt_config()
    sampling_config = config.get_sampling_config()
    conversion_factor = config.get_conversion_factor()

    logger.info("=" * 70)
    logger.info("Starting GMC Geiger MQTT Bridge - Service Mode")
    logger.info("=" * 70)
    logger.info(f"Device: {device_config.port} @ {device_config.baudrate} baud")
    logger.info(f"MQTT: {mqtt_config.broker}:{mqtt_config.port}")
    logger.info(f"Sampling interval: {sampling_config.get('interval', 1)}s")
    logger.info(f"Aggregation window: {sampling_config.get('aggregation_window', 600)}s")
    logger.info("=" * 70)

    mqtt_client: Optional[MQTTClient] = None
    publisher: Optional[MQTTPublisher] = None
    device: Optional[GMCDevice] = None
    aggregator: Optional[MovingAverageAggregator] = None
    reading_count = 0  # Initialize early to avoid UnboundLocalError in finally block

    try:
        # Connect to device
        logger.info("Connecting to GMC device...")
        device = GMCDevice(device_config)
        device.connect()
        logger.info(f"Connected to device: {device.device_info}")

        # Connect to MQTT broker
        logger.info("Connecting to MQTT broker...")
        mqtt_client = MQTTClient(mqtt_config)
        mqtt_client.connect()

        # Initialize publisher
        publisher = MQTTPublisher(
            mqtt_client=mqtt_client,
            config=mqtt_config,
            device_info=device.device_info,
            conversion_factor=conversion_factor,
        )

        # Perform startup sequence
        publisher.startup()

        # Initialize Home Assistant Discovery if enabled
        if mqtt_config.homeassistant_discovery:
            logger.info("Publishing Home Assistant MQTT discovery...")
            discovery = HomeAssistantDiscovery(
                mqtt_client=mqtt_client,
                config=mqtt_config,
                device_info=device.device_info,
                device_id=publisher.device_id,
            )
            discovery.publish_discovery()

        # Initialize aggregator
        aggregator = MovingAverageAggregator(
            window_seconds=sampling_config.get("aggregation_window", 600),
            conversion_factor=conversion_factor,
        )

        logger.info("=" * 70)
        logger.info("Service started successfully. Press Ctrl+C to stop.")
        logger.info("=" * 70)

        # Main loop (reading_count already initialized above)
        sampling_interval = sampling_config.get("interval", 1)
        aggregation_interval = sampling_config.get("aggregation_interval", 600)

        while not shutdown_requested:
            try:
                # Read from device
                reading = device.get_cpm()
                reading_count += 1

                # Log reading (less verbose in service mode)
                if reading_count % 60 == 0:  # Log every minute
                    logger.info(
                        f"[{reading_count:5d}] CPM: {reading.cpm:4d} | "
                        f"µSv/h: {reading.to_usv_per_hour(conversion_factor):.4f} | "
                        f"Window samples: {aggregator.get_sample_count()}"
                    )

                # Publish realtime reading
                publisher.publish_realtime(reading)

                # Add to aggregator
                aggregator.add_reading(reading)

                # Check if we should publish aggregated data
                if aggregator.should_publish(reading.timestamp, aggregation_interval):
                    aggregated = aggregator.get_aggregated()
                    if aggregated:
                        publisher.publish_aggregated(aggregated)
                        aggregator.mark_published(reading.timestamp)

                # Wait before next reading
                time.sleep(sampling_interval)

            except GMCDeviceError as e:
                logger.error(f"Error reading from device: {e}")
                time.sleep(5.0)  # Wait longer on error

            except Exception as e:
                logger.error(f"Unexpected error in main loop: {e}", exc_info=True)
                time.sleep(5.0)

        logger.info("Shutdown requested, cleaning up...")

    except KeyboardInterrupt:
        logger.info("Interrupted by user (Ctrl+C)")

    except GMCDeviceError as e:
        logger.error(f"Device error: {e}")
        return 1

    except Exception as e:
        logger.exception(f"Fatal error: {e}")
        return 1

    finally:
        # Cleanup
        logger.info("Performing shutdown sequence...")

        if publisher:
            try:
                publisher.shutdown()
            except Exception as e:
                logger.error(f"Error during publisher shutdown: {e}")

        if mqtt_client:
            try:
                mqtt_client.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting MQTT: {e}")

        if device:
            try:
                device.disconnect()
            except Exception as e:
                logger.error(f"Error disconnecting device: {e}")

        logger.info("=" * 70)
        logger.info(f"Shutdown complete. Total readings: {reading_count}")
        logger.info("=" * 70)

    return 0


def main() -> int:
    """Main application entry point."""
    global shutdown_requested

    # Register signal handlers
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    try:
        # Load configuration
        config_path = sys.argv[1] if len(sys.argv) > 1 else None
        config = Config(config_path)

        # Setup logging
        setup_logging(config)

        # Check if MQTT is enabled
        mqtt_config = config.get_mqtt_config()

        if mqtt_config.enabled:
            # Run in service mode with MQTT
            return service_mode(config)
        else:
            # Run in test mode (no MQTT)
            logger = logging.getLogger(__name__)
            logger.info("MQTT disabled, running in test mode")
            return test_device_reading(config)

    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
