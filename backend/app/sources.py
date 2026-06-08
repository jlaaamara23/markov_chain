"""Calculation provenance for the UI — tap any number to see its formula."""

from __future__ import annotations

from typing import Any

from app.scoring import _WEIGHTS


def _src(
    method: str,
    formula: str,
    description: str,
    inputs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    return {
        "method": method,
        "formula": formula,
        "description": description,
        "inputs": inputs or {},
    }


def build_indicator_sources(
    indicators: dict[str, Any],
    *,
    last_close: float,
    previous_close: float,
) -> dict[str, dict[str, Any]]:
    return {
        "stdev_daily": _src(
            "sample_standard_deviation",
            "std(daily_returns, ddof=1)",
            "Sample standard deviation of daily simple returns over the selected history window.",
            {"stdev_daily": indicators.get("stdev_daily")},
        ),
        "stdev_annualized": _src(
            "annualized_volatility",
            "std(daily_returns) × √252",
            "Daily return volatility scaled to a full trading year (252 days).",
            {
                "stdev_daily": indicators.get("stdev_daily"),
                "trading_days_per_year": 252,
                "stdev_annualized": indicators.get("stdev_annualized"),
            },
        ),
        "volatility_score": _src(
            "volatility_score_mapping",
            "clamp(annualized_stdev / 0.80 × 100, 0, 100)",
            "Maps annualized volatility to a 0–100 risk score (80%+ annualized stdev → 100).",
            {
                "stdev_annualized": indicators.get("stdev_annualized"),
                "volatility_score": indicators.get("volatility_score"),
            },
        ),
        "ma_20": _src(
            "simple_moving_average",
            "mean(close[-20:])",
            "20-day simple moving average of the close price (context only, not used in Markov predictions).",
            {"ma_20": indicators.get("ma_20"), "window": 20},
        ),
        "ma_50": _src(
            "simple_moving_average",
            "mean(close[-50:])",
            "50-day simple moving average of the close price (context only, not used in Markov predictions).",
            {"ma_50": indicators.get("ma_50"), "window": 50},
        ),
        "rsi_14": _src(
            "rsi_wilder",
            "RSI = 100 − 100 / (1 + RS), RS = avg_gain / avg_loss (Wilder smoothing, period 14)",
            "Relative Strength Index using 14-day Wilder smoothing.",
            {"rsi_14": indicators.get("rsi_14"), "period": 14},
        ),
        "momentum_20d": _src(
            "price_momentum",
            "close[-1] / close[-21] − 1",
            "Total return over the last 20 trading days.",
            {"momentum_20d": indicators.get("momentum_20d"), "lookback_days": 20},
        ),
        "momentum_60d": _src(
            "price_momentum",
            "close[-1] / close[-61] − 1",
            "Total return over the last 60 trading days.",
            {"momentum_60d": indicators.get("momentum_60d"), "lookback_days": 60},
        ),
        "volume_change": _src(
            "volume_ratio",
            "mean(volume[-5:]) / mean(volume[-25:-5]) − 1",
            "Recent 5-session average volume vs the prior 20-session baseline.",
            {"volume_change": indicators.get("volume_change")},
        ),
        "historical_growth": _src(
            "total_return",
            "close[-1] / close[0] − 1",
            "Total return across the entire selected history window.",
            {"historical_growth": indicators.get("historical_growth")},
        ),
        "trend_direction": _src(
            "sma_spread",
            "(SMA20 − SMA50) / SMA50; up if > 0.5%, down if < −0.5%",
            "Coarse trend tag from the relative position of the 20- and 50-day SMAs.",
            {
                "trend_direction": indicators.get("trend_direction"),
                "ma_20": indicators.get("ma_20"),
                "ma_50": indicators.get("ma_50"),
            },
        ),
        "last_close": _src(
            "market_data",
            "last adjusted close from yfinance history",
            "Most recent closing price in the downloaded OHLCV series.",
            {"last_close": last_close},
        ),
        "change_percent": _src(
            "daily_change",
            "(last_close − previous_close) / previous_close × 100",
            "Percent change versus the prior trading session's close.",
            {
                "last_close": last_close,
                "previous_close": previous_close,
                "change_percent": round(
                    (last_close - previous_close) / previous_close * 100.0, 4
                )
                if previous_close
                else 0,
            },
        ),
        "change_amount": _src(
            "daily_change",
            "last_close − previous_close",
            "Dollar change versus the prior trading session's close.",
            {
                "last_close": last_close,
                "previous_close": previous_close,
                "change_amount": round(last_close - previous_close, 4),
            },
        ),
    }


def build_scoring_sources(
    scoring: dict[str, Any],
    markov_metrics: dict[str, Any],
) -> dict[str, dict[str, Any]]:
    breakdown = scoring.get("score_breakdown") or {}
    sources: dict[str, dict[str, Any]] = {
        "profit_score": _src(
            "markov_weighted_score",
            "Σ (component_value × weight) × 100",
            "Profit score from Markov expected returns and probabilities only (no MA or Monte Carlo).",
            {
                "profit_score": scoring.get("profit_score"),
                "weights": _WEIGHTS,
            },
        ),
        "risk_level": _src(
            "volatility_buckets",
            "low if volatility_score < 30; medium if < 60; else high",
            "Risk bucket derived from the volatility score (technical context).",
            {"risk_level": scoring.get("risk_level")},
        ),
        "recommendation": _src(
            "score_risk_matrix",
            "strong_buy / buy / hold / avoid from profit_score + risk_level",
            "Trade recommendation combining Markov profit score and volatility risk.",
            {
                "recommendation": scoring.get("recommendation"),
                "profit_score": scoring.get("profit_score"),
                "risk_level": scoring.get("risk_level"),
            },
        ),
        "confidence": _src(
            "markov_chain_next_day",
            "max P(next_state | context)",
            "Probability mass on the most likely next-day return bin.",
            {"confidence": markov_metrics.get("confidence")},
        ),
        "next_positive_probability": _src(
            "markov_chain_next_day",
            "Σ P(state) for bins with lower bound ≥ 0%",
            "Next-day probability of a non-negative return bin.",
            {"next_positive_probability": markov_metrics.get("next_positive_probability")},
        ),
    }

    for name, info in breakdown.items():
        weight = info.get("weight", _WEIGHTS.get(name, 0))
        sources[f"score_breakdown__{name}"] = _src(
            "markov_score_component",
            f"component × {weight} × 100",
            f"Contribution of '{name.replace('_', ' ')}' to the profit score.",
            {
                "component": info.get("value"),
                "weight": weight,
                "contribution": info.get("contribution"),
                "raw_markov_value": markov_metrics.get(
                    {
                        "horizon_return": "expected_return_horizon",
                        "horizon_positive": "horizon_positive_probability",
                        "next_return": "expected_return_next_day",
                        "next_positive": "next_positive_probability",
                        "equilibrium_return": "equilibrium_expected_return",
                        "equilibrium_positive": "equilibrium_positive_probability",
                        "confidence": "confidence",
                    }.get(name, name)
                ),
            },
        )

    return sources


def merge_calculation_sources(*parts: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for part in parts:
        merged.update(part)
    return merged
