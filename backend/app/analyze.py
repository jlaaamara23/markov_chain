"""Per-stock analysis orchestrator used by the /analyze endpoint.

Pulls OHLCV history once per ticker, then drives the indicators, Markov
chain, and scoring modules from the same data so we never round-trip to
Yahoo twice for the same symbol in a single request.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

import numpy as np

from app.indicators import compute_all_indicators
from app.markov import _current_price, run_prediction_from_closes
from app.scoring import score_stock
from app.sources import build_indicator_sources, build_scoring_sources, merge_calculation_sources
from app.ticker_util import normalize_equity_symbol

ANALYZE_SCHEMA_VERSION = 1


def _fetch_ohlcv(symbol: str, period: str) -> dict[str, Any]:
    """Fetch close + volume + name/currency metadata in a single yfinance call.

    Returns a dict with ``close`` and ``volume`` numpy arrays (already aligned
    and NaN-dropped) plus ``last_close`` / ``previous_close`` / ``name`` /
    ``currency`` for the response payload.
    """
    import yfinance as yf

    sym = normalize_equity_symbol(symbol)
    ticker = yf.Ticker(sym)
    hist = ticker.history(period=period, auto_adjust=True)
    if hist is None or len(hist) < 3:
        raise ValueError(
            f"No or insufficient price history for {sym} (period={period}). "
            "Check the ticker spelling (e.g. Apple is AAPL, not APPL)."
        )

    frame = hist[["Close", "Volume"]].dropna()
    if len(frame) < 3:
        raise ValueError(f"Not enough close observations for {sym}")

    close = frame["Close"].astype(float).to_numpy()
    volume = frame["Volume"].astype(float).to_numpy()

    last_close = float(close[-1])
    previous_close = float(close[-2])

    name: str | None = None
    currency: str | None = None
    try:
        info = ticker.info or {}
        name = info.get("longName") or info.get("shortName")
        currency = info.get("currency")
    except Exception:
        pass

    return {
        "symbol": sym,
        "name": name,
        "currency": currency,
        "close": close,
        "volume": volume,
        "last_close": last_close,
        "previous_close": previous_close,
    }


def analyze_symbol(
    symbol: str,
    period: str,
    steps: int,
    context_len: int,
) -> dict[str, Any]:
    """Run the full analysis pipeline for a single ticker."""
    fetched = _fetch_ohlcv(symbol, period)
    close: np.ndarray = fetched["close"]
    volume: np.ndarray = fetched["volume"]
    sym = fetched["symbol"]
    last_close = fetched["last_close"]
    previous_close = fetched["previous_close"]

    current_price = _current_price(sym)

    markov_full = run_prediction_from_closes(
        close_prices=close,
        symbol=sym,
        period=period,
        steps=steps,
        context_len=context_len,
        current_price=current_price,
    )

    indicators = compute_all_indicators(close, volume)

    # Compact summary used by the score/recommendation engine. The full
    # Markov payload is also returned below so the UI can render the
    # detailed next-day / horizon distributions for the selected ticker.
    markov_summary = {
        "next_positive_probability": markov_full["next_positive_probability"],
        "horizon_positive_probability": markov_full["horizon_positive_probability"],
        "equilibrium_positive_probability": markov_full["equilibrium_positive_probability"],
        "predicted_state": markov_full["predicted_state"],
        "current_state": markov_full["current_state"],
        "confidence": markov_full["confidence"],
        "expected_return_next_day": markov_full["expected_return_next_day"],
        "estimated_next_close": markov_full["estimated_next_close"],
        "expected_return_horizon": markov_full["expected_return_horizon"],
        "estimated_close_horizon": markov_full["estimated_close_horizon"],
        "horizon_steps": markov_full["horizon_steps"],
        "context_len": markov_full["context_len"],
    }

    scoring = score_stock(indicators, markov_summary, last_close)

    change_amount = last_close - previous_close
    change_percent = (change_amount / previous_close * 100.0) if previous_close else 0.0

    calculation_sources = merge_calculation_sources(
        markov_full.get("calculation_sources", {}),
        build_indicator_sources(
            indicators,
            last_close=last_close,
            previous_close=previous_close,
        ),
        build_scoring_sources(scoring, markov_summary),
    )
    markov_full = {**markov_full, "calculation_sources": calculation_sources}

    return {
        "symbol": sym,
        "name": fetched["name"],
        "currency": fetched["currency"],
        "period": period,
        "last_close": round(last_close, 4),
        "previous_close": round(previous_close, 4),
        "current_price": round(float(current_price), 4) if current_price is not None else None,
        "change_amount": round(change_amount, 4),
        "change_percent": round(change_percent, 4),
        "indicators": indicators,
        "markov": markov_summary,
        "markov_detail": markov_full,
        "scoring": scoring,
        "calculation_sources": calculation_sources,
    }


def analyze_symbols(
    symbols: list[str],
    period: str = "2y",
    steps: int = 5,
    context_len: int = 5,
) -> dict[str, Any]:
    """Analyze a list of symbols, ranked by profit_score (highest first).

    Failed symbols don't break the response: their error message is recorded
    in ``errors`` so the UI can surface it next to the ranked results.
    """
    cleaned: list[str] = []
    for raw in symbols:
        if not raw:
            continue
        try:
            cleaned.append(normalize_equity_symbol(raw))
        except ValueError:
            continue
    cleaned = list(dict.fromkeys(cleaned))[:25]

    results: list[dict[str, Any]] = []
    errors: dict[str, str] = {}

    for sym in cleaned:
        try:
            results.append(
                analyze_symbol(sym, period=period, steps=steps, context_len=context_len)
            )
        except ValueError as exc:
            errors[sym] = str(exc)
        except Exception as exc:  # pragma: no cover - defensive against yfinance flakiness
            errors[sym] = f"Unexpected error: {exc!r}"

    results.sort(key=lambda r: float(r["scoring"]["profit_score"]), reverse=True)

    return {
        "schema_version": ANALYZE_SCHEMA_VERSION,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "period": period,
        "horizon_steps": steps,
        "context_len": context_len,
        "count": len(results),
        "results": results,
        "errors": errors,
    }
