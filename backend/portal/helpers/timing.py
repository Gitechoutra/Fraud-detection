"""Latency measurement helpers."""

import time


def now_ms():
    """A monotonic clock in milliseconds, for measuring durations."""
    return time.perf_counter() * 1000.0


def percentile(values, pct):
    """Nearest-rank percentile; 0 for an empty list."""
    if not values:
        return 0.0
    ordered = sorted(values)
    k = max(0, min(len(ordered) - 1, int(round(pct / 100.0 * len(ordered) + 0.5)) - 1))
    return float(ordered[k])
