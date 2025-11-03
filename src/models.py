"""Domain models for GMC Geiger counter readings and device information."""

from dataclasses import dataclass
from datetime import datetime
from typing import Optional


@dataclass
class Reading:
    """Represents a single radiation reading from the GMC device."""

    cpm: int  # Counts per minute
    timestamp: datetime

    def __post_init__(self):
        """Validate the reading data."""
        if self.cpm < 0:
            raise ValueError(f"CPM must be non-negative, got {self.cpm}")

    def to_usv_per_hour(self, conversion_factor: float = 0.0065) -> float:
        """
        Convert CPM to µSv/h using the specified conversion factor.

        Default factor of 0.0065 is commonly used for many GMC devices,
        but this may vary depending on the specific model and tube type.

        Args:
            conversion_factor: Multiplication factor to convert CPM to µSv/h

        Returns:
            Radiation level in microsieverts per hour
        """
        return self.cpm * conversion_factor

    def __str__(self) -> str:
        """Human-readable string representation."""
        return f"Reading(cpm={self.cpm}, µSv/h={self.to_usv_per_hour():.4f}, time={self.timestamp.isoformat()})"


@dataclass
class DeviceInfo:
    """Information about the connected GMC device."""

    model: str
    version: str
    serial: Optional[str] = None

    def __str__(self) -> str:
        """Human-readable string representation."""
        serial_str = f", serial={self.serial}" if self.serial else ""
        return f"GMC Device: {self.model} (v{self.version}{serial_str})"


@dataclass
class DeviceConfig:
    """Configuration for the GMC device connection."""

    port: str
    baudrate: int = 115200
    timeout: float = 5.0

    def __post_init__(self):
        """Validate the configuration."""
        if self.baudrate <= 0:
            raise ValueError(f"Baudrate must be positive, got {self.baudrate}")
        if self.timeout <= 0:
            raise ValueError(f"Timeout must be positive, got {self.timeout}")
