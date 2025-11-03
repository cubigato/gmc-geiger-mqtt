"""GMC Device Handler for serial communication with GMC Geiger counters.

This module implements the communication protocol as specified in GQ-RFC1801.txt
for reading data from GMC Geiger counter devices.
"""

import logging
import time
from typing import Optional

import serial

from .models import DeviceConfig, DeviceInfo, Reading
from datetime import datetime


logger = logging.getLogger(__name__)


class GMCDeviceError(Exception):
    """Base exception for GMC device errors."""

    pass


class GMCConnectionError(GMCDeviceError):
    """Raised when connection to the device fails."""

    pass


class GMCCommandError(GMCDeviceError):
    """Raised when a command fails to execute properly."""

    pass


class GMCDevice:
    """Handler for GMC Geiger counter device communication."""

    # Command constants from GQ-RFC1801.txt
    CMD_GET_VER = b"<GETVER>>"
    CMD_GET_CPM = b"<GETCPM>>"
    CMD_GET_SERIAL = b"<GETSERIAL>>"

    def __init__(self, config: DeviceConfig):
        """
        Initialize the GMC device handler.

        Args:
            config: Device configuration including port, baudrate, and timeout
        """
        self.config = config
        self.serial: Optional[serial.Serial] = None
        self._device_info: Optional[DeviceInfo] = None

    def connect(self) -> None:
        """
        Establish connection to the GMC device.

        Raises:
            GMCConnectionError: If connection fails
        """
        try:
            logger.info(
                f"Connecting to GMC device on {self.config.port} at {self.config.baudrate} baud"
            )
            self.serial = serial.Serial(
                port=self.config.port,
                baudrate=self.config.baudrate,
                timeout=self.config.timeout,
                write_timeout=self.config.timeout,
                bytesize=serial.EIGHTBITS,
                parity=serial.PARITY_NONE,
                stopbits=serial.STOPBITS_ONE,
                rtscts=False,
                dsrdtr=False,
                xonxoff=False,
            )

            # DTR/RTS aktivieren (some CH340 chips need this)
            self.serial.setDTR(True)
            self.serial.setRTS(True)

            # Give the device a moment to initialize
            time.sleep(0.5)

            # Clear any pending data in the buffer
            self.serial.reset_input_buffer()
            self.serial.reset_output_buffer()

            logger.info("Successfully connected to GMC device")

            # Fetch device info
            self._device_info = self._get_device_info()
            logger.info(f"Device info: {self._device_info}")

        except serial.SerialException as e:
            raise GMCConnectionError(f"Failed to connect to device: {e}") from e

    def disconnect(self) -> None:
        """Close the connection to the GMC device."""
        if self.serial and self.serial.is_open:
            logger.info("Disconnecting from GMC device")
            self.serial.close()
            self.serial = None

    def is_connected(self) -> bool:
        """Check if the device is connected."""
        return self.serial is not None and self.serial.is_open

    def _ensure_connected(self) -> None:
        """Ensure the device is connected, raise error if not."""
        if not self.is_connected():
            raise GMCConnectionError("Device is not connected")

    def _send_command(self, command: bytes) -> None:
        """
        Send a command to the device.

        Args:
            command: Command bytes to send

        Raises:
            GMCCommandError: If sending fails
        """
        self._ensure_connected()
        try:
            # Clear input buffer before sending command to prevent stale data
            self.serial.reset_input_buffer()
            logger.debug(f"Sending command: {command}")
            self.serial.write(command)
            self.serial.flush()
        except serial.SerialException as e:
            raise GMCCommandError(f"Failed to send command: {e}") from e

    def _read_response(self, num_bytes: int) -> bytes:
        """
        Read a fixed number of bytes from the device.

        Args:
            num_bytes: Number of bytes to read

        Returns:
            Bytes read from device

        Raises:
            GMCCommandError: If reading fails or timeout occurs
        """
        self._ensure_connected()
        try:
            data = self.serial.read(num_bytes)
            if len(data) != num_bytes:
                raise GMCCommandError(
                    f"Expected {num_bytes} bytes, got {len(data)} bytes"
                )
            logger.debug(f"Received {len(data)} bytes: {data}")
            return data
        except serial.SerialException as e:
            raise GMCCommandError(f"Failed to read response: {e}") from e

    def _read_until(self, terminator: bytes = b"\x00", max_bytes: int = 256) -> bytes:
        """
        Read bytes until a terminator is found or max_bytes is reached.

        Args:
            terminator: Byte sequence that marks end of data
            max_bytes: Maximum number of bytes to read

        Returns:
            Bytes read (excluding terminator)

        Raises:
            GMCCommandError: If reading fails
        """
        self._ensure_connected()
        try:
            data = bytearray()
            while len(data) < max_bytes:
                byte = self.serial.read(1)
                if not byte:
                    break
                if byte == terminator:
                    break
                data.extend(byte)
            logger.debug(f"Read until terminator: {bytes(data)}")
            return bytes(data)
        except serial.SerialException as e:
            raise GMCCommandError(f"Failed to read response: {e}") from e

    def _get_device_info(self) -> DeviceInfo:
        """
        Retrieve device information (version and model).

        Returns:
            DeviceInfo object with device details

        Raises:
            GMCCommandError: If command fails
        """
        # Get version string
        self._send_command(self.CMD_GET_VER)
        time.sleep(0.2)  # Wait for device to prepare response

        # Read version - GMC devices return variable length (typically 13-14 bytes)
        # Use read_until to get data until timeout
        version_data = self._read_until(terminator=b"\x00", max_bytes=20)

        # If no null terminator was found, the data is complete as-is
        version_str = version_data.decode("ascii", errors="ignore").strip()

        if not version_str:
            raise GMCCommandError("Failed to read version string")

        logger.debug(f"Version string: {version_str}")

        # Parse version string (format is typically "GMC-800Re1.10")
        # Try to find version pattern (digits with dot)
        import re

        match = re.search(r"^(.*?)(\d+\.\d+)$", version_str)
        if match:
            model = match.group(1)
            version = match.group(2)
        else:
            # Fallback: try to split by space
            parts = version_str.rsplit(" ", 1)
            if len(parts) == 2:
                model = parts[0]
                version = parts[1]
            else:
                model = version_str
                version = "unknown"

        # Try to get serial number (not all devices support this)
        serial_num = None
        try:
            self._send_command(self.CMD_GET_SERIAL)
            time.sleep(0.05)
            serial_data = self._read_response(7)
            # Serial is 7 bytes, convert to hex string
            serial_num = serial_data.hex().upper()
        except GMCCommandError as e:
            logger.debug(f"Device does not support serial number query: {e}")

        return DeviceInfo(model=model, version=version, serial=serial_num)

    def get_cpm(self) -> Reading:
        """
        Get the current CPM (counts per minute) reading from the device.

        Returns:
            Reading object with CPM value and timestamp

        Raises:
            GMCCommandError: If reading fails
        """
        self._ensure_connected()

        self._send_command(self.CMD_GET_CPM)
        time.sleep(0.1)  # Small delay for device to prepare response

        # CPM is returned as 4 bytes (32-bit unsigned integer, big-endian)
        # First byte is MSB, fourth byte is LSB
        data = self._read_response(4)
        cpm = (data[0] << 24) | (data[1] << 16) | (data[2] << 8) | data[3]

        timestamp = datetime.now()

        logger.debug(f"Read CPM: {cpm}")

        return Reading(cpm=cpm, timestamp=timestamp)

    @property
    def device_info(self) -> Optional[DeviceInfo]:
        """Get cached device information."""
        return self._device_info

    def __enter__(self):
        """Context manager entry."""
        self.connect()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.disconnect()
        return False
