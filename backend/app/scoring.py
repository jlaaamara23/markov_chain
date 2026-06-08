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

# Markov-only profit score weights (sum to 1.0). No MA20/MA50 or Monte Carlo.
_WEIGHTS: dict[str, float] = {
    "horizon_positive": 0.40,
    "next_positive": 0.25,
    "equilibrium_positive": 0.20,
    "confidence": 0.15,
}

# Volatility-score thresholds for the risk bucket.
_RISK_LOW_MAX = 30.0
_RISK_MEDIUM_MAX = 60.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def compute_profit_score(
    indicators: dict[str, Any],
    markov_metrics: dict[str, Any],
    last_close: float,
) -> dict[str, Any]:
    """Combine Markov chain probabilities into a 0..100 score (no MA or Monte Carlo)."""
    components = {
        "horizon_positive": _clamp(
            float(markov_metrics.get("horizon_positive_probability", 0.0)), 0.0, 1.0
        ),
        "next_positive": _clamp(
            float(markov_metrics.get("next_positive_probability", 0.0)), 0.0, 1.0
        ),
        "equilibrium_positive": _clamp(
            float(markov_metrics.get("equilibrium_positive_probability", 0.0)), 0.0, 1.0
        ),
        "confidence": _clamp(float(markov_metrics.get("confidence", 0.0)), 0.0, 1.0),
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
