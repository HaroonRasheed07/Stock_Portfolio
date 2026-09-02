"""Comprehensive test suite for recommendation engine, backtesting, and portfolio health."""
import sys
sys.path.insert(0, '.')

import asyncio
import traceback

results = {}

# ─── TEST 1: Anti-panic-sell — single negative factor should NOT produce SELL ───
print("=" * 70)
print("TEST 1: Anti-panic-sell — single negative factor should NOT produce SELL")
print("=" * 70)
try:
    from app.engines.recommendation import RecommendationEngine
    engine = RecommendationEngine()
    rec = engine.recommend(
        symbol="TEST",
        fundamental_data={"score": 75, "metrics": {"pe_ratio": 20}},
        technical_data={"trend": "Downtrend", "trend_strength": 60, "momentum": "Bearish"},
        risk_data={"risk_score": 55},
        sentiment_data={"overall_score": -0.3, "overall_sentiment": "Negative"},
        risk_profile="moderate",
    )
    print(f"  Recommendation: {rec['recommendation']}")
    print(f"  Confidence: {rec['confidence']}")
    print(f"  Anti-panic note: {rec.get('anti_panic_note')}")
    print(f"  Negative factors: {rec['negative_factors']}")
    print(f"  Positive factors: {rec['positive_factors']}")
    
    assert rec['recommendation'] != 'SELL', f"FAIL: Single negative factor produced SELL"
    assert rec['recommendation'] in ('HOLD', 'WATCH', 'REDUCE'), f"FAIL: Expected HOLD/WATCH/REDUCE, got {rec['recommendation']}"
    print("  >> PASS")
    results['test1'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test1'] = f'FAIL: {e}'

# ─── TEST 2: Multi-factor SELL requires fundamental deterioration ───
print()
print("=" * 70)
print("TEST 2: Multi-factor SELL requires fundamental deterioration")
print("=" * 70)
try:
    rec2 = engine.recommend(
        symbol="TEST2",
        fundamental_data={"score": 20, "metrics": {"pe_ratio": 80}},
        technical_data={"trend": "Strong Downtrend", "trend_strength": 90, "momentum": "Bearish"},
        risk_data={"risk_score": 85},
        sentiment_data={"overall_score": -0.8, "overall_sentiment": "Negative"},
        catalyst_data={"catalysts": [{"title": "Earnings miss", "sentiment": "negative"}]},
        risk_profile="moderate",
    )
    print(f"  Multi-factor recommendation: {rec2['recommendation']}")
    print(f"  Score: {rec2.get('score')}")
    print(f"  Positive factors: {rec2['positive_factors']}")
    print(f"  Negative factors: {rec2['negative_factors']}")
    
    assert rec2['recommendation'] in ('REDUCE', 'SELL'), f"FAIL: Multi-factor deterioration should produce REDUCE/SELL, got {rec2['recommendation']}"
    print("  >> PASS")
    results['test2'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test2'] = f'FAIL: {e}'

# ─── TEST 3: TAKE PROFIT for high gain + overweight ───
print()
print("=" * 70)
print("TEST 3: TAKE PROFIT for high gain + overweight")
print("=" * 70)
try:
    rec3 = engine.recommend(
        symbol="TEST3",
        fundamental_data={"score": 85, "metrics": {"pe_ratio": 18}},
        technical_data={"trend": "Strong Uptrend", "trend_strength": 85, "momentum": "Bullish"},
        risk_data={"risk_score": 25},
        sentiment_data={"overall_score": 0.6, "overall_sentiment": "Positive"},
        portfolio_allocation=12,
        unrealized_gain_pct=120,
        risk_profile="conservative",
    )
    print(f"  Take profit recommendation: {rec3['recommendation']}")
    print(f"  Reasons: {rec3['reasons']}")
    print(f"  Score: {rec3.get('score')}")
    
    # For conservative profile, gain>100 + alloc>10 should be TAKE PROFIT
    assert rec3['recommendation'] == 'TAKE PROFIT', f"FAIL: Expected TAKE PROFIT, got {rec3['recommendation']}"
    print("  >> PASS")
    results['test3'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test3'] = f'FAIL: {e}'

# ─── TEST 4: Insufficient data returns WATCH ───
print()
print("=" * 70)
print("TEST 4: Insufficient data returns WATCH")
print("=" * 70)
try:
    rec4 = engine.recommend(symbol="TEST4", risk_profile="moderate")
    print(f"  Insufficient data recommendation: {rec4['recommendation']}")
    print(f"  Confidence: {rec4['confidence']}")
    
    assert rec4['recommendation'] == 'WATCH', f"FAIL: Insufficient data should return WATCH, got {rec4['recommendation']}"
    print("  >> PASS")
    results['test4'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test4'] = f'FAIL: {e}'

# ─── TEST 5: Backtest with valid ticker ───
print()
print("=" * 70)
print("TEST 5: Backtest with valid ticker (AAPL, 2y)")
print("=" * 70)
try:
    from app.services.backtest_service import BacktestService
    from app.services.stock_service import StockService
    from app.database import SessionLocal

    db = SessionLocal()
    ss = StockService(db)
    hist = asyncio.run(ss.get_historical_prices("AAPL", period="2y"))
    print(f"  Historical data points: {len(hist)}")
    
    bt = BacktestService()
    result = bt.run_backtest(hist, strategy="sma_crossover", initial_capital=10000)
    print(f"  Backtest result - Profit/Loss: ${result.get('profit_loss', 'N/A')}")
    print(f"  Return: {result.get('total_return', 'N/A')}%")
    print(f"  Trades: {result.get('num_trades', 'N/A')}")
    print(f"  Profit/Loss: ${result.get('profit_loss', 'N/A')}")
    print(f"  Win rate: {result.get('win_rate', 'N/A')}%")
    print(f"  Max drawdown: {result.get('max_drawdown', 'N/A')}%")
    print(f"  Assumptions: {result.get('assumptions', [])}")
    
    assert result.get('total_return') is not None, "FAIL: Backtest should return total_return"
    assert result.get('num_trades') is not None, "FAIL: Backtest should return num_trades"
    print("  >> PASS")
    results['test5'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test5'] = f'FAIL: {e}'

# ─── TEST 6: Backtest with insufficient data ───
print()
print("=" * 70)
print("TEST 6: Backtest with insufficient data (5d)")
print("=" * 70)
try:
    short_hist = asyncio.run(ss.get_historical_prices("AAPL", period="5d"))
    print(f"  Short historical data points: {len(short_hist)}")
    result2 = bt.run_backtest(short_hist, strategy="sma_crossover", initial_capital=10000)
    print(f"  Short backtest result: {result2}")
    print(f"  num_trades: {result2.get('num_trades')}")
    print(f"  assumptions: {result2.get('assumptions')}")
    
    assert result2.get('num_trades') == 0, f"FAIL: Short backtest should have 0 trades, got {result2.get('num_trades')}"
    assert len(result2.get('assumptions', [])) > 0, "FAIL: Should have assumptions about insufficient data"
    print("  >> PASS")
    results['test6'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test6'] = f'FAIL: {e}'

# ─── TEST 7: Portfolio health report ───
print()
print("=" * 70)
print("TEST 7: Portfolio health report")
print("=" * 70)
try:
    from app.services.analysis_service import AnalysisService
    service = AnalysisService(db)
    health = asyncio.run(service.get_portfolio_health_report())
    print(f"  Health score: {health.get('overall_score')}")
    print(f"  Grade: {health.get('grade')}")
    print(f"  Strengths: {len(health.get('strengths', []))}")
    print(f"  Risks: {len(health.get('risks', []))}")
    print(f"  Actions: {len(health.get('actions', []))}")
    wsid = health.get('what_should_i_do', {})
    print(f"  What should I do: {wsid.get('summary', 'N/A')[:100]}")
    print(f"  Data quality: {health.get('data_quality', {}).get('message')}")
    print(f"  Score breakdown: {health.get('score_breakdown')}")
    
    assert health.get('overall_score') is not None, "FAIL: Health score should exist"
    assert health.get('grade') is not None, "FAIL: Grade should exist"
    assert health.get('what_should_i_do') is not None, "FAIL: What should I do section should exist"
    print("  >> PASS")
    results['test7'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test7'] = f'FAIL: {e}'

# ─── TEST 8: Rebalancing ───
print()
print("=" * 70)
print("TEST 8: Rebalancing")
print("=" * 70)
try:
    from app.engines.rebalancing import RebalancingEngine
    from app.services.portfolio_service import PortfolioService
    ps = PortfolioService(db)
    holdings = ps.get_holdings()
    print(f"  Holdings count: {len(holdings)}")
    for h in holdings[:5]:
        print(f"    {h['symbol']}: ${h.get('current_value', 0):,.2f} ({h.get('allocation_pct', 0):.1f}%)")
    
    re = RebalancingEngine()
    rebal = re.analyze(holdings)
    print(f"  Rebalancing score: {rebal.get('rebalancing_score')}")
    print(f"  Suggestions: {len(rebal.get('suggestions', []))}")
    print(f"  Summary: {rebal.get('summary', '')[:150]}")
    print(f"  Total positions: {rebal.get('total_positions')}")
    print(f"  Total value: ${rebal.get('total_portfolio_value', 0):,.2f}")
    
    assert rebal.get('rebalancing_score') is not None, "FAIL: Rebalancing score should exist"
    assert len(rebal.get('suggestions', [])) > 0, "FAIL: Should have rebalancing suggestions"
    print("  >> PASS")
    results['test8'] = 'PASS'
except Exception as e:
    print(f"  >> FAIL: {e}")
    traceback.print_exc()
    results['test8'] = f'FAIL: {e}'

db.close()

# ─── SUMMARY ───
print()
print("=" * 70)
print("TEST RESULTS SUMMARY")
print("=" * 70)
all_pass = True
for test, result in results.items():
    status = "PASS" if result == "PASS" else "FAIL"
    print(f"  {test}: {status}" + (f" ({result})" if result != "PASS" else ""))
    if result != "PASS":
        all_pass = False

print()
if all_pass:
    print("ALL 8 TESTS PASSED")
else:
    print("SOME TESTS FAILED — see details above")
