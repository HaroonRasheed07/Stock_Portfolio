import sqlite3
con = sqlite3.connect("data/portfolio.db")
cur = con.cursor()
tables = [r[0] for r in cur.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
print("TABLES:", tables)
for t in ("holdings", "portfolios", "portfolio_snapshots", "watchlist_items", "alerts", "user_settings", "catalyst_events", "catalyst_alerts"):
    if t in tables:
        print(t, "->", cur.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0])
if "holdings" in tables:
    for row in cur.execute("SELECT symbol, quantity, current_value FROM holdings LIMIT 30").fetchall():
        print(row)
con.close()
