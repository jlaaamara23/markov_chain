"""Shared ticker normalization (aliases for common typos)."""

from __future__ import annotations

import re

# Yahoo Finance symbols users often mistype
_ALIASES: dict[str, str] = {
    "APPL": "AAPL",
}


def normalize_equity_symbol(raw: str) -> str:
    s = raw.strip().upper()
    if not re.fullmatch(r"[A-Z0-9.\-]{1,12}", s):
        raise ValueError("Invalid symbol format")
    return _ALIASES.get(s, s)
