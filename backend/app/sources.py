"""Calculation provenance metadata for traceable UI values."""

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
            "daily_volatility",
            "How much the price typically moves up or down each day.",
            "Measures day-to-day price swings over the selected history.",
            {"stdev_daily": indicators.get("stdev_daily")},
        ),
        "stdev_annualized": _src(
            "yearly_volatility",
            "Daily volatility scaled up to a full trading year (252 days).",
            "Shows how volatile the stock would look on a yearly basis.",
            {
                "stdev_daily": indicators.get("stdev_daily"),
                "trading_days_per_year": 252,
                "stdev_annualized": indicators.get("stdev_annualized"),
            },
        ),
        "volatility_score": _src(
            "risk_score",
            "Yearly volatility mapped to a score from 0 (calm) to 100 (very volatile).",
            "Higher score means bigger price swings and more risk.",
            {
                "stdev_annualized": indicators.get("stdev_annualized"),
                "volatility_score": indicators.get("volatility_score"),
            },
        ),
        "ma_20": _src(
            "moving_average",
            "Average closing price over the last 20 trading days.",
            "Smooths short-term price noise.",
            {"ma_20": indicators.get("ma_20"), "window": 20},
        ),
        "ma_50": _src(
            "moving_average",
            "Average closing price over the last 50 trading days.",
            "Shows the medium-term price trend.",
            {"ma_50": indicators.get("ma_50"), "window": 50},
        ),
        "rsi_14": _src(
            "rsi",
            "Momentum score from 0 to 100 based on recent gains vs losses.",
            "Above 70 often means strong recent gains; below 30 often means heavy selling.",
            {"rsi_14": indicators.get("rsi_14"), "period": 14},
        ),
        "momentum_20d": _src(
            "price_change",
            "Percent change from the price 20 trading days ago to today.",
            "Shows how much the stock moved over the last month of trading.",
            {"momentum_20d": indicators.get("momentum_20d"), "lookback_days": 20},
        ),
        "momentum_60d": _src(
            "price_change",
            "Percent change from the price 60 trading days ago to today.",
            "Shows the stock's move over roughly the last three months.",
            {"momentum_60d": indicators.get("momentum_60d"), "lookback_days": 60},
        ),
        "volume_change": _src(
            "volume_change",
            "Recent average volume compared with the prior month's average.",
            "Positive means more trading activity lately; negative means quieter trading.",
            {"volume_change": indicators.get("volume_change")},
        ),
        "historical_growth": _src(
            "total_return",
            "Percent change from the first price in the window to the last price.",
            "Total gain or loss across the whole selected history period.",
            {"historical_growth": indicators.get("historical_growth")},
        ),
        "trend_direction": _src(
            "trend",
            "Up if the short average is clearly above the long average; down if below; else sideways.",
            "A simple read on whether the stock is trending up, down, or flat.",
            {
                "trend_direction": indicators.get("trend_direction"),
                "ma_20": indicators.get("ma_20"),
                "ma_50": indicators.get("ma_50"),
            },
        ),
        "last_close": _src(
            "market_price",
            "The most recent closing price in the downloaded data.",
            "Latest end-of-day price used as the starting point for forecasts.",
            {"last_close": last_close},
        ),
        "change_percent": _src(
            "daily_change",
            "Percent change from yesterday's close to today's close.",
            "How much the stock moved since the previous trading session.",
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
            "Today's close minus yesterday's close.",
            "Dollar change since the previous trading session.",
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
            "profit_score",
            "Weighted sum of forecast returns, positive chances, and confidence → score out of 100.",
            "Higher score means stronger expected profit potential from the Markov forecast.",
            {
                "profit_score": scoring.get("profit_score"),
                "weights": _WEIGHTS,
            },
        ),
        "risk_level": _src(
            "risk_level",
            "Low if volatility score is under 30; medium if under 60; otherwise high.",
            "Tells you how risky the stock looks based on price swings.",
            {"risk_level": scoring.get("risk_level")},
        ),
        "recommendation": _src(
            "recommendation",
            "Buy, hold, or avoid — based on profit score and risk level together.",
            "Combines expected profit with how volatile the stock is.",
            {
                "recommendation": scoring.get("recommendation"),
                "profit_score": scoring.get("profit_score"),
                "risk_level": scoring.get("risk_level"),
            },
        ),
        "confidence": _src(
            "forecast_confidence",
            "The highest single probability among tomorrow's possible outcomes.",
            "How sure the model is about the most likely next-day result.",
            {"confidence": markov_metrics.get("confidence")},
        ),
        "next_positive_probability": _src(
            "positive_chance",
            "Add up the chances of all outcomes where return is zero or positive.",
            "Probability the stock does not fall into a negative return bin tomorrow.",
            {"next_positive_probability": markov_metrics.get("next_positive_probability")},
        ),
    }

    for name, info in breakdown.items():
        weight = info.get("weight", _WEIGHTS.get(name, 0))
        sources[f"score_breakdown__{name}"] = _src(
            "score_part",
            f"This part's value × {int(weight * 100)}% weight.",
            f"How much '{name.replace('_', ' ')}' adds to the total profit score.",
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
