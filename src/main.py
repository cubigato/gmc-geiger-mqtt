"""Main entry point for GMC Geiger MQTT bridge.

This is a minimal implementation for testing serial communication with the device.
"""

import logging
import sys
import time
from pathlib import Path

from .config import Config, ConfigError
from .gmc_device import GMCDevice, GMCDeviceError


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
    logger.info(f"Starting GMC Geiger test mode")
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


def main() -> int:
    """Main application entry point."""
    try:
        # Load configuration
        config_path = sys.argv[1] if len(sys.argv) > 1 else None
        config = Config(config_path)

        # Setup logging
        setup_logging(config)

        # Run in test mode
        return test_device_reading(config)

    except ConfigError as e:
        print(f"Configuration error: {e}", file=sys.stderr)
        return 1

    except Exception as e:
        print(f"Fatal error: {e}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
