"""
Centralized Ticker Normalization & Validation Service.

ALL provider calls MUST pass through this service.
NO raw user ticker should ever reach yfinance/provider code directly.

This is the SINGLE SOURCE OF TRUTH for ticker normalization.
"""
import re
import logging
from typing import Optional, Tuple, Set, Dict, List
from functools import lru_cache

from app.utils.ticker import normalize_ticker as _normalize_ticker, validate_ticker as _validate_ticker

logger = logging.getLogger(__name__)

# Known ticker corrections - SINGLE SOURCE OF TRUTH
# Maps likely-intended tickers to their canonical form
# Only explicit, verified mappings - NO blind O->0 or 0->O replacements
_TICKER_CORRECTIONS: Dict[str, str] = {
    # V00/VOO family - common OCR errors
    "V00": "VOO",
    "V0O": "VOO",
    "V0V": "VOO",
    # CSCO family
    "CSC0": "CSCO",
    "C5CO": "CSCO",
    # Microsoft
    "MSF": "MSFT",
    "MCR0": "MSFT",
    # Apple
    "AAP1": "AAPL",
    "APPL": "AAPL",
    # Common ETFs
    "SPY": "SPY",
    "QQQ": "QQQ",
    "VTI": "VTI",
    "IVV": "IVV",
    "VO": "VO",
    "VF0": "VFI",
    "VT0": "VTV",
    # Common stocks
    "JPM": "JPM",
    "UNH": "UNH",
    "JNJ": "JNJ",
    "V": "V",
    "O": "O",  # Realty Income - DO NOT confuse with Walmart (WMT)
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
    # WMT (Walmart) - ensure NOT mapped to O
    "WMT": "WMT",
    "WAL": "WMT",
}

# Valid US ticker pattern: 1-5 alphanumeric chars (NYSE/NASDAQ)
# Allows ETFs with digits like SPY1, QQQ2
_TICKER_PATTERN = re.compile(r"^[A-Z0-9]{1,5}$")


class TickerService:
    """
    Centralized ticker normalization and validation.
    
    Usage:
        ticker_service = TickerService()
        canonical = ticker_service.normalize("V00")  # Returns "VOO"
        is_valid, canonical, error = ticker_service.validate("V00")  # (True, "VOO", "")
    """
    
    def __init__(self):
        self._corrections = _TICKER_CORRECTIONS.copy()
        self._validation_cache: Dict[str, Tuple[bool, str, str]] = {}
    
    def normalize(self, raw: str) -> str:
        """
        Normalize a raw ticker string to canonical form.
        
        - Strips whitespace
        - Uppercases
        - Removes common prefixes ($, NYSE:, NASDAQ:, AMEX:)
        - Applies known corrections
        - Returns canonical form
        
        NEVER blindly replaces O<->0. Only uses explicit mappings.
        """
        if not raw:
            return ""
        cleaned = raw.strip().upper()
        
        # Remove common prefixes that get accidentally included
        for prefix in ["$", "NYSE:", "NASDAQ:", "AMEX:"]:
            if cleaned.startswith(prefix):
                cleaned = cleaned[len(prefix):]
        
        # Apply known corrections
        if cleaned in self._corrections:
            corrected = self._corrections[cleaned]
            if corrected != cleaned:
                logger.info(f"Ticker normalized: {cleaned} -> {corrected}")
            return corrected
        
        return cleaned
    
    def validate(self, ticker: str) -> Tuple[bool, str, str]:
        """
        Validate a ticker symbol.
        
        Returns (is_valid, canonical_ticker, error_message).
        
        This MUST be called before ANY provider call.
        """
        if not ticker or not ticker.strip():
            return False, "", "Ticker cannot be empty."
        
        # Check cache
        cache_key = ticker.strip().upper()
        if cache_key in self._validation_cache:
            return self._validation_cache[cache_key]
        
        normalized = self.normalize(ticker)
        
        if not _TICKER_PATTERN.match(normalized):
            result = (False, normalized, f"Invalid ticker format: '{normalized}'. Tickers are 1-5 alphanumeric characters.")
            self._validation_cache[cache_key] = result
            return result
        
        # Check for obviously wrong patterns
        if len(normalized) > 5:
            result = (False, normalized, f"Ticker too long: '{normalized}'. US tickers are 1-5 characters.")
            self._validation_cache[cache_key] = result
            return result
        
        # All digits is invalid
        if all(c in "0123456789" for c in normalized):
            result = (False, normalized, f"Invalid ticker: '{normalized}'. Tickers must contain letters.")
            self._validation_cache[cache_key] = result
            return result
        
        result = (True, normalized, "")
        self._validation_cache[cache_key] = result
        return result
    
    def validate_or_raise(self, ticker: str) -> str:
        """
        Validate ticker and return canonical form.
        Raises ValueError if invalid.
        """
        is_valid, canonical, error = self.validate(ticker)
        if not is_valid:
            raise ValueError(error)
        return canonical
    
    def is_valid_format(self, ticker: str) -> bool:
        """Quick check if a string looks like a valid ticker format."""
        if not ticker:
            return False
        normalized = self.normalize(ticker)
        return bool(_TICKER_PATTERN.match(normalized))
    
    def normalize_batch(self, tickers: List[str]) -> List[str]:
        """Normalize a batch of tickers."""
        return [self.normalize(t) for t in tickers]
    
    def validate_batch(self, tickers: List[str]) -> Dict[str, Tuple[bool, str, str]]:
        """Validate a batch of tickers. Returns {original: (is_valid, canonical, error)}."""
        results = {}
        for t in tickers:
            results[t] = self.validate(t)
        return results
    
    def get_corrections(self) -> Dict[str, str]:
        """Get all known ticker corrections (for testing/debugging)."""
        return self._corrections.copy()
    
    def add_correction(self, raw: str, canonical: str):
        """Add a new ticker correction (for runtime additions)."""
        raw_upper = raw.strip().upper()
        canonical_upper = canonical.strip().upper()
        self._corrections[raw_upper] = canonical_upper
        # Invalidate cache
        self._validation_cache.clear()
        logger.info(f"Added ticker correction: {raw_upper} -> {canonical_upper}")


# Global singleton instance
_ticker_service: Optional[TickerService] = None


def get_ticker_service() -> TickerService:
    """Get or create the global TickerService singleton."""
    global _ticker_service
    if _ticker_service is None:
        _ticker_service = TickerService()
    return _ticker_service


# Convenience functions for direct use
def normalize_ticker(raw: str) -> str:
    """Normalize ticker using global service."""
    return get_ticker_service().normalize(raw)


def validate_ticker(ticker: str) -> Tuple[bool, str, str]:
    """Validate ticker using global service."""
    return get_ticker_service().validate(ticker)


def validate_ticker_or_raise(ticker: str) -> str:
    """Validate ticker or raise ValueError."""
    return get_ticker_service().validate_or_raise(ticker)


# Re-export the utility functions for backward compatibility
# These now use the centralized service
def normalize_ticker_legacy(raw: str) -> str:
    """Legacy wrapper - uses centralized service."""
    return normalize_ticker(raw)


def validate_ticker_legacy(ticker: str) -> Tuple[bool, str, str]:
    """Legacy wrapper - uses centralized service."""
    return validate_ticker(ticker)