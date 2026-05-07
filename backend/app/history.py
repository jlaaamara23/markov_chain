"""GET /history/{symbol}: time-series payload for the dashboard's price chart.

Returns close prices plus rolling 20-day and 50-day moving averages, with
ISO-formatted dates the frontend can hand directly to a chart library.

Kept deliberately small (Tier 1): close + ma_20 + ma_50 + dates. Volume,
realized returns, and Markov bin coloring belong to a follow-up tier and
are intentionally not included here so the response stays light.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from app.markov import _current_price
from app.ticker_util import normalize_equity_symbol

HISTORY_SCHEMA_VERSION = 1


def _fetch_history_frame(symbol: str, period: str):
    """Fetch a yfinance DataFrame keeping the original date index intact."""
    import yfinance as yf

    sym = normalize_equity_symbol(symbol)
    ticker = yf.Ticker(sym)
    hist = ticker.history(period=period, auto_adjust=True)
    if hist is None or len(hist) < 3:
        raise ValueError(
            f"No or insufficient price history for {sym} (period={period}). "
            "Check the ticker spelling (e.g. Apple is AAPL, not APPL)."
        )

    frame = hist[["Close"]].dropna()
    if len(frame) < 3:
        raise ValueError(f"Not enough close observations for {sym}")

    name: str | None = None
    currency: str | None = None
    try:
        info = ticker.info or {}
        name = info.get("longName") or info.get("shortName")
        currency = info.get("currency")
    except Exception:
        pass

    return sym, frame, name, currency


def get_history(symbol: str, period: str = "2y") -> dict[str, Any]:
    sym, frame, name, currency = _fetch_history_frame(symbol, period)

    closes = frame["Close"].astype(float)
    # Rolling MAs return NaN until enough observations are accumulated; the
    # frontend treats null as "no line yet" and Recharts handles the gap with
    # `connectNulls`.
    ma_20 = closes.rolling(window=20, min_periods=20).mean()
    ma_50 = closes.rolling(window=50, min_periods=50).mean()

    series: list[dict[str, Any]] = []
    for date, close, m20, m50 in zip(frame.index, closes, ma_20, ma_50):
        date_str = date.strftime("%Y-%m-%d") if hasattr(date, "strftime") else str(date)
        series.append(
            {
                "date": date_str,
                "close": round(float(close), 4),
                "ma_20": None if np.isnan(m20) else round(float(m20), 4),
                "ma_50": None if np.isnan(m50) else round(float(m50), 4),
            }
        )

    last_close = float(closes.iloc[-1])
    current_price = _current_price(sym)

    return {
        "schema_version": HISTORY_SCHEMA_VERSION,
        "symbol": sym,
        "name": name,
        "currency": currency,
        "period": period,
        "last_close": round(last_close, 4),
        "current_price": round(float(current_price), 4) if current_price is not None else None,
        "count": len(series),
        "series": series,
    }
