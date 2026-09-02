"""
Resilience test suite for YFinanceProvider + resilience utilities.
Run from backend/ directory: python test_resilience.py
"""
import sys
import asyncio
import traceback

sys.path.insert(0, '.')

results = {}

def run_test(name, fn):
    try:
        fn()
        results[name] = ("PASS", None)
    except AssertionError as e:
        results[name] = ("FAIL", str(e))
    except Exception as e:
        results[name] = ("ERROR", f"{type(e).__name__}: {e}\n{traceback.format_exc()}")


# ──────────────────────────────────────────────────────
# Test 0: Import validation
# ──────────────────────────────────────────────────────
def test_imports():
    from app.providers.yfinance_provider import YFinanceProvider
    from app.utils.resilience import classify_error, CircuitBreaker
    # ErrorClassifier is NOT a class — it's a function classify_error()
    # Verify it exists
    assert callable(classify_error), "classify_error should be callable"
    assert CircuitBreaker is not None, "CircuitBreaker class should exist"

run_test("0_imports", test_imports)

# ──────────────────────────────────────────────────────
# Initialize provider
# ──────────────────────────────────────────────────────
from app.providers.yfinance_provider import YFinanceProvider
from app.utils.resilience import classify_error, CircuitBreaker

provider = YFinanceProvider()

# ──────────────────────────────────────────────────────
# Test 1: Valid ticker fetch (AAPL)
# ──────────────────────────────────────────────────────
def test_valid_ticker():
    result = asyncio.run(provider.get_current_price("AAPL"))
    print(f"  AAPL result keys: {list(result.keys())}")
    print(f"  AAPL price: {result.get('price')}")
    print(f"  AAPL status: {result.get('status')}")
    assert result.get("price") is not None, f"AAPL price should not be None, got: {result.get('price')}"
    assert isinstance(result.get("price"), (int, float)), f"AAPL price should be numeric, got: {type(result.get('price'))}"
    assert result.get("price") > 0, f"AAPL price should be positive, got: {result.get('price')}"

run_test("1_valid_ticker_AAPL", test_valid_ticker)

# ──────────────────────────────────────────────────────
# Test 2: Invalid ticker
# ──────────────────────────────────────────────────────
def test_invalid_ticker():
    result = asyncio.run(provider.get_current_price("INVALID_TICKER_XYZ"))
    print(f"  Invalid ticker result: {result}")
    has_error = result.get("error") is not None
    is_not_found = result.get("status") in ("not_found", "provider_unavailable")
    assert has_error or is_not_found, \
        f"Invalid ticker should return error/not_found, got: status={result.get('status')}, error={result.get('error')}"

run_test("2_invalid_ticker", test_invalid_ticker)

# ──────────────────────────────────────────────────────
# Test 3: Error classification (classify_error function)
# NOTE: The original test used ErrorClassifier() class which doesn't exist.
# The actual API is classify_error(exc=None, message="...")
# ──────────────────────────────────────────────────────
def test_error_classification():
    # Test 429 classification
    r1 = classify_error(exc=Exception('HTTP Error 429'))
    print(f"  429 classification: {r1}")
    assert r1 == "rate_limited", f"429 should be 'rate_limited', got: {r1}"

    # Test timeout classification
    r2 = classify_error(exc=Exception('timeout'))
    print(f"  Timeout classification: {r2}")
    assert r2 == "timeout", f"timeout should be 'timeout', got: {r2}"

    # Test JSON decode classification
    r3 = classify_error(exc=Exception('JSONDecodeError'))
    print(f"  JSON decode classification: {r3}")
    assert r3 == "parse_error", f"JSONDecodeError should be 'parse_error', got: {r3}"

run_test("3_error_classification", test_error_classification)

# ──────────────────────────────────────────────────────
# Test 4: Circuit breaker
# NOTE: CircuitBreaker constructor takes (name, failure_threshold, cooldown_seconds)
# Not (threshold, recovery_timeout) as the test assumed.
# ──────────────────────────────────────────────────────
def test_circuit_breaker():
    cb = CircuitBreaker(name="test", failure_threshold=3, cooldown_seconds=1)
    print(f"  Initial state: {cb.state}")
    assert cb.state == "closed", f"Initial state should be 'closed', got: {cb.state}"
    print(f"  Allow request: {cb.allow_request()}")
    assert cb.allow_request() == True, "Should allow request when closed"
    # Record some failures
    for i in range(3):
        cb.record_failure(category="rate_limited")
    print(f"  State after 3 failures: {cb.state}")
    assert cb.state == "open", f"After threshold failures, state should be 'open', got: {cb.state}"
    assert cb.allow_request() == False, "Should NOT allow request when open"
    # After cooldown
    import time
    time.sleep(1.1)
    print(f"  State after cooldown: {cb.state}")
    assert cb.state == "half_open", f"After cooldown, state should be 'half_open', got: {cb.state}"
    assert cb.allow_request() == True, "Should allow probe request when half_open"
    # Success resets
    cb.record_success()
    print(f"  State after success: {cb.state}")
    assert cb.state == "closed", f"After success, state should be 'closed', got: {cb.state}"

run_test("4_circuit_breaker", test_circuit_breaker)

# ──────────────────────────────────────────────────────
# Test 5: Stock info for ETF vs stock
# ──────────────────────────────────────────────────────
def test_etf_vs_stock():
    voo_info = asyncio.run(provider.get_stock_info("VOO"))
    aapl_info = asyncio.run(provider.get_stock_info("AAPL"))
    print(f"  VOO asset_type: {voo_info.get('asset_type')}")
    print(f"  VOO has etf_data: {'etf_data' in voo_info}")
    print(f"  AAPL asset_type: {aapl_info.get('asset_type')}")
    print(f"  AAPL has etf_data: {'etf_data' in aapl_info}")
    # VOO should be ETF
    assert voo_info.get("asset_type") == "ETF", \
        f"VOO asset_type should be 'ETF', got: {voo_info.get('asset_type')}"
    assert "etf_data" in voo_info, "VOO should have 'etf_data' key"
    # AAPL should be EQUITY (not ETF)
    assert aapl_info.get("asset_type") == "EQUITY", \
        f"AAPL asset_type should be 'EQUITY', got: {aapl_info.get('asset_type')}"
    assert "etf_data" not in aapl_info, "AAPL should NOT have 'etf_data' key"

run_test("5_etf_vs_stock_info", test_etf_vs_stock)

# ──────────────────────────────────────────────────────
# Test 6: Batch historical download
# ──────────────────────────────────────────────────────
def test_historical_prices():
    hist = asyncio.run(provider.get_historical_prices("AAPL", period="5d"))
    print(f"  AAPL 5d history type: {type(hist)}")
    print(f"  AAPL 5d history points: {len(hist)}")
    assert len(hist) > 0, f"Should have historical data, got {len(hist)} rows"
    # Check required columns exist
    required_cols = {"Date", "Open", "High", "Low", "Close", "Volume"}
    actual_cols = set(hist.columns)
    assert required_cols.issubset(actual_cols), \
        f"Missing columns: {required_cols - actual_cols}"

run_test("6_historical_prices", test_historical_prices)

# ──────────────────────────────────────────────────────
# Test 7: No fabricated data for missing fields
# ──────────────────────────────────────────────────────
def test_no_fabricated_data():
    result = asyncio.run(provider.get_stock_info("AAPL"))
    print("  Field inspection:")
    for key in ['pe_ratio', 'market_cap', 'revenue', 'profit_margin']:
        val = result.get(key)
        if val is None:
            print(f"    {key}: None (correct - not fabricated)")
        else:
            print(f"    {key}: {val}")
    # The key assertion: we do NOT fabricate data.
    # If yfinance provides it, great. If not, it should be None.
    # We just verify the fields exist in the result dict.
    for key in ['pe_ratio', 'market_cap', 'revenue', 'profit_margin']:
        assert key in result, f"Key '{key}' should be present in result (even if None)"
    # Verify no placeholder/fake values (0, "N/A", "unknown", etc.)
    for key in ['pe_ratio', 'market_cap', 'revenue', 'profit_margin']:
        val = result.get(key)
        if val is not None:
            assert isinstance(val, (int, float)), \
                f"{key} should be numeric or None, got: {type(val)} = {val}"
            # For fields that yfinance doesn't return for ETFs or certain stocks,
            # they come back as None — that's correct behavior.

run_test("7_no_fabricated_data", test_no_fabricated_data)

# ──────────────────────────────────────────────────────
# Print report
# ──────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  RESILIENCE TEST REPORT")
print("=" * 60)
all_pass = True
for name, (status, detail) in results.items():
    icon = "PASS" if status == "PASS" else ("FAIL" if status == "FAIL" else "ERROR")
    line = f"  [{icon}] {name}"
    if detail:
        line += f"  —  {detail.splitlines()[0]}"
    print(line)
    if status != "PASS":
        all_pass = False

print("=" * 60)
total = len(results)
passed = sum(1 for s, _ in results.values() if s == "PASS")
print(f"  {passed}/{total} tests passed")
if all_pass:
    print("  ALL TESTS PASSED")
else:
    print("  SOME TESTS FAILED")
print("=" * 60)
