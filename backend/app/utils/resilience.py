"""
Provider resilience infrastructure.

- ErrorClassifier: categorizes provider exceptions into actionable classes
- CircuitBreaker: stops hammering a failing provider; half-open recovery
- ProviderHealth: process-wide observability registry (diagnostics endpoint)

No fake data is ever produced here — only failure classification and state.
"""
import time
import logging
import random
import threading
from typing import Dict, Any, Optional, List
from datetime import datetime

logger = logging.getLogger(__name__)


class ErrorCategory:
    RATE_LIMITED = "rate_limited"
    TIMEOUT = "timeout"
    PARSE_ERROR = "parse_error"
    NOT_FOUND = "not_found"
    NETWORK = "network"
    AUTH = "auth"
    UNKNOWN = "unknown"


def classify_error(exc: Optional[BaseException] = None, message: str = "") -> str:
    """
    Classify a provider failure into an ErrorCategory.
    Checks both exception type/message and plain message text.
    """
    text = message or ""
    if exc is not None:
        text = f"{type(exc).__name__}: {exc}"

    t = text.lower()
    if "429" in t or "too many requests" in t or "rate limit" in t:
        return ErrorCategory.RATE_LIMITED
    if "timeout" in t or "timed out" in t or "readtimeout" in t or "connecttimeout" in t:
        return ErrorCategory.TIMEOUT
    if "jsondecodeerror" in t or "expecting value" in t or "json" in t and "decode" in t:
        return ErrorCategory.PARSE_ERROR
    if "404" in t or "not found" in t or "no data" in t or "delisted" in t \
            or "empty" in t or "no rows" in t or "no results" in t:
        return ErrorCategory.NOT_FOUND
    if "401" in t or "403" in t or "unauthorized" in t or "forbidden" in t or "api key" in t:
        return ErrorCategory.AUTH
    if ("connection" in t or "10054" in t or "reset" in t or "unreachable" in t
            or "getaddrinfo failed" in t or "ssl" in t):
        return ErrorCategory.NETWORK
    return ErrorCategory.UNKNOWN


class CircuitBreaker:
    """
    Per-provider circuit breaker.

    States:
      closed     -> normal operation
      open       -> provider failing; calls short-circuit immediately
      half_open  -> after cooldown, allow ONE probe call through

    FailureThreshold consecutive rate-limit/network failures open the circuit.
    """

    def __init__(self, name: str, failure_threshold: int = 5, cooldown_seconds: float = 60.0):
        self.name = name
        self.failure_threshold = failure_threshold
        self.cooldown_seconds = cooldown_seconds
        self._state = "closed"
        self._failure_count = 0
        self._opened_at: float = 0.0
        self._lock = threading.Lock()

    @property
    def state(self) -> str:
        with self._lock:
            if self._state == "open":
                if time.time() - self._opened_at >= self.cooldown_seconds:
                    self._state = "half_open"
            return self._state

    def allow_request(self) -> bool:
        """Whether a provider request may proceed right now."""
        s = self.state
        if s == "closed":
            return True
        if s == "open":
            return False
        # half_open: allow the single probe
        return True

    def record_success(self):
        with self._lock:
            self._state = "closed"
            self._failure_count = 0

    def record_failure(self, category: str = ""):
        with self._lock:
            # Only rate limits / network issues trip the breaker;
            # parse errors / not-found are symbol-specific, not provider-wide.
            if category in (ErrorCategory.RATE_LIMITED, ErrorCategory.NETWORK, ErrorCategory.TIMEOUT, ErrorCategory.AUTH):
                self._failure_count += 1
                if self._failure_count >= self.failure_threshold or self._state == "half_open":
                    self._state = "open"
                    self._opened_at = time.time()
                    logger.warning(
                        f"Circuit breaker '{self.name}' OPENED "
                        f"({self._failure_count} consecutive {category} failures); "
                        f"cooling down {self.cooldown_seconds:.0f}s"
                    )
            else:
                # soft failures don't count toward the breaker
                pass

    def snapshot(self) -> Dict[str, Any]:
        return {
            "state": self.state,
            "failure_count": self._failure_count,
            "cooldown_remaining": max(0.0, self.cooldown_seconds - (time.time() - self._opened_at))
            if self._state == "open" else 0.0,
        }


class ProviderHealth:
    """
    Process-wide provider health registry for the diagnostics endpoint.
    Thread-safe counters; never logs API keys.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._stats: Dict[str, Dict[str, Any]] = {}

    def _bucket(self, provider: str) -> Dict[str, Any]:
        if provider not in self._stats:
            self._stats[provider] = {
                "requests_total": 0,
                "cache_hits": 0,
                "successes": 0,
                "failures": 0,
                "by_category": {},
                "last_success_at": None,
                "last_failure_at": None,
                "last_failure_message": "",
                "avg_duration_ms": None,
                "_durations": [],
            }
        return self._stats[provider]

    def record_cache_hit(self, provider: str):
        with self._lock:
            self._bucket(provider)["cache_hits"] += 1

    def record_success(self, provider: str, duration_ms: float, ticker: str = "", op: str = ""):
        with self._lock:
            b = self._bucket(provider)
            b["requests_total"] += 1
            b["successes"] += 1
            b["last_success_at"] = datetime.utcnow().isoformat()
            b["_durations"].append(duration_ms)
            durs = b["_durations"][-50:]
            b["avg_duration_ms"] = round(sum(durs) / len(durs), 1)
        logger.info(f"[provider:{provider}] ok op={op} ticker={ticker} dur={duration_ms:.0f}ms")

    def record_failure(self, provider: str, category: str, message: str,
                       duration_ms: float = 0.0, ticker: str = "", op: str = ""):
        safe_msg = (message or "")[:200]
        with self._lock:
            b = self._bucket(provider)
            b["requests_total"] += 1
            b["failures"] += 1
            b["by_category"][category] = b["by_category"].get(category, 0) + 1
            b["last_failure_at"] = datetime.utcnow().isoformat()
            b["last_failure_message"] = safe_msg
        logger.warning(
            f"[provider:{provider}] fail op={op} ticker={ticker} "
            f"cat={category} dur={duration_ms:.0f}ms msg={safe_msg}"
        )

    def snapshot(self) -> Dict[str, Any]:
        with self._lock:
            out = {}
            for p, b in self._stats.items():
                out[p] = {k: v for k, v in b.items() if not k.startswith("_")}
            return out


# Process-wide singletons
_health = ProviderHealth()


def get_provider_health() -> ProviderHealth:
    return _health


_breakers: Dict[str, CircuitBreaker] = {}


def get_circuit_breaker(name: str = "yahoo") -> CircuitBreaker:
    if name not in _breakers:
        _breakers[name] = CircuitBreaker(name)
    return _breakers[name]


def backoff_with_jitter(attempt: int, base: float = 2.0, cap: float = 30.0) -> float:
    """Exponential backoff with full jitter: attempt 1 -> ~[1..2)s, capped."""
    exp = min(cap, base ** attempt)
    return random.uniform(exp * 0.5, exp)


def structured_failure(symbol: str, category: str, message: str,
                       cached: bool = False) -> Dict[str, Any]:
    """
    Standardized provider-failure payload. NEVER fabricates values.
    Callers may attach stale cached data under 'stale' when available.
    """
    return {
        "symbol": symbol,
        "price": None,
        "status": "provider_unavailable",
        "error_category": category,
        "error": message[:200],
        "from_stale_cache": cached,
    }
