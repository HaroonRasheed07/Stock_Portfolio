"""
Static stock directory: canonical company names + aliases for the most
commonly held US stocks/ETFs. Used as fallback evidence source when the
database has no cached company info (fresh installs, client machines).

This complements (never replaces) live yfinance data.
"""
from typing import Dict, Optional, List

# symbol -> (company_name, aliases)
_STOCK_DIRECTORY: Dict[str, Dict[str, any]] = {
    "AAPL": {"name": "Apple Inc.", "aliases": ["apple"]},
    "MSFT": {"name": "Microsoft Corporation", "aliases": ["microsoft"]},
    "AMZN": {"name": "Amazon.com", "aliases": ["amazon"]},
    "GOOGL": {"name": "Alphabet Inc.", "aliases": ["alphabet", "google"]},
    "GOOG": {"name": "Alphabet Inc.", "aliases": ["alphabet", "google"]},
    "META": {"name": "Meta Platforms", "aliases": ["meta platforms", "facebook"]},
    "NVDA": {"name": "NVIDIA Corporation", "aliases": ["nvidia"]},
    "TSLA": {"name": "Tesla, Inc.", "aliases": ["tesla"]},
    "BRK-B": {"name": "Berkshire Hathaway", "aliases": ["berkshire hathaway", "berkshire"]},
    "JPM": {"name": "JPMorgan Chase & Co.", "aliases": ["jpmorgan", "jp morgan", "jpmorgan chase"]},
    "V": {"name": "Visa Inc.", "aliases": ["visa inc", "visa"]},
    "UNH": {"name": "UnitedHealth Group", "aliases": ["unitedhealth", "united health group"]},
    "JNJ": {"name": "Johnson & Johnson", "aliases": ["johnson & johnson", "johnson and johnson", "j&j"]},
    "WMT": {"name": "Walmart Inc.", "aliases": ["walmart", "wal-mart"]},
    "PG": {"name": "Procter & Gamble", "aliases": ["procter & gamble", "procter and gamble", "p&g"]},
    "KO": {"name": "The Coca-Cola Company", "aliases": ["coca-cola", "coca cola", "coke"]},
    "PEP": {"name": "PepsiCo, Inc.", "aliases": ["pepsico", "pepsi"]},
    "COST": {"name": "Costco Wholesale Corporation", "aliases": ["costco"]},
    "HD": {"name": "The Home Depot", "aliases": ["home depot"]},
    "LOW": {"name": "Lowe's Companies", "aliases": ["lowe's", "lowes companies"]},
    "XOM": {"name": "Exxon Mobil Corporation", "aliases": ["exxon", "exxon mobil"]},
    "CVX": {"name": "Chevron Corporation", "aliases": ["chevron"]},
    "ABBV": {"name": "AbbVie Inc.", "aliases": ["abbvie"]},
    "MRK": {"name": "Merck & Co.", "aliases": ["merck"]},
    "PFE": {"name": "Pfizer Inc.", "aliases": ["pfizer"]},
    "LLY": {"name": "Eli Lilly and Company", "aliases": ["eli lilly", "lilly"]},
    "SBUX": {"name": "Starbucks Corporation", "aliases": ["starbucks"]},
    "MCD": {"name": "McDonald's Corporation", "aliases": ["mcdonald's", "mcdonalds"]},
    "NKE": {"name": "NIKE, Inc.", "aliases": ["nike"]},
    "DIS": {"name": "The Walt Disney Company", "aliases": ["disney", "walt disney"]},
    "INTC": {"name": "Intel Corporation", "aliases": ["intel"]},
    "CSCO": {"name": "Cisco Systems", "aliases": ["cisco"]},
    "ORCL": {"name": "Oracle Corporation", "aliases": ["oracle"]},
    "CRM": {"name": "Salesforce, Inc.", "aliases": ["salesforce"]},
    "AMD": {"name": "Advanced Micro Devices", "aliases": ["amd", "advanced micro devices"]},
    "QCOM": {"name": "QUALCOMM Incorporated", "aliases": ["qualcomm"]},
    "TXN": {"name": "Texas Instruments", "aliases": ["texas instruments"]},
    "UNP": {"name": "Union Pacific Corporation", "aliases": ["union pacific"]},
    "BA": {"name": "The Boeing Company", "aliases": ["boeing"]},
    "CAT": {"name": "Caterpillar Inc.", "aliases": ["caterpillar"]},
    "GE": {"name": "General Electric", "aliases": ["general electric"]},
    "MMM": {"name": "3M Company", "aliases": ["3m"]},
    "HON": {"name": "Honeywell International", "aliases": ["honeywell"]},
    "UPS": {"name": "United Parcel Service", "aliases": ["ups", "united parcel service"]},
    "RTX": {"name": "RTX Corporation", "aliases": ["rtx", "raytheon"]},
    "SPG": {"name": "Simon Property Group", "aliases": ["simon property"]},
    "PLD": {"name": "Prologis, Inc.", "aliases": ["prologis"]},
    "AMT": {"name": "American Tower Corporation", "aliases": ["american tower"]},
    "CCI": {"name": "Crown Castle Inc.", "aliases": ["crown castle"]},
    "O": {"name": "Realty Income Corporation", "aliases": ["realty income"]},
    "OHI": {"name": "Omega Healthcare Investors", "aliases": ["omega healthcare"]},
    "VICI": {"name": "VICI Properties", "aliases": ["vici properties", "vici"]},
    "MAIN": {"name": "Main Street Capital", "aliases": ["main street capital"]},
    "SNA": {"name": "Snap-on Incorporated", "aliases": ["snap-on", "snap on"]},
    "KMB": {"name": "Kimberly-Clark Corporation", "aliases": ["kimberly-clark", "kimberly clark"]},
    "CL": {"name": "Colgate-Palmolive", "aliases": ["colgate", "colgate-palmolive"]},
    "MO": {"name": "Altria Group", "aliases": ["altria"]},
    "PM": {"name": "Philip Morris International", "aliases": ["philip morris"]},
    "T": {"name": "AT&T Inc.", "aliases": ["at&t", "at t"]},
    "VZ": {"name": "Verizon Communications", "aliases": ["verizon"]},
    "DHI": {"name": "D.R. Horton", "aliases": ["d.r. horton", "dr horton", "d r horton"]},
    "AGCO": {"name": "AGCO Corporation", "aliases": ["agco"]},
    "DE": {"name": "Deere & Company", "aliases": ["deere", "john deere"]},
    "UL": {"name": "Unilever PLC", "aliases": ["unilever"]},
    "VYM": {"name": "Vanguard High Dividend Yield ETF", "aliases": ["vanguard high dividend", "high dividend yield etf"]},
    "MICC": {"name": "Millicom International Cellular", "aliases": ["millicom"]},
    # ETFs
    "VOO": {"name": "Vanguard S&P 500 ETF", "aliases": ["vanguard s&p 500", "vanguard 500"]},
    "VTI": {"name": "Vanguard Total Stock Market ETF", "aliases": ["vanguard total stock market", "total stock market etf"]},
    "SPY": {"name": "SPDR S&P 500 ETF Trust", "aliases": ["spdr s&p 500", "s&p 500 etf"]},
    "QQQ": {"name": "Invesco QQQ Trust", "aliases": ["invesco qqq", "nasdaq 100 etf"]},
    "IVV": {"name": "iShares Core S&P 500 ETF", "aliases": ["ishares core s&p 500", "ishares s&p 500"]},
    "SCHD": {"name": "Schwab US Dividend Equity ETF", "aliases": ["schwab dividend", "schwab us dividend equity"]},
    "SCHF": {"name": "Schwab International Equity ETF", "aliases": ["schwab international equity"]},
    "VXUS": {"name": "Vanguard Total International Stock ETF", "aliases": ["vanguard total international"]},
    "BND": {"name": "Vanguard Total Bond Market ETF", "aliases": ["vanguard total bond market"]},
    "AGG": {"name": "iShares Core U.S. Aggregate Bond ETF", "aliases": ["ishares aggregate bond"]},
}


def lookup_company_name(symbol: str) -> Optional[str]:
    """Canonical company name for a ticker, or None."""
    entry = _STOCK_DIRECTORY.get(symbol.strip().upper())
    return entry["name"] if entry else None


def lookup_aliases(symbol: str) -> List[str]:
    """Search aliases for a ticker."""
    entry = _STOCK_DIRECTORY.get(symbol.strip().upper())
    return list(entry["aliases"]) if entry else []


def known_symbols() -> List[str]:
    return list(_STOCK_DIRECTORY.keys())