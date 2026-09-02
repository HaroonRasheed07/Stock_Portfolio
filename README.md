# Stock Portfolio Intelligence Platform


### Before You Start — Install 2 Free Programs

**Python** (one-time setup, 2 minutes):
1. Go to **https://www.python.org/downloads/**
2. Click the big yellow **"Download Python 3.x.x"** button
3. Run the downloaded file
4. **CHECK THIS BOX** at the bottom: "Add Python to PATH" (very important!)
5. Click **"Install Now"**

**Node.js** (one-time setup, 2 minutes):
1. Go to **https://nodejs.org/**
2. Click the green **"LTS"** download button
3. Run the downloaded file, click **"Next"** through everything (accept all defaults)

### Launch the Application

1. Double-click **`start.bat`** in this folder
2. Wait for the message **"ALL DONE!"** (first time takes 3-5 minutes while it installs packages)
3. Your browser will open automatically

### Upload Your Portfolio

1. Click **"Upload Portfolio CSV"** (top-right corner of the dashboard)
2. Select your brokerage CSV file (e.g., your Holdings export)
3. Click **"Parse & Preview"** to check the data looks right
4. Click **"Confirm Import"** to save
5. Click **"Refresh Live Prices"** on the dashboard to get live prices

**That's it!** The application will show your portfolio value, risk analysis, news catalysts, and stock recommendations.

### To Stop

Close both command windows, or double-click **`stop.bat`**.

### To Start Again

Double-click **`start.bat`** any time.

---

## What You Get

| Feature | Description |
|---------|-------------|
| **Dashboard** | Total portfolio value, gains/losses, sector breakdown, risk status |
| **Holdings** | All positions with live prices and gain/loss |
| **Stock Analysis** | Click any stock for fundamentals, technicals, AI recommendation |
| **News & Catalysts** | Market news ranked by impact (Critical / High / Medium / Low) |
| **Catalyst Watch** | Early-warning signals for your holdings |
| **Trading Setups** | Detected swing trade opportunities |
| **Health Report** | Portfolio health score with actionable insights |
| **Risk Analysis** | Volatility, concentration, correlation, beta analysis |

## CSV Format

Your CSV file needs these columns (order does not matter):

| Column | Example |
|--------|---------|
| Symbol | AAPL |
| Name | Apple Inc. |
| Quantity | 100 |
| Avg. Price | 150.00 |
| Cost Basis | 15000.00 |
| Value | 19500.00 |

Column names are auto-detected, so minor naming differences are fine.

## Troubleshooting

| Problem | Solution |
|---------|----------|
| "Python is not installed" | Reinstall from python.org, **check "Add Python to PATH"** |
| "Node.js is not installed" | Reinstall from nodejs.org |
| First load is slow | Normal! First launch installs packages (3-5 min) |
| Port already in use | Run `stop.bat` first, then `start.bat` |
| Prices not loading | Click "Refresh Live Prices" on dashboard |

## Data & Cost

- **Stock prices**: Yahoo Finance (free)
- **News & catalysts**: RSS feeds + Yahoo Finance (free)
- **Fundamentals**: Yahoo Finance (free)
- **No paid API keys required** — works 100% free
