"""
Flexible CSV parser for brokerage portfolio exports.
Handles various column naming conventions, number formats, and data quality issues.
"""
import csv
import io
import re
import logging
from typing import List, Dict, Optional, Tuple, Any
from difflib import SequenceMatcher

logger = logging.getLogger(__name__)

# Column aliases for fuzzy matching
COLUMN_ALIASES = {
    "symbol": [
        "symbol", "ticker", "stock", "security", "sym", "stock symbol",
        "ticker symbol", "securities", "instrument",
    ],
    "name": [
        "name", "description", "company", "security name", "company name",
        "stock name", "instrument name", "long name", "holding",
    ],
    "quantity": [
        "quantity", "qty", "shares", "units", "amount", "number of shares",
        "share quantity", "position", "holdings",
    ],
    "avg_price": [
        "avg. price", "avg price", "average price", "cost per share",
        "purchase price", "avg cost", "average cost", "price paid",
        "unit cost", "cost/share",
    ],
    "cost_basis": [
        "cost basis", "total cost", "cost", "book value", "book cost",
        "purchase value", "invested", "investment", "original value",
    ],
    "current_value": [
        "value", "market value", "current value", "total value",
        "market val", "current market value", "mv", "worth",
    ],
    "unrealized_gain": [
        "unrealized gain ($)", "unrealized gain", "gain/loss", "p&l",
        "unrealized p/l", "gain", "profit/loss", "unrealized",
        "gain loss", "unrealized gain/loss",
    ],
    "unrealized_gain_pct": [
        "unrealized gain (%)", "unrealized gain %", "gain/loss %",
        "return %", "return", "% gain", "% change", "pct change",
        "gain %", "gain/loss pct",
    ],
}


def _similarity(a: str, b: str) -> float:
    """Calculate string similarity ratio."""
    return SequenceMatcher(None, a.lower().strip(), b.lower().strip()).ratio()


def _clean_number(value: str) -> Optional[float]:
    """Parse a number from various formats: '$1,234.56', '(1,234.56)', '-1234.56'."""
    if not value or not isinstance(value, str):
        return None
    # Remove whitespace
    value = value.strip()
    if not value or value in ("-", "--", "N/A", "n/a", "NA", ""):
        return None

    # Check for negative in parentheses: (1,234.56) -> -1234.56
    is_negative = False
    if value.startswith("(") and value.endswith(")"):
        is_negative = True
        value = value[1:-1]

    # Remove currency symbols and whitespace
    value = re.sub(r'[$€£¥]', '', value).strip()
    # Remove commas and quotes
    value = value.replace(",", "").replace('"', "").replace("'", "")
    # Handle percentage sign
    value = value.replace("%", "").strip()

    if not value:
        return None

    try:
        result = float(value)
        return -result if is_negative else result
    except ValueError:
        return None


def detect_delimiter(content: str) -> str:
    """Detect CSV delimiter from file content."""
    sniffer = csv.Sniffer()
    try:
        dialect = sniffer.sniff(content[:4096], delimiters=",\t;|")
        return dialect.delimiter
    except csv.Error:
        return ","


def detect_column_mapping(headers: List[str]) -> Dict[str, Optional[str]]:
    """Auto-detect column mapping using fuzzy string matching."""
    mapping = {}

    for field, aliases in COLUMN_ALIASES.items():
        best_match = None
        best_score = 0.0

        for header in headers:
            header_clean = header.lower().strip()
            # Exact match first
            if header_clean in [a.lower() for a in aliases]:
                best_match = header
                best_score = 1.0
                break
            # Fuzzy match
            for alias in aliases:
                score = _similarity(header_clean, alias.lower())
                if score > best_score and score >= 0.65:
                    best_match = header
                    best_score = score

        mapping[field] = best_match

    return mapping


def parse_csv_content(
    content: str,
    column_mapping: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """
    Parse CSV content into structured preview data.

    Returns:
        {
            "headers": [...],
            "column_mapping": {...},
            "rows": [...],
            "warnings": [...],
            "errors": [...],
            "total_rows": int,
            "valid_rows": int,
            "error_rows": int,
            "estimated_total_value": float,
        }
    """
    result = {
        "headers": [],
        "column_mapping": {},
        "rows": [],
        "warnings": [],
        "errors": [],
        "total_rows": 0,
        "valid_rows": 0,
        "error_rows": 0,
        "estimated_total_value": 0.0,
    }

    try:
        # Detect delimiter
        delimiter = detect_delimiter(content)

        # Parse CSV
        reader = csv.DictReader(io.StringIO(content), delimiter=delimiter)
        if not reader.fieldnames:
            result["errors"].append("Could not detect CSV headers.")
            return result

        headers = list(reader.fieldnames)
        result["headers"] = headers

        # Auto-detect or use provided column mapping
        if column_mapping:
            mapping = column_mapping
        else:
            mapping = detect_column_mapping(headers)

        result["column_mapping"] = mapping

        # Validate required columns
        if not mapping.get("symbol"):
            result["errors"].append(
                "Could not detect a 'Symbol' column. "
                f"Available columns: {', '.join(headers)}"
            )
            return result

        if not mapping.get("quantity"):
            result["warnings"].append(
                "Could not detect a 'Quantity' column. All holdings will default to quantity 0."
            )

        # Parse rows
        total_value = 0.0
        for row_idx, raw_row in enumerate(reader, start=1):
            row_data = {
                "row_number": row_idx,
                "symbol": "",
                "name": None,
                "quantity": 0.0,
                "avg_price": None,
                "cost_basis": None,
                "current_value": None,
                "unrealized_gain": None,
                "unrealized_gain_pct": None,
                "warnings": [],
                "errors": [],
            }

            # Extract symbol
            symbol_col = mapping.get("symbol")
            if symbol_col and raw_row.get(symbol_col):
                row_data["symbol"] = raw_row[symbol_col].strip().upper()
            else:
                row_data["errors"].append("Missing symbol")
                result["error_rows"] += 1
                result["rows"].append(row_data)
                continue

            # Skip empty rows
            if not row_data["symbol"]:
                continue

            # Extract name
            name_col = mapping.get("name")
            if name_col:
                row_data["name"] = raw_row.get(name_col, "").strip() or None

            # Extract numeric fields
            qty_col = mapping.get("quantity")
            if qty_col:
                qty = _clean_number(raw_row.get(qty_col, ""))
                if qty is not None:
                    row_data["quantity"] = qty
                else:
                    row_data["warnings"].append("Could not parse quantity")

            price_col = mapping.get("avg_price")
            if price_col:
                row_data["avg_price"] = _clean_number(raw_row.get(price_col, ""))

            basis_col = mapping.get("cost_basis")
            if basis_col:
                row_data["cost_basis"] = _clean_number(raw_row.get(basis_col, ""))

            value_col = mapping.get("current_value")
            if value_col:
                val = _clean_number(raw_row.get(value_col, ""))
                row_data["current_value"] = val
                if val:
                    total_value += val

            gain_col = mapping.get("unrealized_gain")
            if gain_col:
                row_data["unrealized_gain"] = _clean_number(raw_row.get(gain_col, ""))

            gain_pct_col = mapping.get("unrealized_gain_pct")
            if gain_pct_col:
                row_data["unrealized_gain_pct"] = _clean_number(raw_row.get(gain_pct_col, ""))

            # Validation warnings
            if row_data["quantity"] == 0 and not row_data.get("current_value"):
                row_data["warnings"].append("Zero quantity and no value")

            if row_data["avg_price"] is None and row_data["cost_basis"] is None:
                row_data["warnings"].append("Missing cost basis information")

            result["rows"].append(row_data)
            result["total_rows"] += 1
            if not row_data["errors"]:
                result["valid_rows"] += 1
            else:
                result["error_rows"] += 1

        result["estimated_total_value"] = round(total_value, 2)

        # Summary warnings
        if result["error_rows"] > 0:
            result["warnings"].append(
                f"{result['error_rows']} row(s) have errors and may not be imported."
            )

    except Exception as e:
        logger.error(f"CSV parsing error: {e}")
        result["errors"].append(f"Failed to parse CSV: {str(e)}")

    return result


def parse_csv_file(file_content: bytes, filename: str = "upload.csv") -> Dict[str, Any]:
    """Parse a CSV file from bytes content."""
    # Try common encodings
    for encoding in ["utf-8", "utf-8-sig", "latin-1", "cp1252"]:
        try:
            content = file_content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        return {
            "headers": [],
            "column_mapping": {},
            "rows": [],
            "warnings": [],
            "errors": ["Could not decode CSV file. Please ensure it is UTF-8 encoded."],
            "total_rows": 0,
            "valid_rows": 0,
            "error_rows": 0,
            "estimated_total_value": 0.0,
        }

    result = parse_csv_content(content)
    result["filename"] = filename
    return result
