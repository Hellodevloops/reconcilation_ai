#!/usr/bin/env python3

import re
from datetime import datetime

def _normalize_date_yyyy_mm_dd(raw: str | None) -> str | None:
    """Normalize date to YYYY-MM-DD format"""
    print(f"DEBUG: Normalizing date: '{raw}'")
    if not raw:
        return None
    txt = str(raw).strip()
    if not txt:
        return None

    txt = re.sub(r"\s+", " ", txt)
    candidates = [
        "%Y-%m-%d",
        "%d/%m/%Y",
        "%d-%m-%Y",
        "%d/%m/%y",
        "%d-%m-%y",
        "%d %b %Y",
        "%d %B %Y",
        "%d %b %y",
        "%d %B %y",
    ]
    for fmt in candidates:
        try:
            result = datetime.strptime(txt, fmt).date().isoformat()
            print(f"DEBUG: Successfully parsed with format '{fmt}': {result}")
            return result
        except Exception as e:
            print(f"DEBUG: Failed to parse '{txt}' with format '{fmt}': {e}")
            continue
    print(f"DEBUG: Could not parse date '{txt}' with any format")
    return None

# Test the date parsing
test_dates = ["01/15/2024", "15/01/2024", "2024-01-15"]
for date in test_dates:
    print(f"Testing date: {date}")
    result = _normalize_date_yyyy_mm_dd(date)
    print(f"Result: {result}")
    print()
