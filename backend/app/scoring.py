"""Profit-potential scoring, risk classification, and trade recommendation.

The functions here turn the raw indicators (`indicators.py`) and the Markov
chain output (`markov.py`) into three user-facing values:

- ``profit_score``: 0..100, higher = more attractive forward return setup
- ``risk_level``: ``"low"`` / ``"medium"`` / ``"high"``
- ``recommendation``: ``"strong_buy"`` / ``"buy"`` / ``"hold"`` / ``"avoid"``

The scoring is intentionally transparent: every component contribution is
returned in ``score_breakdown`` so the UI can display *why* a stock got its
rating.
"""

from __future__ import annotations

from typing import Any

# Component weights for the profit score. They sum to 1.0.
_WEIGHTS: dict[str, float] = {
    "horizon_positive": 0.25,
    "next_positive": 0.10,
    "momentum": 0.20,
    "trend": 0.15,
    "volume": 0.10,
    "rsi": 0.10,
    "volatility_penalty": 0.10,
}

# Volatility-score thresholds for the risk bucket.
_RISK_LOW_MAX = 30.0
_RISK_MEDIUM_MAX = 60.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_momentum(momentum_20d: float) -> float:
    """Map 20-day momentum (decimal) to a 0..1 sub-score.

    -15% or worse -> 0, 0% -> 0.5, +15% or better -> 1.0.
    """
    return _clamp((momentum_20d + 0.15) / 0.30, 0.0, 1.0)


def _score_trend(trend_direction: str, ma_20: float, ma_50: float, last_close: float) -> float:
    """Combine MA cross signal with the discrete trend tag.

    "up" trend + price above both MAs is the ideal setup (1.0). A clean
    downtrend with price below both MAs collapses to 0.0.
    """
    base = {"up": 0.7, "sideways": 0.5, "down": 0.2}.get(trend_direction, 0.5)

    # MA cross bonus: +0.3 when fast MA is above slow MA AND price is above fast MA.
    if ma_20 > 0 and ma_50 > 0 and last_close > 0:
        if ma_20 > ma_50 and last_close > ma_20:
            return _clamp(base + 0.3, 0.0, 1.0)
        if ma_20 < ma_50 and last_close < ma_20:
            return _clamp(base - 0.2, 0.0, 1.0)
    return base


def _score_volume(volume_change: float) -> float:
    """Recent volume vs baseline. -50% -> 0, flat -> 0.5, +100%+ -> 1.0."""
    return _clamp((volume_change + 0.5) / 1.5, 0.0, 1.0)


def _score_rsi(rsi_value: float) -> float:
    """Bell curve centered around 55 (slightly bullish optimum).

    Overbought (>70) and oversold (<30) territories both score lower.
    """
    distance = abs(rsi_value - 55.0)
    return _clamp(1.0 - (distance / 35.0), 0.0, 1.0)


def _score_volatility_penalty(volatility_score: float) -> float:
    """Higher volatility means lower score. 0 vol -> 1.0, 100 vol -> 0.0."""
    return _clamp(1.0 - (volatility_score / 100.0), 0.0, 1.0)


def compute_profit_score(
    indicators: dict[str, Any],
    markov_metrics: dict[str, Any],
    last_close: float,
) -> dict[str, Any]:
    """Combine indicators and Markov forward-looking probabilities into a 0..100 score."""
    components = {
        "horizon_positive": _clamp(float(markov_metrics.get("horizon_positive_probability", 0.0)), 0.0, 1.0),
        "next_positive": _clamp(float(markov_metrics.get("next_positive_probability", 0.0)), 0.0, 1.0),
        "momentum": _score_momentum(float(indicators.get("momentum_20d", 0.0))),
        "trend": _score_trend(
            str(indicators.get("trend_direction", "sideways")),
            float(indicators.get("ma_20", 0.0)),
            float(indicators.get("ma_50", 0.0)),
            float(last_close),
        ),
        "volume": _score_volume(float(indicators.get("volume_change", 0.0))),
        "rsi": _score_rsi(float(indicators.get("rsi_14", 50.0))),
        "volatility_penalty": _score_volatility_penalty(
            float(indicators.get("volatility_score", 0.0))
        ),
    }

    weighted_total = sum(components[name] * _WEIGHTS[name] for name in _WEIGHTS)
    score = round(weighted_total * 100.0, 2)

    breakdown = {
        name: {
            "value": round(components[name], 4),
            "weight": _WEIGHTS[name],
            "contribution": round(components[name] * _WEIGHTS[name] * 100.0, 2),
        }
        for name in _WEIGHTS
    }

    return {"profit_score": score, "score_breakdown": breakdown}


def compute_risk_level(volatility_score: float) -> str:
    if volatility_score < _RISK_LOW_MAX:
        return "low"
    if volatility_score < _RISK_MEDIUM_MAX:
        return "medium"
    return "high"


def compute_recommendation(profit_score: float, risk_level: str) -> str:
    """Decision matrix combining profit potential and risk."""
    if profit_score >= 70 and risk_level in ("low", "medium"):
        return "strong_buy"
    if profit_score >= 55:
        return "buy"
    if profit_score >= 40:
        return "hold"
    return "avoid"


def recommendation_color(recommendation: str) -> str:
    """Color tag the frontend can use directly (green / yellow / red)."""
    return {
        "strong_buy": "green",
        "buy": "green",
        "hold": "yellow",
        "avoid": "red",
    }.get(recommendation, "yellow")


def score_stock(
    indicators: dict[str, Any],
    markov_metrics: dict[str, Any],
    last_close: float,
) -> dict[str, Any]:
    """Top-level helper used by the analyze endpoint."""
    profit = compute_profit_score(indicators, markov_metrics, last_close)
    risk = compute_risk_level(float(indicators.get("volatility_score", 0.0)))
    recommendation = compute_recommendation(profit["profit_score"], risk)

    return {
        "profit_score": profit["profit_score"],
        "score_breakdown": profit["score_breakdown"],
        "risk_level": risk,
        "recommendation": recommendation,
        "recommendation_color": recommendation_color(recommendation),
    }
