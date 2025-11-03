"""Processing layer for GMC Geiger counter data (aggregation, averaging)."""

from .aggregator import MovingAverageAggregator

__all__ = ["MovingAverageAggregator"]
