"""
Request tracing — simplified, reliable, thread-safe.

Does NOT use ContextVar (breaks in ThreadPoolExecutor).
Uses process-wide atomic counters instead.

Every provider call increments a counter. We measure from those counters.
"""
import time
import threading
from typing import Dict, Any, List, Optional
from dataclasses import dataclass, field


@dataclass
class ProviderCallRecord:
    """One provider call record."""
    timestamp: float
    operation: str
    tickers: str
    cache_hit: bool
    batch: bool
    success: bool
    failure_category: str
    stale_served: bool
    duration_ms: float = 0.0


class RequestTracer:
    """Process-wide, thread-safe provider call tracker."""

    def __init__(self):
        self._lock = threading.Lock()
        self._calls: List[ProviderCallRecord] = []
        self._counters: Dict[str, int] = {}

    def log(self, operation: str, tickers: str, cache_hit: bool,
            batch: bool = False, success: bool = True,
            failure_category: str = "", stale: bool = False,
            duration_ms: float = 0.0):
        """Log a provider call."""
        record = ProviderCallRecord(
            timestamp=time.time(),
            operation=operation,
            tickers=tickers,
            cache_hit=cache_hit,
            batch=batch,
            success=success,
            failure_category=failure_category,
            stale_served=stale,
            duration_ms=duration_ms,
        )
        with self._lock:
            self._calls.append(record)
            # Keep last 500 calls
            if len(self._calls) > 500:
                self._calls = self._calls[-500:]
            # Increment counters
            key = f"{operation}:{'batch' if batch else 'individual'}"
            self._counters[key] = self._counters.get(key, 0) + 1

    def summary(self) -> Dict[str, Any]:
        """Return a summary of all tracked calls."""
        with self._lock:
            calls = list(self._calls)
            counters = dict(self._counters)

        if not calls:
            return {"total_calls": 0, "counters": counters}

        total = len(calls)
        cache_hits = sum(1 for c in calls if c.cache_hit)
        cache_misses = total - cache_hits
        successes = sum(1 for c in calls if c.success)
        failures = total - successes
        batches = sum(1 for c in calls if c.batch)
        individuals = total - batches
        stale_served = sum(1 for c in calls if c.stale_served)
        retries = sum(1 for c in calls if c.failure_category and not c.cache_hit)
        rate_limits = sum(1 for c in calls if c.failure_category == "rate_limited")

        # Ticker breakdown
        tickers_fetched = set()
        for c in calls:
            if not c.cache_hit:
                for t in c.tickers.split(","):
                    t = t.strip()
                    if t:
                        tickers_fetched.add(t)

        # Calls per operation
        by_op: Dict[str, int] = {}
        for c in calls:
            key = f"{'batch_' if c.batch else ''}{c.operation}"
            by_op[key] = by_op.get(key, 0) + 1

        # Burst detection: calls within first 1s, 5s
        if calls:
            t0 = calls[0].timestamp
            first_1s = sum(1 for c in calls if c.timestamp - t0 <= 1.0)
            first_5s = sum(1 for c in calls if c.timestamp - t0 <= 5.0)
        else:
            first_1s = first_5s = 0

        return {
            "total_calls": total,
            "cache_hits": cache_hits,
            "cache_misses": cache_misses,
            "successes": successes,
            "failures": failures,
            "batch_calls": batches,
            "individual_calls": individuals,
            "stale_served": stale_served,
            "rate_limits": rate_limits,
            "tickers_fetched": sorted(tickers_fetched),
            "by_operation": by_op,
            "first_1s_calls": first_1s,
            "first_5s_calls": first_5s,
            "counters": counters,
        }

    def reset(self):
        """Clear all tracked calls."""
        with self._lock:
            self._calls.clear()
            self._counters.clear()

    def get_raw_calls(self) -> list:
        """Return all call records as serializable dicts."""
        with self._lock:
            calls = list(self._calls)
        return [
            {
                "timestamp": c.timestamp,
                "operation": c.operation,
                "tickers": c.tickers,
                "cache_hit": c.cache_hit,
                "batch": c.batch,
                "success": c.success,
                "failure_category": c.failure_category,
                "stale_served": c.stale_served,
                "duration_ms": c.duration_ms,
            }
            for c in calls
        ]


# Process-wide singleton
_tracer: Optional[RequestTracer] = None
_lock = threading.Lock()


def get_request_tracer() -> RequestTracer:
    global _tracer
    if _tracer is None:
        with _lock:
            if _tracer is None:
                _tracer = RequestTracer()
    return _tracer
