"""Domain models for GMC Geiger counter readings and device information."""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional, List


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


@dataclass
class MQTTConfig:
    """Configuration for MQTT connection and publishing."""

    enabled: bool = True
    broker: str = "localhost"
    port: int = 1883
    username: Optional[str] = None
    password: Optional[str] = None
    client_id: str = "gmc-geiger-mqtt"
    topic_prefix: str = "gmc/geiger"
    qos_realtime: int = 0
    qos_aggregate: int = 1
    qos_info: int = 1
    retain_info: bool = True
    retain_availability: bool = True
    homeassistant_discovery: bool = False
    homeassistant_prefix: str = "homeassistant"

    def __post_init__(self):
        """Validate the configuration."""
        if self.port <= 0 or self.port > 65535:
            raise ValueError(f"Port must be between 1 and 65535, got {self.port}")
        if self.qos_realtime not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {self.qos_realtime}")
        if self.qos_aggregate not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {self.qos_aggregate}")
        if self.qos_info not in (0, 1, 2):
            raise ValueError(f"QoS must be 0, 1, or 2, got {self.qos_info}")

    def get_topic(self, device_id: str, subtopic: str) -> str:
        """
        Construct a full MQTT topic path.

        Args:
            device_id: Device identifier (serial number or fallback)
            subtopic: Subtopic (e.g., 'state', 'state_avg', 'availability')

        Returns:
            Full topic path
        """
        return f"{self.topic_prefix}/{device_id}/{subtopic}"


@dataclass
class AggregatedReading:
    """Represents aggregated radiation readings over a time window."""

    cpm_avg: float
    cpm_min: int
    cpm_max: int
    usv_h_avg: float
    window_seconds: int
    sample_count: int
    timestamp: datetime
    samples: List[Reading] = field(default_factory=list, repr=False)

    def to_dict(self, conversion_factor: float = 0.0065) -> dict:
        """
        Convert aggregated reading to dictionary for JSON serialization.

        Args:
            conversion_factor: CPM to µSv/h conversion factor

        Returns:
            Dictionary representation
        """
        return {
            "cpm_avg": round(self.cpm_avg, 2),
            "cpm_min": self.cpm_min,
            "cpm_max": self.cpm_max,
            "usv_h_avg": round(self.usv_h_avg, 4),
            "window_minutes": self.window_seconds // 60,
            "sample_count": self.sample_count,
            "timestamp": self.timestamp.isoformat(),
            "unit": "CPM",
        }

    def __str__(self) -> str:
        """Human-readable string representation."""
        return (
            f"AggregatedReading("
            f"cpm_avg={self.cpm_avg:.1f}, "
            f"cpm_min={self.cpm_min}, "
            f"cpm_max={self.cpm_max}, "
            f"µSv/h={self.usv_h_avg:.4f}, "
            f"samples={self.sample_count})"
        )
