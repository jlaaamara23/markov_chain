"""Profit-potential scoring, risk classification, and trade recommendation.

All profit-score components come from the Markov chain output.
"""

from __future__ import annotations

from typing import Any

# Profit score weights (sum to 1.0).
_WEIGHTS: dict[str, float] = {
    "horizon_return": 0.30,
    "horizon_positive": 0.20,
    "next_return": 0.15,
    "next_positive": 0.10,
    "equilibrium_return": 0.15,
    "equilibrium_positive": 0.05,
    "confidence": 0.05,
}

# Map expected returns (decimal) to a 0..1 sub-score centered at 0.5.
_HORIZON_RETURN_SCALE = 0.08
_NEXT_RETURN_SCALE = 0.03
_EQUILIBRIUM_RETURN_SCALE = 0.08

# Volatility-score thresholds for the risk bucket.
_RISK_LOW_MAX = 30.0
_RISK_MEDIUM_MAX = 60.0


def _clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def _score_expected_return(ret: float, scale: float) -> float:
    """0.5 at flat return; rises toward 1.0 for strong positive Markov expectation."""
    if scale <= 0:
        return 0.5
    return _clamp(0.5 + float(ret) / scale, 0.0, 1.0)


def compute_profit_score(
    indicators: dict[str, Any],
    markov_metrics: dict[str, Any],
    last_close: float,
) -> dict[str, Any]:
    """Combine Markov expected returns and probabilities into a 0..100 score."""
    components = {
        "horizon_return": _score_expected_return(
            float(markov_metrics.get("expected_return_horizon", 0.0)),
            _HORIZON_RETURN_SCALE,
        ),
        "horizon_positive": _clamp(
            float(markov_metrics.get("horizon_positive_probability", 0.0)), 0.0, 1.0
        ),
        "next_return": _score_expected_return(
            float(markov_metrics.get("expected_return_next_day", 0.0)),
            _NEXT_RETURN_SCALE,
        ),
        "next_positive": _clamp(
            float(markov_metrics.get("next_positive_probability", 0.0)), 0.0, 1.0
        ),
        "equilibrium_return": _score_expected_return(
            float(markov_metrics.get("equilibrium_expected_return", 0.0)),
            _EQUILIBRIUM_RETURN_SCALE,
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
    """Decision matrix combining Markov profit potential and volatility risk."""
    if profit_score >= 68 and risk_level in ("low", "medium"):
        return "strong_buy"
    if profit_score >= 52:
        return "buy"
    if profit_score >= 38:
        return "hold"
    return "avoid"


def recommendation_color(recommendation: str) -> str:
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
