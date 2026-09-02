"""
Comprehensive test: CSV import + Ticker normalization + Portfolio service.
Run from backend/ directory: python -m tests.test_csv_import_and_ticker_normalization
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import traceback
from app.services.ticker_service import get_ticker_service
from app.utils.ticker import normalize_ticker as util_normalize, validate_ticker as util_validate

# ============================================================
# TEST RESULTS TRACKER
# ============================================================
results = []

def record(test_name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((test_name, status, detail))
    print(f"  [{status}] {test_name}" + (f" — {detail}" if detail else ""))

# ============================================================
# 1. READ CSV AND EXTRACT TICKERS
# ============================================================
print("\n" + "=" * 70)
print("TEST 1: Read Holdings-Aug-16-2026.csv and extract tickers")
print("=" * 70)

csv_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                        "..", "Holdings-Aug-16-2026.csv")
csv_path = os.path.normpath(csv_path)

import csv
csv_tickers = []
try:
    with open(csv_path, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            sym = row.get("Symbol", "").strip()
            if sym:
                csv_tickers.append(sym)
    record("CSV file read successfully", True, f"Found {len(csv_tickers)} tickers")
    record("Ticker list matches expected 25 holdings", len(csv_tickers) == 25,
           f"Got {len(csv_tickers)} tickers")
    print(f"    Tickers: {csv_tickers}")
except FileNotFoundError:
    record("CSV file found", False, f"Path: {csv_path}")
except Exception as e:
    record("CSV file read", False, str(e))

# ============================================================
# 2. VALIDATE EVERY CSV TICKER THROUGH TICKER SERVICE
# ============================================================
print("\n" + "=" * 70)
print("TEST 2: Validate every CSV ticker through TickerService")
print("=" * 70)

ts = get_ticker_service()

all_valid = True
for ticker in csv_tickers:
    try:
        canonical = ts.validate_or_raise(ticker)
        is_correct = (canonical == ticker)
        record(f"validate_or_raise('{ticker}')", is_correct,
               f"returned '{canonical}'" + (" (correct — no unwanted normalization)" if is_correct else f" (UNWANTED CHANGE from '{ticker}')"))
        if not is_correct:
            all_valid = False
    except ValueError as e:
        record(f"validate_or_raise('{ticker}')", False, f"ValueError: {e}")
        all_valid = False
    except Exception as e:
        record(f"validate_or_raise('{ticker}')", False, f"Exception: {e}")
        all_valid = False

record("ALL 25 CSV tickers validate correctly", all_valid)

# ============================================================
# 3. TEST PORTFOLIO SERVICE — LOAD HOLDINGS FROM DB
# ============================================================
print("\n" + "=" * 70)
print("TEST 3: PortfolioService.get_holdings() — load from database")
print("=" * 70)

try:
    from app.database import SessionLocal, init_db
    init_db()
    db = SessionLocal()

    from app.services.portfolio_service import PortfolioService
    ps = PortfolioService(db)

    holdings = ps.get_holdings()
    record("get_holdings() returns a list", isinstance(holdings, list),
           f"Type: {type(holdings).__name__}")
    record("Portfolio has 25 holdings in DB", len(holdings) == 25,
           f"Got {len(holdings)} holdings")

    if holdings:
        print(f"    Total holdings: {len(holdings)}")
        for h in holdings:
            sym = h.get('symbol', '?')
            name = h.get('name', 'N/A')
            alloc = h.get('allocation_pct', 0)
            print(f"    {sym}: {name}, alloc={alloc:.2f}%")
    else:
        print("    [WARNING] No holdings in DB — run CSV import first")

    # Verify VOO is present and not V00
    symbols_in_db = [h.get('symbol') for h in holdings]
    record("VOO is in DB (not V00)", "VOO" in symbols_in_db,
           f"Symbols: {symbols_in_db[:10]}...")
    record("V00 is NOT in DB", "V00" not in symbols_in_db)
    record("O (Realty Income) is in DB", "O" in symbols_in_db)
    record("V (Visa) is in DB", "V" in symbols_in_db)
    record("UL (Unilever) is in DB", "UL" in symbols_in_db)
    record("JNJ is in DB", "JNJ" in symbols_in_db)
    record("AAPL is in DB (not APPL)", "AAPL" in symbols_in_db and "APPL" not in symbols_in_db)

    db.close()
except Exception as e:
    record("PortfolioService instantiation", False, f"Exception: {e}\n{traceback.format_exc()}")

# ============================================================
# 4. VERIFY PORTFOLIO SUMMARY CALCULATIONS
# ============================================================
print("\n" + "=" * 70)
print("TEST 4: Portfolio summary calculations")
print("=" * 70)

try:
    from app.database import SessionLocal
    from app.services.portfolio_service import PortfolioService
    db = SessionLocal()
    ps = PortfolioService(db)

    summary = ps.get_portfolio_summary()
    record("get_portfolio_summary() returns dict", isinstance(summary, dict))

    total_value = summary.get('total_value', 0)
    total_cost = summary.get('total_cost_basis', 0)
    gain_loss = summary.get('total_gain_loss', 0)
    gain_loss_pct = summary.get('total_gain_loss_pct', 0)
    num_holdings = summary.get('num_holdings', 0)

    print(f"    Total value:     ${total_value:,.2f}")
    print(f"    Total cost:      ${total_cost:,.2f}")
    print(f"    Gain/Loss:       ${gain_loss:,.2f}")
    print(f"    Gain/Loss %:     {gain_loss_pct:.2f}%")
    print(f"    Num holdings:    {num_holdings}")

    record("total_value > 0", total_value > 0, f"${total_value:,.2f}")
    record("total_cost_basis > 0", total_cost > 0, f"${total_cost:,.2f}")
    record("num_holdings == 25", num_holdings == 25, f"Got {num_holdings}")
    record("gain_loss is numeric", isinstance(gain_loss, (int, float)),
           f"${gain_loss:,.2f}")
    record("gain_loss_pct is numeric", isinstance(gain_loss_pct, (int, float)),
           f"{gain_loss_pct:.2f}%")

    # Sanity check: gain should roughly equal CSV unrealized gains
    # CSV total value is ~10,585+9,195+7,277+... ~ $120K+
    record("total_value > 50000 (sanity check)", total_value > 50000,
           f"${total_value:,.2f} seems reasonable for a diversified portfolio")

    db.close()
except Exception as e:
    record("Portfolio summary", False, f"Exception: {e}\n{traceback.format_exc()}")

# ============================================================
# 5. TICKER NORMALIZATION EDGE CASES
# ============================================================
print("\n" + "=" * 70)
print("TEST 5: Ticker normalization edge cases")
print("=" * 70)

# 5a: V00 -> VOO
try:
    result = ts.validate_or_raise("V00")
    record("'V00' normalizes to 'VOO'", result == "VOO", f"Got '{result}'")
except ValueError as e:
    record("'V00' normalizes to 'VOO'", False, f"ValueError: {e}")

# 5b: APPL -> AAPL
try:
    result = ts.validate_or_raise("APPL")
    record("'APPL' normalizes to 'AAPL'", result == "AAPL", f"Got '{result}'")
except ValueError as e:
    record("'APPL' normalizes to 'AAPL'", False, f"ValueError: {e}")

# 5c: "" raises ValueError
try:
    ts.validate_or_raise("")
    record("Empty string raises ValueError", False, "No exception raised")
except ValueError:
    record("Empty string raises ValueError", True)
except Exception as e:
    record("Empty string raises ValueError", False, f"Wrong exception: {type(e).__name__}: {e}")

# 5d: "123" raises ValueError (all digits)
try:
    ts.validate_or_raise("123")
    record("'123' raises ValueError (all digits)", False, "No exception raised")
except ValueError:
    record("'123' raises ValueError (all digits)", True)
except Exception as e:
    record("'123' raises ValueError (all digits)", False, f"Wrong exception: {type(e).__name__}: {e}")

# 5e: "O" remains "O" (Realty Income, NOT confused with 0)
try:
    result = ts.validate_or_raise("O")
    record("'O' remains 'O'", result == "O", f"Got '{result}'")
except ValueError as e:
    record("'O' remains 'O'", False, f"ValueError: {e}")

# 5f: "V" remains "V" (Visa)
try:
    result = ts.validate_or_raise("V")
    record("'V' remains 'V'", result == "V", f"Got '{result}'")
except ValueError as e:
    record("'V' remains 'V'", False, f"ValueError: {e}")

# 5g: "UL" remains "UL" (Unilever)
try:
    result = ts.validate_or_raise("UL")
    record("'UL' remains 'UL'", result == "UL", f"Got '{result}'")
except ValueError as e:
    record("'UL' remains 'UL'", False, f"ValueError: {e}")

# 5h: Verify VOO is NOT converted to V00
try:
    result = ts.validate_or_raise("VOO")
    record("'VOO' stays 'VOO' (not V00)", result == "VOO", f"Got '{result}'")
except ValueError as e:
    record("'VOO' stays 'VOO'", False, f"ValueError: {e}")

# 5i: Lowercase input normalizes correctly
try:
    result = ts.validate_or_raise("voO")
    record("'voO' normalizes to 'VOO'", result == "VOO", f"Got '{result}'")
except ValueError as e:
    record("'voO' normalizes to 'VOO'", False, f"ValueError: {e}")

# 5j: Prefix stripping
try:
    result = ts.validate_or_raise("$VOO")
    record("'$VOO' strips $ prefix, returns 'VOO'", result == "VOO", f"Got '{result}'")
except ValueError as e:
    record("'$VOO' strips $ prefix", False, f"ValueError: {e}")

try:
    result = ts.validate_or_raise("NYSE:V")
    record("'NYSE:V' strips prefix, returns 'V'", result == "V", f"Got '{result}'")
except ValueError as e:
    record("'NYSE:V' strips prefix", False, f"ValueError: {e}")

# 5k: Ticker too long
try:
    ts.validate_or_raise("TOOLONG")
    record("'TOOLONG' (7 chars) raises ValueError", False, "No exception raised")
except ValueError:
    record("'TOOLONG' (7 chars) raises ValueError", True)

# ============================================================
# 6. UTILITY MODULE PARITY CHECK
# ============================================================
print("\n" + "=" * 70)
print("TEST 6: app.utils.ticker parity with TickerService")
print("=" * 70)

parity_cases = [
    ("VOO", "VOO"), ("V00", "VOO"), ("APPL", "AAPL"), ("O", "O"),
    ("V", "V"), ("UL", "UL"), ("JNJ", "JNJ"), ("AAPL", "AAPL"),
]
all_parity = True
for raw, expected in parity_cases:
    util_result = util_normalize(raw)
    svc_result = ts.normalize(raw)
    match = (util_result == expected) and (svc_result == expected)
    record(f"normalize('{raw}') -> '{expected}' (utils={util_result}, svc={svc_result})",
           match)
    if not match:
        all_parity = False

record("All utility parity checks pass", all_parity)

# ============================================================
# SUMMARY
# ============================================================
print("\n" + "=" * 70)
print("FINAL RESULTS")
print("=" * 70)

total = len(results)
passed = sum(1 for _, s, _ in results if s == "PASS")
failed = sum(1 for _, s, _ in results if s == "FAIL")

print(f"\n  Total tests: {total}")
print(f"  PASSED:      {passed}")
print(f"  FAILED:      {failed}")
print(f"  Pass rate:   {passed/total*100:.1f}%")

if failed:
    print(f"\n  FAILED TESTS:")
    for name, status, detail in results:
        if status == "FAIL":
            print(f"    [FAIL] {name} — {detail}")
else:
    print(f"\n  ALL TESTS PASSED!")

print("\n" + "=" * 70)

if __name__ == "__main__":
    sys.exit(0 if failed == 0 else 1)
