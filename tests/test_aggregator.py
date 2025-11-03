"""Unit tests for MovingAverageAggregator."""

from datetime import datetime, timedelta

import pytest

from gmc_geiger_mqtt.models import Reading
from gmc_geiger_mqtt.processing.aggregator import MovingAverageAggregator


class TestMovingAverageAggregator:
    """Tests for MovingAverageAggregator."""

    def test_initialization(self):
        """Test aggregator initialization with default values."""
        aggregator = MovingAverageAggregator()
        assert aggregator.window_seconds == 600
        assert aggregator.conversion_factor == 0.0065
        assert aggregator.get_sample_count() == 0

    def test_initialization_custom_values(self):
        """Test aggregator initialization with custom values."""
        aggregator = MovingAverageAggregator(window_seconds=300, conversion_factor=0.01)
        assert aggregator.window_seconds == 300
        assert aggregator.conversion_factor == 0.01

    def test_add_single_reading(self):
        """Test adding a single reading."""
        aggregator = MovingAverageAggregator(window_seconds=600)
        timestamp = datetime.now()
        reading = Reading(cpm=25, timestamp=timestamp)

        aggregator.add_reading(reading)
        assert aggregator.get_sample_count() == 1

    def test_add_multiple_readings(self):
        """Test adding multiple readings."""
        aggregator = MovingAverageAggregator(window_seconds=600)
        timestamp = datetime.now()

        for i in range(10):
            reading = Reading(cpm=20 + i, timestamp=timestamp + timedelta(seconds=i))
            aggregator.add_reading(reading)

        assert aggregator.get_sample_count() == 10

    def test_old_samples_removed(self):
        """Test that old samples outside window are removed."""
        aggregator = MovingAverageAggregator(window_seconds=60)
        base_time = datetime.now()

        # Add samples spanning 120 seconds
        for i in range(120):
            reading = Reading(cpm=25, timestamp=base_time + timedelta(seconds=i))
            aggregator.add_reading(reading)

        # Should only keep samples from the last 60 seconds
        assert aggregator.get_sample_count() <= 61  # Allow for boundary

    def test_get_aggregated_empty(self):
        """Test get_aggregated with no samples."""
        aggregator = MovingAverageAggregator()
        result = aggregator.get_aggregated()
        assert result is None

    def test_get_aggregated_single_sample(self):
        """Test get_aggregated with single sample."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()
        reading = Reading(cpm=42, timestamp=timestamp)
        aggregator.add_reading(reading)

        result = aggregator.get_aggregated()
        assert result is not None
        assert result.cpm_avg == 42.0
        assert result.cpm_min == 42
        assert result.cpm_max == 42
        assert result.sample_count == 1

    def test_get_aggregated_multiple_samples(self):
        """Test get_aggregated with multiple samples."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()

        # Add samples with CPM values: 20, 22, 24, 26, 28
        cpm_values = [20, 22, 24, 26, 28]
        for i, cpm in enumerate(cpm_values):
            reading = Reading(cpm=cpm, timestamp=timestamp + timedelta(seconds=i))
            aggregator.add_reading(reading)

        result = aggregator.get_aggregated()
        assert result is not None
        assert result.cpm_avg == 24.0  # Average of 20, 22, 24, 26, 28
        assert result.cpm_min == 20
        assert result.cpm_max == 28
        assert result.sample_count == 5
        assert result.window_seconds == 600

    def test_aggregated_usv_calculation(self):
        """Test that µSv/h is calculated correctly in aggregated reading."""
        aggregator = MovingAverageAggregator(conversion_factor=0.01)
        timestamp = datetime.now()

        # Add samples with CPM = 100
        for i in range(5):
            reading = Reading(cpm=100, timestamp=timestamp + timedelta(seconds=i))
            aggregator.add_reading(reading)

        result = aggregator.get_aggregated()
        assert result is not None
        assert result.cpm_avg == 100.0
        assert result.usv_h_avg == pytest.approx(1.0, rel=1e-6)  # 100 * 0.01

    def test_should_publish_first_time(self):
        """Test should_publish returns True on first call."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()
        assert aggregator.should_publish(timestamp, 600) is True

    def test_should_publish_before_interval(self):
        """Test should_publish returns False before interval elapsed."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()

        aggregator.mark_published(timestamp)
        # Check 30 seconds later
        assert aggregator.should_publish(timestamp + timedelta(seconds=30), 600) is False

    def test_should_publish_after_interval(self):
        """Test should_publish returns True after interval elapsed."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()

        aggregator.mark_published(timestamp)
        # Check 600 seconds later
        assert aggregator.should_publish(timestamp + timedelta(seconds=600), 600) is True

    def test_mark_published(self):
        """Test mark_published updates last publication time."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()

        aggregator.mark_published(timestamp)
        # Should not publish immediately after marking
        assert aggregator.should_publish(timestamp, 600) is False
        # Should publish after interval
        assert aggregator.should_publish(timestamp + timedelta(seconds=601), 600) is True

    def test_get_window_age_empty(self):
        """Test get_window_age with no samples."""
        aggregator = MovingAverageAggregator()
        assert aggregator.get_window_age() is None

    def test_get_window_age_single_sample(self):
        """Test get_window_age with single sample."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()
        reading = Reading(cpm=25, timestamp=timestamp)
        aggregator.add_reading(reading)

        age = aggregator.get_window_age()
        assert age is not None
        assert age.total_seconds() == 0

    def test_get_window_age_multiple_samples(self):
        """Test get_window_age with multiple samples."""
        aggregator = MovingAverageAggregator()
        base_time = datetime.now()

        # Add samples spanning 60 seconds
        for i in range(61):
            reading = Reading(cpm=25, timestamp=base_time + timedelta(seconds=i))
            aggregator.add_reading(reading)

        age = aggregator.get_window_age()
        assert age is not None
        assert age.total_seconds() == pytest.approx(60.0, abs=0.1)

    def test_clear(self):
        """Test clear removes all samples."""
        aggregator = MovingAverageAggregator()
        timestamp = datetime.now()

        # Add some samples
        for i in range(10):
            reading = Reading(cpm=25, timestamp=timestamp + timedelta(seconds=i))
            aggregator.add_reading(reading)

        assert aggregator.get_sample_count() == 10

        # Clear and verify
        aggregator.clear()
        assert aggregator.get_sample_count() == 0
        assert aggregator.get_aggregated() is None

    def test_to_dict_format(self):
        """Test that aggregated reading produces correct dict format."""
        aggregator = MovingAverageAggregator(conversion_factor=0.0065)
        timestamp = datetime.now()

        # Add samples
        for i in range(5):
            reading = Reading(cpm=20 + i * 2, timestamp=timestamp + timedelta(seconds=i))
            aggregator.add_reading(reading)

        result = aggregator.get_aggregated()
        assert result is not None

        data = result.to_dict()
        assert "cpm_avg" in data
        assert "cpm_min" in data
        assert "cpm_max" in data
        assert "usv_h_avg" in data
        assert "window_minutes" in data
        assert "sample_count" in data
        assert "timestamp" in data
        assert "unit" in data
        assert data["unit"] == "CPM"

    def test_string_representation(self):
        """Test string representation."""
        aggregator = MovingAverageAggregator(window_seconds=300)
        str_repr = str(aggregator)
        assert "MovingAverageAggregator" in str_repr
        assert "window=300s" in str_repr
        assert "samples=0" in str_repr
