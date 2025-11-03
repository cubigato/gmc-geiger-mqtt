"""Moving average aggregator for GMC Geiger counter readings."""

import logging
from collections import deque
from datetime import datetime, timedelta
from typing import Optional

from ..models import AggregatedReading, Reading

logger = logging.getLogger(__name__)


class MovingAverageAggregator:
    """
    Aggregates readings over a time window and calculates statistics.

    This class maintains a sliding window of readings and can calculate:
    - Average CPM
    - Minimum CPM
    - Maximum CPM
    - Average µSv/h
    - Sample count
    """

    def __init__(
        self,
        window_seconds: int = 600,
        conversion_factor: float = 0.0065,
    ):
        """
        Initialize the aggregator.

        Args:
            window_seconds: Time window in seconds (default: 600 = 10 minutes)
            conversion_factor: CPM to µSv/h conversion factor
        """
        self.window_seconds = window_seconds
        self.conversion_factor = conversion_factor
        self._samples: deque[Reading] = deque()
        self._last_aggregation_time: Optional[datetime] = None

        logger.info(
            f"Moving average aggregator initialized "
            f"(window={window_seconds}s, factor={conversion_factor})"
        )

    def add_reading(self, reading: Reading) -> None:
        """
        Add a reading to the aggregator.

        Automatically removes old readings outside the time window.

        Args:
            reading: Reading to add
        """
        self._samples.append(reading)
        self._clean_old_samples(reading.timestamp)

        logger.debug(
            f"Added reading (CPM={reading.cpm}), window now contains {len(self._samples)} samples"
        )

    def _clean_old_samples(self, current_time: datetime) -> None:
        """
        Remove samples older than the time window.

        Args:
            current_time: Current timestamp to calculate window from
        """
        cutoff_time = current_time - timedelta(seconds=self.window_seconds)

        # Remove old samples from the left (oldest)
        while self._samples and self._samples[0].timestamp < cutoff_time:
            removed = self._samples.popleft()
            logger.debug(
                f"Removed old sample from {removed.timestamp.isoformat()} (CPM={removed.cpm})"
            )

    def get_aggregated(self) -> Optional[AggregatedReading]:
        """
        Calculate and return aggregated statistics.

        Returns:
            AggregatedReading with statistics, or None if no samples available
        """
        if not self._samples:
            logger.warning("No samples available for aggregation")
            return None

        # Calculate statistics
        cpm_values = [reading.cpm for reading in self._samples]
        cpm_avg = sum(cpm_values) / len(cpm_values)
        cpm_min = min(cpm_values)
        cpm_max = max(cpm_values)

        # Calculate average µSv/h
        usv_h_avg = cpm_avg * self.conversion_factor

        # Use the timestamp of the most recent sample
        timestamp = self._samples[-1].timestamp

        aggregated = AggregatedReading(
            cpm_avg=cpm_avg,
            cpm_min=cpm_min,
            cpm_max=cpm_max,
            usv_h_avg=usv_h_avg,
            window_seconds=self.window_seconds,
            sample_count=len(self._samples),
            timestamp=timestamp,
            samples=list(self._samples),
        )

        logger.debug(
            f"Calculated aggregated reading: "
            f"avg={cpm_avg:.1f}, min={cpm_min}, max={cpm_max}, "
            f"samples={len(self._samples)}"
        )

        return aggregated

    def should_publish(self, current_time: datetime, interval_seconds: int) -> bool:
        """
        Check if enough time has passed since last aggregation to publish.

        Args:
            current_time: Current timestamp
            interval_seconds: Minimum interval between publications

        Returns:
            True if should publish, False otherwise
        """
        if self._last_aggregation_time is None:
            return True

        elapsed = (current_time - self._last_aggregation_time).total_seconds()
        should_publish = elapsed >= interval_seconds

        if should_publish:
            logger.debug(
                f"Should publish aggregation (elapsed={elapsed:.1f}s >= {interval_seconds}s)"
            )

        return should_publish

    def mark_published(self, timestamp: datetime) -> None:
        """
        Mark that an aggregation was published at the given time.

        Args:
            timestamp: Timestamp of publication
        """
        self._last_aggregation_time = timestamp
        logger.debug(f"Marked aggregation published at {timestamp.isoformat()}")

    def get_sample_count(self) -> int:
        """
        Get the current number of samples in the window.

        Returns:
            Number of samples
        """
        return len(self._samples)

    def get_window_age(self) -> Optional[timedelta]:
        """
        Get the age of the oldest sample in the window.

        Returns:
            Timedelta of oldest sample age, or None if no samples
        """
        if not self._samples:
            return None

        oldest = self._samples[0]
        newest = self._samples[-1]
        return newest.timestamp - oldest.timestamp

    def clear(self) -> None:
        """Clear all samples from the aggregator."""
        sample_count = len(self._samples)
        self._samples.clear()
        self._last_aggregation_time = None
        logger.info(f"Cleared aggregator ({sample_count} samples removed)")

    def __str__(self) -> str:
        """String representation of aggregator state."""
        return (
            f"MovingAverageAggregator(window={self.window_seconds}s, samples={len(self._samples)})"
        )
