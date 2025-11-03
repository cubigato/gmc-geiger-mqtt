"""Unit tests for domain models."""

from datetime import datetime

import pytest

from gmc_geiger_mqtt.models import (
    AggregatedReading,
    DeviceConfig,
    DeviceInfo,
    MQTTConfig,
    Reading,
)


class TestReading:
    """Tests for Reading model."""

    def test_create_valid_reading(self):
        """Test creating a valid reading."""
        timestamp = datetime.now()
        reading = Reading(cpm=42, timestamp=timestamp)
        assert reading.cpm == 42
        assert reading.timestamp == timestamp

    def test_negative_cpm_raises_error(self):
        """Test that negative CPM raises ValueError."""
        with pytest.raises(ValueError, match="CPM must be non-negative"):
            Reading(cpm=-1, timestamp=datetime.now())

    def test_to_usv_per_hour_default(self):
        """Test conversion to µSv/h with default factor."""
        reading = Reading(cpm=100, timestamp=datetime.now())
        usv_h = reading.to_usv_per_hour()
        assert usv_h == pytest.approx(0.65, rel=1e-6)

    def test_to_usv_per_hour_custom_factor(self):
        """Test conversion with custom factor."""
        reading = Reading(cpm=100, timestamp=datetime.now())
        usv_h = reading.to_usv_per_hour(conversion_factor=0.01)
        assert usv_h == pytest.approx(1.0, rel=1e-6)

    def test_string_representation(self):
        """Test string representation."""
        reading = Reading(cpm=28, timestamp=datetime.now())
        str_repr = str(reading)
        assert "cpm=28" in str_repr
        assert "µSv/h=" in str_repr


class TestDeviceInfo:
    """Tests for DeviceInfo model."""

    def test_create_device_info_with_serial(self):
        """Test creating device info with serial number."""
        info = DeviceInfo(model="GMC-800Re", version="1.10", serial="ABC123")
        assert info.model == "GMC-800Re"
        assert info.version == "1.10"
        assert info.serial == "ABC123"

    def test_create_device_info_without_serial(self):
        """Test creating device info without serial number."""
        info = DeviceInfo(model="GMC-800Re", version="1.10")
        assert info.model == "GMC-800Re"
        assert info.version == "1.10"
        assert info.serial is None

    def test_string_representation_with_serial(self):
        """Test string representation with serial."""
        info = DeviceInfo(model="GMC-800Re", version="1.10", serial="ABC123")
        str_repr = str(info)
        assert "GMC-800Re" in str_repr
        assert "1.10" in str_repr
        assert "ABC123" in str_repr

    def test_string_representation_without_serial(self):
        """Test string representation without serial."""
        info = DeviceInfo(model="GMC-800Re", version="1.10")
        str_repr = str(info)
        assert "GMC-800Re" in str_repr
        assert "1.10" in str_repr


class TestDeviceConfig:
    """Tests for DeviceConfig model."""

    def test_create_valid_config(self):
        """Test creating valid device config."""
        config = DeviceConfig(port="/dev/ttyUSB0", baudrate=115200, timeout=5.0)
        assert config.port == "/dev/ttyUSB0"
        assert config.baudrate == 115200
        assert config.timeout == 5.0

    def test_default_values(self):
        """Test default baudrate and timeout."""
        config = DeviceConfig(port="/dev/ttyUSB0")
        assert config.baudrate == 115200
        assert config.timeout == 5.0

    def test_invalid_baudrate_raises_error(self):
        """Test that invalid baudrate raises ValueError."""
        with pytest.raises(ValueError, match="Baudrate must be positive"):
            DeviceConfig(port="/dev/ttyUSB0", baudrate=0)

        with pytest.raises(ValueError, match="Baudrate must be positive"):
            DeviceConfig(port="/dev/ttyUSB0", baudrate=-9600)

    def test_invalid_timeout_raises_error(self):
        """Test that invalid timeout raises ValueError."""
        with pytest.raises(ValueError, match="Timeout must be positive"):
            DeviceConfig(port="/dev/ttyUSB0", timeout=0)

        with pytest.raises(ValueError, match="Timeout must be positive"):
            DeviceConfig(port="/dev/ttyUSB0", timeout=-1.0)


class TestMQTTConfig:
    """Tests for MQTTConfig model."""

    def test_create_with_defaults(self):
        """Test creating MQTT config with defaults."""
        config = MQTTConfig()
        assert config.enabled is True
        assert config.broker == "localhost"
        assert config.port == 1883
        assert config.client_id == "gmc-geiger-mqtt"
        assert config.topic_prefix == "gmc/geiger"
        assert config.qos_realtime == 0
        assert config.qos_aggregate == 1

    def test_create_with_custom_values(self):
        """Test creating MQTT config with custom values."""
        config = MQTTConfig(
            broker="mqtt.example.com",
            port=8883,
            username="user",
            password="pass",
            topic_prefix="radiation/sensors",
        )
        assert config.broker == "mqtt.example.com"
        assert config.port == 8883
        assert config.username == "user"
        assert config.password == "pass"
        assert config.topic_prefix == "radiation/sensors"

    def test_invalid_port_raises_error(self):
        """Test that invalid port raises ValueError."""
        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            MQTTConfig(port=0)

        with pytest.raises(ValueError, match="Port must be between 1 and 65535"):
            MQTTConfig(port=70000)

    def test_invalid_qos_raises_error(self):
        """Test that invalid QoS raises ValueError."""
        with pytest.raises(ValueError, match="QoS must be 0, 1, or 2"):
            MQTTConfig(qos_realtime=3)

        with pytest.raises(ValueError, match="QoS must be 0, 1, or 2"):
            MQTTConfig(qos_aggregate=-1)

    def test_get_topic(self):
        """Test topic construction."""
        config = MQTTConfig(topic_prefix="gmc/geiger")
        topic = config.get_topic("device123", "state")
        assert topic == "gmc/geiger/device123/state"

    def test_get_topic_custom_prefix(self):
        """Test topic construction with custom prefix."""
        config = MQTTConfig(topic_prefix="radiation/sensors")
        topic = config.get_topic("gmc800", "state_avg")
        assert topic == "radiation/sensors/gmc800/state_avg"


class TestAggregatedReading:
    """Tests for AggregatedReading model."""

    def test_create_aggregated_reading(self):
        """Test creating aggregated reading."""
        timestamp = datetime.now()
        aggregated = AggregatedReading(
            cpm_avg=25.5,
            cpm_min=18,
            cpm_max=35,
            usv_h_avg=0.1658,
            window_seconds=600,
            sample_count=100,
            timestamp=timestamp,
        )
        assert aggregated.cpm_avg == 25.5
        assert aggregated.cpm_min == 18
        assert aggregated.cpm_max == 35
        assert aggregated.usv_h_avg == 0.1658
        assert aggregated.window_seconds == 600
        assert aggregated.sample_count == 100
        assert aggregated.timestamp == timestamp

    def test_to_dict(self):
        """Test conversion to dictionary."""
        timestamp = datetime.now()
        aggregated = AggregatedReading(
            cpm_avg=25.5,
            cpm_min=18,
            cpm_max=35,
            usv_h_avg=0.1658,
            window_seconds=600,
            sample_count=100,
            timestamp=timestamp,
        )
        data = aggregated.to_dict()

        assert data["cpm_avg"] == 25.5
        assert data["cpm_min"] == 18
        assert data["cpm_max"] == 35
        assert data["usv_h_avg"] == 0.1658
        assert data["window_minutes"] == 10
        assert data["sample_count"] == 100
        assert data["timestamp"] == timestamp.isoformat()
        assert data["unit"] == "CPM"

    def test_string_representation(self):
        """Test string representation."""
        aggregated = AggregatedReading(
            cpm_avg=25.5,
            cpm_min=18,
            cpm_max=35,
            usv_h_avg=0.1658,
            window_seconds=600,
            sample_count=100,
            timestamp=datetime.now(),
        )
        str_repr = str(aggregated)
        assert "cpm_avg=25.5" in str_repr
        assert "cpm_min=18" in str_repr
        assert "cpm_max=35" in str_repr
        assert "samples=100" in str_repr
