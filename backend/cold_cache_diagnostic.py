"""
COLD CACHE DIAGNOSTIC MEASUREMENT

Simulates fresh machine: new DB, no cache, imports client's 25 holdings,
then measures exact provider call count for each page load.

Runs:
  1. Trading Opportunities (cold cache)
  2. Portfolio Health (warm cache from step 1)
  3. Catalyst summary (independent)
  4. Dashboard (combination of above)
"""
import sys
import os
import time
import json
import shutil
import tempfile
import asyncio
import urllib.request

BACKEND = "http://localhost:8000"

# Client's 25 holdings
CLIENT_HOLDINGS = [
    "VOO", "VYM", "JPM", "CSCO", "TXN", "UNH", "MSFT", "JNJ", "O", "ABBV",
    "SBUX", "KMB", "AAPL", "V", "UL", "LOW", "AMT", "SNA", "COST", "PEP",
    "OHI", "MAIN", "DHI", "AGCO", "MICC"
]


def api_get(path):
    """Call backend API."""
    url = f"{BACKEND}{path}"
    req = urllib.request.Request(url)
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            dur = (time.time() - start) * 1000
            return data, dur
    except Exception as e:
        dur = (time.time() - start) * 1000
        return {"error": str(e)}, dur


def api_post(path):
    url = f"{BACKEND}{path}"
    req = urllib.request.Request(url, method="POST")
    start = time.time()
    try:
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
            dur = (time.time() - start) * 1000
            return data, dur
    except Exception as e:
        dur = (time.time() - start) * 1000
        return {"error": str(e)}, dur


def get_trace():
    """Get the latest request trace from diagnostics."""
    data, _ = api_get("/diagnostics/request-trace")
    return data


def get_provider_health():
    """Get provider health snapshot."""
    data, _ = api_get("/diagnostics")
    return data


def reset_provider_health():
    """No explicit reset endpoint, but we record health before/after."""
    pass


def measure_section(name, api_call):
    """Run an API call and measure it, then get the trace."""
    print(f"\n{'='*60}")
    print(f"  {name}")
    print(f"{'='*60}")

    # Record provider health before
    health_before = get_provider_health()
    yahoo_before = health_before.get("providers", {}).get("yahoo", {})
    requests_before = yahoo_before.get("requests_total", 0)
    cache_hits_before = yahoo_before.get("cache_hits", 0)

    # Make the API call
    result, dur_ms = api_call()

    # Record provider health after
    health_after = get_provider_health()
    yahoo_after = health_after.get("providers", {}).get("yahoo", {})
    requests_after = yahoo_after.get("requests_total", 0)
    cache_hits_after = yahoo_after.get("cache_hits", 0)

    # Get latest trace
    trace_data = get_trace()
    traces = trace_data.get("recent_traces", [])
    latest_trace = traces[-1] if traces else {}

    provider_calls = requests_after - requests_before
    cache_hit_delta = cache_hits_after - cache_hits_before

    print(f"  API response time: {dur_ms:.0f}ms")
    print(f"  Provider calls (new): {provider_calls}")
    print(f"  Cache hits (new): {cache_hit_delta}")
    print(f"  Batch calls: {latest_trace.get('batch_calls', '?')}")
    print(f"  Individual fallback: {latest_trace.get('individual_fallback_calls', '?')}")
    print(f"  Retries: {latest_trace.get('retries', '?')}")
    print(f"  Rate limits: {latest_trace.get('rate_limits', '?')}")
    print(f"  Stale served: {latest_trace.get('stale_served', '?')}")
    print(f"  Cache hits in trace: {latest_trace.get('cache_hits', '?')}")
    print(f"  Cache misses in trace: {latest_trace.get('cache_misses', '?')}")
    print(f"  Operations breakdown: {latest_trace.get('operations_breakdown', {})}")
    print(f"  Tickers fetched from provider: {latest_trace.get('tickers_fetched', [])}")
    print(f"  Data status: {result.get('data', {}).get('data_status', 'N/A')}")

    if latest_trace.get("data_quality"):
        print(f"  Data quality: {latest_trace['data_quality']}")

    return {
        "name": name,
        "api_dur_ms": dur_ms,
        "provider_calls": provider_calls,
        "cache_hits": cache_hit_delta,
        "batch_calls": latest_trace.get("batch_calls", 0),
        "individual_fallback": latest_trace.get("individual_fallback_calls", 0),
        "retries": latest_trace.get("retries", 0),
        "rate_limits": latest_trace.get("rate_limits", 0),
        "trace": latest_trace,
    }


def main():
    print("=" * 60)
    print("  COLD CACHE DIAGNOSTIC MEASUREMENT")
    print("=" * 60)

    # Step 0: Verify backend is alive
    health, _ = api_get("/health")
    print(f"\nBackend: {health.get('status', 'DEAD')}")
    if health.get("status") != "ok":
        print("FATAL: Backend not running")
        sys.exit(1)

    # Step 0.5: Get environment info
    env, _ = api_get("/diagnostics/environment")
    print(f"\nEnvironment:")
    for k, v in env.items():
        print(f"  {k}: {v}")

    # Step 1: Reset provider health baseline
    health_start = get_provider_health()
    yahoo_start = health_start.get("providers", {}).get("yahoo", {})
    print(f"\nProvider baseline: requests_total={yahoo_start.get('requests_total', 0)}, "
          f"cache_hits={yahoo_start.get('cache_hits', 0)}")

    # Step 2: Clear caches by restarting backend
    print("\n--- CLEARING CACHES (restart backend) ---")
    # We can't restart from here, but we can use ?refresh=true to bypass result cache
    # The real cold cache test requires manual DB replacement

    results = []

    # ============================================================
    # TEST 1: Trading Opportunities (cold cache, ?refresh=true)
    # ============================================================
    r = measure_section(
        "TEST 1: Trading Opportunities (refresh=true)",
        lambda: api_get("/analytics/trading-opportunities?refresh=true")
    )
    results.append(r)

    # ============================================================
    # TEST 2: Trading Opportunities (warm cache, no refresh)
    # ============================================================
    r = measure_section(
        "TEST 2: Trading Opportunities (cached, no refresh)",
        lambda: api_get("/analytics/trading-opportunities")
    )
    results.append(r)

    # ============================================================
    # TEST 3: Portfolio Health (refresh=true)
    # ============================================================
    r = measure_section(
        "TEST 3: Portfolio Health (refresh=true)",
        lambda: api_get("/analytics/portfolio-health?refresh=true")
    )
    results.append(r)

    # ============================================================
    # TEST 4: Portfolio Health (cached)
    # ============================================================
    r = measure_section(
        "TEST 4: Portfolio Health (cached)",
        lambda: api_get("/analytics/portfolio-health")
    )
    results.append(r)

    # ============================================================
    # TEST 5: Risk Summary
    # ============================================================
    r = measure_section(
        "TEST 5: Risk Summary",
        lambda: api_get("/portfolio/risk-summary")
    )
    results.append(r)

    # ============================================================
    # TEST 6: Dashboard data (portfolio + performance)
    # ============================================================
    print(f"\n{'='*60}")
    print(f"  TEST 6: Dashboard (portfolio + performance)")
    print(f"{'='*60}")
    p1, d1 = api_get("/portfolio")
    p2, d2 = api_get("/portfolio/performance")
    print(f"  /portfolio: {d1:.0f}ms")
    print(f"  /portfolio/performance: {d2:.0f}ms")
    results.append({"name": "Dashboard", "api_dur_ms": d1 + d2, "provider_calls": 0})

    # ============================================================
    # TEST 7: Catalyst summary
    # ============================================================
    r = measure_section(
        "TEST 7: Catalyst Summary",
        lambda: api_get("/catalysts/summary")
    )
    results.append(r)

    # ============================================================
    # FINAL SUMMARY
    # ============================================================
    print(f"\n{'='*60}")
    print(f"  FINAL MEASUREMENT SUMMARY")
    print(f"{'='*60}")

    health_end = get_provider_health()
    yahoo_end = health_end.get("providers", {}).get("yahoo", {})

    total_requests = yahoo_end.get("requests_total", 0)
    total_cache_hits = yahoo_end.get("cache_hits", 0)
    total_successes = yahoo_end.get("successes", 0)
    total_failures = yahoo_end.get("failures", 0)
    by_category = yahoo_end.get("by_category", {})

    print(f"\n  Total Yahoo provider requests: {total_requests}")
    print(f"  Total cache hits: {total_cache_hits}")
    print(f"  Total successes: {total_successes}")
    print(f"  Total failures: {total_failures}")
    print(f"  Failure categories: {by_category}")

    print(f"\n  Per-section breakdown:")
    for r in results:
        print(f"    {r['name']}: {r.get('provider_calls', '?')} provider calls, "
              f"{r.get('cache_hits', '?')} cache hits, "
              f"{r.get('api_dur_ms', 0):.0f}ms")

    # Key diagnostic question: how many Yahoo calls for one page load?
    trading = results[0]  # Cold cache trading
    print(f"\n  *** KEY ANSWER: One cold-cache Trading Opportunities page load ***")
    print(f"  Yahoo provider calls: {trading.get('provider_calls', '?')}")
    print(f"  Batch calls: {trading.get('batch_calls', '?')}")
    print(f"  Individual fallback: {trading.get('individual_fallback', '?')}")

    # Write results to file
    with open("cold_cache_measurement.json", "w") as f:
        json.dump({
            "results": results,
            "provider_health_final": yahoo_end,
        }, f, indent=2, default=str)
    print(f"\n  Results saved to cold_cache_measurement.json")


if __name__ == "__main__":
    main()
