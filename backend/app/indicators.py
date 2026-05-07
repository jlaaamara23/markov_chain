"""Technical indicators computed from numpy price/volume arrays.

All public functions are pure: they take numpy arrays and return scalars
(or short dicts of scalars). They do not perform any I/O. yfinance access
is handled in `analyze.py`, so indicators can be unit-tested in isolation.
"""

from __future__ import annotations

import math
from typing import Any

import numpy as np

# Trading days per year, used to annualize daily statistics.
TRADING_DAYS_PER_YEAR = 252

# Volatility score caps. An annualized stdev of 0% maps to score 0;
# 80%+ annualized stdev maps to score 100. Values in between scale linearly.
_VOL_SCORE_CAP_ANNUALIZED = 0.80


def daily_simple_returns(close: np.ndarray) -> np.ndarray:
    if close.size < 2:
        return np.empty(0, dtype=float)
    return close[1:] / close[:-1] - 1.0


def standard_deviation(returns: np.ndarray, annualize: bool = False) -> float:
    """Sample standard deviation of daily returns.

    `annualize=True` multiplies by sqrt(252), which is the standard convention
    for converting daily return volatility into an annualized figure.
    """
    if returns.size < 2:
        return 0.0
    sd = float(np.std(returns, ddof=1))
    if annualize:
        sd *= math.sqrt(TRADING_DAYS_PER_YEAR)
    return sd


def moving_average(close: np.ndarray, window: int) -> float:
    """Latest n-period simple moving average. Returns 0.0 if window > length."""
    if window <= 0 or close.size < window:
        return 0.0
    return float(np.mean(close[-window:]))


def rsi(close: np.ndarray, period: int = 14) -> float:
    """Relative Strength Index using Wilder's smoothing.

    Returns a value in [0, 100]. Falls back to 50.0 (neutral) when there is
    not enough history to compute the indicator reliably.
    """
    if close.size < period + 1:
        return 50.0

    diffs = np.diff(close)
    gains = np.where(diffs > 0, diffs, 0.0)
    losses = np.where(diffs < 0, -diffs, 0.0)

    avg_gain = float(np.mean(gains[:period]))
    avg_loss = float(np.mean(losses[:period]))

    # Wilder smoothing: avg_t = (avg_{t-1} * (n-1) + value_t) / n
    for i in range(period, len(diffs)):
        avg_gain = (avg_gain * (period - 1) + float(gains[i])) / period
        avg_loss = (avg_loss * (period - 1) + float(losses[i])) / period

    if avg_loss == 0.0:
        return 100.0 if avg_gain > 0 else 50.0
    rs = avg_gain / avg_loss
    return float(100.0 - (100.0 / (1.0 + rs)))


def momentum(close: np.ndarray, lookback: int = 20) -> float:
    """Rate of change over `lookback` trading days, expressed as a decimal."""
    if lookback <= 0 or close.size <= lookback:
        return 0.0
    base = float(close[-lookback - 1])
    if base <= 0:
        return 0.0
    return float(close[-1]) / base - 1.0


def volume_change(volume: np.ndarray, recent: int = 5, baseline: int = 20) -> float:
    """Recent vs baseline volume ratio minus 1.

    A value of +0.25 means the last `recent` sessions averaged 25% more volume
    than the prior `baseline` sessions. 0.0 means flat.
    """
    if recent <= 0 or baseline <= 0:
        return 0.0
    if volume.size < recent + baseline:
        return 0.0
    recent_mean = float(np.mean(volume[-recent:]))
    baseline_mean = float(np.mean(volume[-(recent + baseline) : -recent]))
    if baseline_mean <= 0:
        return 0.0
    return recent_mean / baseline_mean - 1.0


def trend_direction(close: np.ndarray, short: int = 20, long: int = 50) -> str:
    """Coarse trend tag based on relative position of two SMAs.

    "up" when the short SMA is meaningfully above the long SMA, "down" when
    below, and "sideways" when they are within ~0.5% of each other.
    """
    if close.size < long:
        return "sideways"
    short_ma = float(np.mean(close[-short:]))
    long_ma = float(np.mean(close[-long:]))
    if long_ma <= 0:
        return "sideways"
    spread = (short_ma - long_ma) / long_ma
    if spread > 0.005:
        return "up"
    if spread < -0.005:
        return "down"
    return "sideways"


def historical_growth(close: np.ndarray) -> float:
    """Total return over the entire window, as a decimal."""
    if close.size < 2 or close[0] <= 0:
        return 0.0
    return float(close[-1]) / float(close[0]) - 1.0


def volatility_score(returns: np.ndarray) -> float:
    """Map annualized stdev to a 0..100 score.

    Designed so 0% vol -> 0, 80%+ annualized vol -> 100. Values are clamped.
    Higher values mean more volatile / risky.
    """
    annualized = standard_deviation(returns, annualize=True)
    if annualized <= 0:
        return 0.0
    score = (annualized / _VOL_SCORE_CAP_ANNUALIZED) * 100.0
    return float(max(0.0, min(100.0, score)))


def compute_all_indicators(close: np.ndarray, volume: np.ndarray) -> dict[str, Any]:
    """Compute every indicator we expose to the API in one pass."""
    returns = daily_simple_returns(close)

    stdev_daily = standard_deviation(returns, annualize=False)
    stdev_annualized = standard_deviation(returns, annualize=True)
    ma_20 = moving_average(close, 20)
    ma_50 = moving_average(close, 50)
    rsi_14 = rsi(close, 14)
    momentum_20d = momentum(close, 20)
    momentum_60d = momentum(close, 60)
    vol_change = volume_change(volume) if volume.size else 0.0
    trend = trend_direction(close)
    growth = historical_growth(close)
    vol_score = volatility_score(returns)

    return {
        "stdev_daily": round(stdev_daily, 6),
        "stdev_annualized": round(stdev_annualized, 6),
        "ma_20": round(ma_20, 6),
        "ma_50": round(ma_50, 6),
        "rsi_14": round(rsi_14, 4),
        "momentum_20d": round(momentum_20d, 6),
        "momentum_60d": round(momentum_60d, 6),
        "volume_change": round(vol_change, 6),
        "trend_direction": trend,
        "historical_growth": round(growth, 6),
        "volatility_score": round(vol_score, 4),
    }
