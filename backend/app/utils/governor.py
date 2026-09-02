"""
Global Provider Request Governor
================================
Single shared throttle for ALL yfinance/provider calls across the entire application.

Architecture:
- ONE semaphore shared by all callers
- Minimum interval between request starts
- Exponential backoff with jitter on rate limits
- Circuit breaker integration
- Request deduplication (in-flight)
- Cache-first strategy
- Bounded concurrency
"""
import asyncio
import time
import logging
import hashlib
from typing import Any, Callable, Dict, Optional, Awaitable, TypeVar
from functools import wraps
from datetime import datetime

logger = logging.getLogger(__name__)

T = TypeVar("T")

# ── Singleton state ──────────────────────────────────────
_governor: Optional["RequestGovernor"] = None


class RequestGovernor:
    """
    Process-wide singleton that controls ALL provider request flow.

    Every provider call in the application MUST go through this governor.
    This prevents:
    - Request storms (25 simultaneous Yahoo calls)
    - Rate limit violations
    - Circuit breaker bypass
    - Duplicate in-flight requests
    """

    def __init__(
        self,
        max_concurrent: int = 3,
        min_interval: float = 0.4,
        max_retries: int = 3,
        backoff_base: float = 2.0,
        backoff_cap: float = 30.0,
    ):
        self._semaphore = asyncio.Semaphore(max_concurrent)
        self._min_interval = min_interval
        self._max_retries = max_retries
        self._backoff_base = backoff_base
        self._backoff_cap = backoff_cap

        # Timing
        self._last_request_time: float = 0
        self._lock = asyncio.Lock()

        # In-flight dedup: key -> Future
        self._inflight: Dict[str, asyncio.Future] = {}

        # Circuit breaker — delegates to shared resilience circuit breaker
        self._circuit_lock = asyncio.Lock()

        # Statistics
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "provider_calls": 0,
            "dedup_hits": 0,
            "rate_limited": 0,
            "circuit_blocked": 0,
            "successes": 0,
            "failures": 0,
            "retries": 0,
        }

    # ── Circuit breaker — delegates to shared resilience breaker ──

    def _get_shared_breaker(self):
        from app.utils.resilience import get_circuit_breaker
        return get_circuit_breaker("yahoo")

    def _circuit_is_open(self) -> bool:
        breaker = self._get_shared_breaker()
        return not breaker.allow_request()

    def _record_success(self):
        self._stats["successes"] += 1
        self._get_shared_breaker().record_success()

    def _record_failure(self, is_rate_limit: bool = False):
        self._stats["failures"] += 1
        if is_rate_limit:
            self._stats["rate_limited"] += 1
        from app.utils.resilience import ErrorCategory
        self._get_shared_breaker().record_failure(ErrorCategory.RATE_LIMITED if is_rate_limit else ErrorCategory.NETWORK)

    # ── Request timing ───────────────────────────────────

    async def _wait_for_interval(self):
        async with self._lock:
            now = time.time()
            elapsed = now - self._last_request_time
            if elapsed < self._min_interval:
                await asyncio.sleep(self._min_interval - elapsed)
            self._last_request_time = time.time()

    # ── Deduplication ────────────────────────────────────

    def _make_key(self, operation: str, symbol: str, **kwargs) -> str:
        raw = f"{operation}:{symbol}"
        if kwargs:
            raw += ":" + "|".join(f"{k}={v}" for k, v in sorted(kwargs.items()))
        return hashlib.md5(raw.encode()).hexdigest()[:16]

    async def dedup_or_submit(self, key: str, coro_factory: Callable[[], Awaitable[T]]) -> T:
        """
        If an identical request is already in-flight, await its result.
        Otherwise, create a new request and register it.
        """
        if key in self._inflight:
            self._stats["dedup_hits"] += 1
            logger.debug(f"Dedup hit for {key}")
            try:
                return await self._inflight[key]
            except Exception:
                raise

        future = asyncio.get_event_loop().create_future()
        self._inflight[key] = future
        try:
            result = await coro_factory()
            if not future.done():
                future.set_result(result)
            return result
        except Exception as e:
            if not future.done():
                future.set_exception(e)
            raise
        finally:
            self._inflight.pop(key, None)

    # ── Main request entry point ─────────────────────────

    async def execute(
        self,
        operation: str,
        symbol: str,
        func: Callable[[], Awaitable[T]],
        cache_get: Optional[Callable[[], Optional[T]]] = None,
        cache_set: Optional[Callable[[T], None]] = None,
        stale_get: Optional[Callable[[], Optional[T]]] = None,
        **kwargs,
    ) -> T:
        """
        Execute a provider request through the governor.

        1. Check cache -> return immediately if fresh
        2. Check circuit breaker -> try stale if open
        3. Acquire semaphore -> bounded concurrency
        4. Wait for min interval -> rate limiting
        5. Execute with retry on rate limit
        6. Record success/failure
        7. Cache result
        """
        self._stats["total_requests"] += 1

        # Step 1: Cache-first
        if cache_get:
            cached = cache_get()
            if cached is not None:
                self._stats["cache_hits"] += 1
                return cached

        # Step 2: Circuit breaker
        if self._circuit_is_open():
            self._stats["circuit_blocked"] += 1
            if stale_get:
                stale = stale_get()
                if stale is not None:
                    logger.debug(f"Stale cache served for {operation}:{symbol} (circuit open)")
                    return stale
            raise ProviderUnavailableError(
                f"Provider temporarily unavailable for {operation}:{symbol}"
            )

        # Step 3-6: Execute with dedup
        async def _do_request() -> T:
            async with self._semaphore:
                await self._wait_for_interval()
                last_error = None
                for attempt in range(self._max_retries + 1):
                    try:
                        result = await func()
                        self._record_success()
                        return result
                    except Exception as e:
                        last_error = e
                        from app.utils.resilience import classify_error as classify
                        category = classify(e)
                        if category == "rate_limited":
                            self._record_failure(is_rate_limit=True)
                            self._stats["retries"] += 1
                            wait = self._backoff_base ** attempt
                            import random
                            wait = min(wait * (0.5 + random.random()), self._backoff_cap)
                            logger.warning(
                                f"Rate limited on {operation}:{symbol} "
                                f"(attempt {attempt + 1}), backing off {wait:.1f}s"
                            )
                            await asyncio.sleep(wait)
                            continue
                        elif category in ("network", "timeout"):
                            self._record_failure()
                            self._stats["retries"] += 1
                            wait = self._backoff_base ** attempt * 0.5
                            import random
                            wait = min(wait * (0.5 + random.random()), self._backoff_cap)
                            logger.debug(
                                f"Network error on {operation}:{symbol} "
                                f"(attempt {attempt + 1}), backing off {wait:.1f}s"
                            )
                            await asyncio.sleep(wait)
                            continue
                        else:
                            # not_found, parse_error, auth, unknown -> don't retry
                            self._record_failure()
                            raise
                # All retries exhausted
                self._record_failure()
                raise last_error

        key = self._make_key(operation, symbol, **kwargs)
        result = await self.dedup_or_submit(key, _do_request)

        # Step 7: Cache result
        if cache_set and result is not None:
            try:
                cache_set(result)
            except Exception:
                pass

        return result

    # ── Stats ────────────────────────────────────────────

    def get_stats(self) -> Dict[str, Any]:
        breaker = self._get_shared_breaker()
        return {
            **self._stats,
            "circuit_open": breaker.state == "open",
            "circuit_state": breaker.state,
            "consecutive_failures": breaker._failure_count,
            "inflight_count": len(self._inflight),
        }

    def reset_stats(self):
        self._stats = {
            "total_requests": 0,
            "cache_hits": 0,
            "provider_calls": 0,
            "dedup_hits": 0,
            "rate_limited": 0,
            "circuit_blocked": 0,
            "successes": 0,
            "failures": 0,
            "retries": 0,
        }


class ProviderUnavailableError(Exception):
    """Raised when the provider circuit breaker is open and no stale data is available."""
    pass


# ── Singleton access ─────────────────────────────────────

def get_governor() -> RequestGovernor:
    global _governor
    if _governor is None:
        _governor = RequestGovernor()
    return _governor
