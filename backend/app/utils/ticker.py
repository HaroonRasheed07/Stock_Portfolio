"""
Ticker normalization and validation utilities.
Prevents V00/VOO type OCR errors and validates tickers before provider calls.
"""
import re
from typing import Optional, Tuple

# Known ticker corrections for common OCR-like errors
# Maps likely-intended tickers to their canonical form
_TICKER_CORRECTIONS = {
    "V00": "VOO",  # V + two zeros → V + two letter O's
    "V0O": "VOO",
    "VOO": "VOO",
    "SCH5": "SCHF",
    "SPY": "SPY",
    "QQQ": "QQQ",
    "VTI": "VTI",
    "IVV": "IVV",
    "VO": "VO",
    "VF0": "VFI",
    "VT0": "VTV",
    "JPM": "JPM",
    "CSC0": "CSCO",
    "CSCO": "CSCO",
    "MSFT": "MSFT",
    "APPL": "AAPL",  # Common typo
    "AAPL": "AAPL",
    "UNH": "UNH",
    "JNJ": "JNJ",
    "V": "V",
    "O": "O",
    "ABBV": "ABBV",
    "SBUX": "SBUX",
    "KMB": "KMB",
    "TXN": "TXN",
    "LOW": "LOW",
    "AMT": "AMT",
    "SNA": "SNA",
    "COST": "COST",
    "PEP": "PEP",
    "OHI": "OHI",
    "MAIN": "MAIN",
    "DHI": "DHI",
    "AGCO": "AGCO",
    "MICC": "MICC",
    "UL": "UL",
}

# Valid US stock ticker pattern: 1-5 uppercase letters (NYSE/NASDAQ)
_TICKER_PATTERN = re.compile(r"^[A-Z]{1,5}$")


def normalize_ticker(raw: str) -> str:
    """
    Normalize a raw ticker string:
    - Strip whitespace
    - Uppercase
    - Apply known corrections for OCR-like errors
    - Return canonical form
    """
    if not raw:
        return ""
    cleaned = raw.strip().upper()
    # Remove common prefixes that get accidentally included
    for prefix in ["$", "NYSE:", "NASDAQ:", "AMEX:"]:
        if cleaned.startswith(prefix):
            cleaned = cleaned[len(prefix):]
    # Apply known corrections
    if cleaned in _TICKER_CORRECTIONS:
        return _TICKER_CORRECTIONS[cleaned]
    return cleaned


def validate_ticker(ticker: str) -> Tuple[bool, str, str]:
    """
    Validate a ticker symbol.
    Returns (is_valid, canonical_ticker, error_message).
    """
    if not ticker or not ticker.strip():
        return False, "", "Ticker cannot be empty."
    
    normalized = normalize_ticker(ticker)
    
    if not _TICKER_PATTERN.match(normalized):
        # Could be a valid ETF with digits (e.g., SPY1, QQQ2)
        # Allow 1-5 alphanumeric chars
        if not re.match(r"^[A-Z0-9]{1,5}$", normalized):
            return False, normalized, f"Invalid ticker format: '{normalized}'. Tickers are 1-5 alphanumeric characters."
    
    # Check for obviously wrong patterns
    if len(normalized) > 5:
        return False, normalized, f"Ticker too long: '{normalized}'. US tickers are 1-5 characters."
    
    # All zeros or special chars
    if all(c in "0123456789" for c in normalized):
        return False, normalized, f"Invalid ticker: '{normalized}'. Tickers must contain letters."
    
    return True, normalized, ""


def is_valid_ticker_format(ticker: str) -> bool:
    """Quick check if a string looks like a valid ticker format."""
    if not ticker:
        return False
    normalized = normalize_ticker(ticker)
    return bool(re.match(r"^[A-Z0-9]{1,5}$", normalized))
