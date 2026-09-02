import sys
sys.path.insert(0, '.')

from app.services.news_relevance_service import NewsRelevanceService

results = []

def test(name, passed, detail=""):
    status = "PASS" if passed else "FAIL"
    results.append((name, passed, detail))
    print(f"[{status}] {name}")
    if detail:
        print(f"       {detail}")

# --- Test 1: Service creation ---
nrs = NewsRelevanceService()
test("Service instantiation", nrs is not None, "NewsRelevanceService created")

# --- Test 2: Walmart article should NOT map to O (Realty Income) ---
walmart_article = {
    "title": "Walmart reports strong Q2 earnings, raises full-year guidance",
    "text": "Walmart Inc reported better-than-expected quarterly results...",
    "source": "Reuters"
}
universe = {
    "O": {"name": "Realty Income Corporation"},
    "WMT": {"name": "Walmart Inc"},
    "VOO": {"name": "Vanguard S&P 500 ETF"},
}
resolved = nrs.resolve_universe([walmart_article], universe)
o_articles = resolved.get("O", [])
wmt_articles = resolved.get("WMT", [])
print(f"  O articles: {len(o_articles)}, WMT articles: {len(wmt_articles)}")
test(
    "Walmart article must NOT map to O",
    len(o_articles) == 0,
    f"O={len(o_articles)} (expected 0)"
)
test(
    "Walmart article SHOULD map to WMT",
    len(wmt_articles) > 0,
    f"WMT={len(wmt_articles)} (expected >0)"
)

# --- Test 3: MSFT news should NOT map to AAPL ---
msft_article = {
    "title": "Microsoft Azure revenue grows 29% in Q2",
    "text": "Microsoft Corporation announced strong cloud growth...",
    "source": "CNBC"
}
universe2 = {
    "MSFT": {"name": "Microsoft Corporation"},
    "AAPL": {"name": "Apple Inc"},
}
resolved2 = nrs.resolve_universe([msft_article], universe2)
msft_count = len(resolved2.get("MSFT", []))
aapl_count = len(resolved2.get("AAPL", []))
print(f"  MSFT articles: {msft_count}, AAPL articles: {aapl_count}")
test(
    "MSFT news maps to MSFT",
    msft_count > 0,
    f"MSFT={msft_count} (expected >0)"
)
test(
    "MSFT news must NOT map to AAPL",
    aapl_count == 0,
    f"AAPL={aapl_count} (expected 0)"
)

# --- Test 4: Short ticker O requires explicit evidence ---
o_article = {
    "title": "Realty Income Corporation increases monthly dividend",
    "text": "Realty Income (NYSE: O) announced a dividend increase...",
    "source": "SeekingAlpha"
}
universe3 = {
    "O": {"name": "Realty Income Corporation"},
}
resolved3 = nrs.resolve_universe([o_article], universe3)
o_count = len(resolved3.get("O", []))
print(f"  O articles: {o_count}")
test(
    "O dividend article maps to O (explicit NYSE:O reference)",
    o_count > 0,
    f"O={o_count} (expected >0)"
)

# --- Test 5: Market-wide article without entity evidence ---
market_article = {
    "title": "Federal Reserve signals potential rate cut in September",
    "text": "Markets rallied on the news of potential monetary policy easing...",
    "source": "Bloomberg"
}
universe4 = {
    "VOO": {"name": "Vanguard S&P 500 ETF"},
    "JPM": {"name": "JPMorgan Chase"},
}
resolved4 = nrs.resolve_universe([market_article], universe4)
unassigned = resolved4.get("_unassigned", [])
print(f"  Unassigned articles: {len(unassigned)}")
for sym in ["VOO", "JPM"]:
    arts = resolved4.get(sym, [])
    print(f"  {sym} articles: {len(arts)}")
test(
    "Market-wide article is unassigned",
    len(unassigned) > 0,
    f"unassigned={len(unassigned)} (expected >0)"
)
test(
    "Market-wide article NOT attributed to VOO",
    len(resolved4.get("VOO", [])) == 0,
    f"VOO={len(resolved4.get('VOO', []))} (expected 0)"
)
test(
    "Market-wide article NOT attributed to JPM",
    len(resolved4.get("JPM", [])) == 0,
    f"JPM={len(resolved4.get('JPM', []))} (expected 0)"
)

# --- Test 6: UL (Unilever) news should not match generic "ul" substring ---
ul_article = {
    "title": "Unilever plc reports strong half-year results",
    "text": "Unilever announced revenue growth across all segments...",
    "source": "FT"
}
universe5 = {
    "UL": {"name": "Unilever plc"},
    "O": {"name": "Realty Income Corporation"},
}
resolved5 = nrs.resolve_universe([ul_article], universe5)
ul_count = len(resolved5.get("UL", []))
o_count2 = len(resolved5.get("O", []))
print(f"  UL articles: {ul_count}, O articles: {o_count2}")
test(
    "Unilever news maps to UL",
    ul_count > 0,
    f"UL={ul_count} (expected >0)"
)
test(
    "Unilever news must NOT map to O",
    o_count2 == 0,
    f"O={o_count2} (expected 0)"
)

# --- Summary ---
print("\n" + "=" * 60)
passed = sum(1 for _, p, _ in results if p)
total = len(results)
print(f"RESULTS: {passed}/{total} passed")
if passed == total:
    print("ALL TESTS PASSED")
else:
    print("FAILURES:")
    for name, p, detail in results:
        if not p:
            print(f"  FAIL: {name} -- {detail}")
print("=" * 60)
