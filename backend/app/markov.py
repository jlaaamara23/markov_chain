from __future__ import annotations

import io
import math
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from app.ticker_util import normalize_equity_symbol

# Uniform bins over observed returns; bounds use data min/max (no ±inf).
NUM_RETURN_BINS = 10
RETURN_PERIOD_DAYS = 5


def _normalize_symbol(symbol: str) -> str:
    return normalize_equity_symbol(symbol)


def _price_history(symbol: str, period: str) -> np.ndarray:
    import yfinance as yf

    sym = _normalize_symbol(symbol)
    ticker = yf.Ticker(sym)
    hist = ticker.history(period=period, auto_adjust=True)
    if hist is None or len(hist) < 3:
        raise ValueError(
            f"No or insufficient price history for {sym} (period={period}). "
            "Check the ticker spelling (e.g. Apple is AAPL, not APPL)."
        )

    close = hist["Close"].astype(float).dropna().to_numpy()
    if len(close) < 3:
        raise ValueError(f"Not enough close observations for {sym}")
    return close


def _current_price(symbol: str) -> float | None:
    """
    Best-effort current price (intraday) via yfinance.
    Falls back to None if unavailable (e.g., market closed / missing fields).
    """
    try:
        import yfinance as yf

        sym = _normalize_symbol(symbol)
        ticker = yf.Ticker(sym)

        # fast_info is usually cheaper/more reliable than full info.
        fi = getattr(ticker, "fast_info", None)
        if fi:
            for key in ("last_price", "lastPrice", "regularMarketPrice"):
                try:
                    val = fi.get(key)  # type: ignore[union-attr]
                except Exception:
                    val = None
                if val is not None:
                    v = float(val)
                    if np.isfinite(v) and v > 0:
                        return v

        info = None
        try:
            info = ticker.info or {}
        except Exception:
            info = {}
        for key in ("regularMarketPrice", "currentPrice", "previousClose"):
            val = info.get(key) if isinstance(info, dict) else None
            if val is not None:
                v = float(val)
                if np.isfinite(v) and v > 0:
                    return v
    except Exception:
        return None
    return None


def _daily_simple_returns(symbol: str, period: str) -> np.ndarray:
    close = _price_history(symbol, period)
    ret = close[1:] / close[:-1] - 1.0
    if len(ret) < 2:
        raise ValueError(f"Not enough return observations for {_normalize_symbol(symbol)}")
    return ret


def _period_returns(close: np.ndarray, period: int = RETURN_PERIOD_DAYS) -> np.ndarray:
    """Rolling N-day simple returns aligned to each trading day."""
    if period <= 0 or close.size <= period:
        raise ValueError(f"Need more than {period} close prices for {period}-day returns")
    return close[period:] / close[:-period] - 1.0


def _build_uniform_bin_edges(
    returns: np.ndarray, n_bins: int = NUM_RETURN_BINS
) -> tuple[tuple[float, ...], float, float]:
    """Equal-width bins from observed min to max (no infinity tails)."""
    r_min = float(np.min(returns))
    r_max = float(np.max(returns))
    if r_min == r_max:
        r_min -= 0.001
        r_max += 0.001
    step = (r_max - r_min) / n_bins
    edges = tuple(r_min + step * i for i in range(1, n_bins))
    return edges, r_min, r_max


def _build_uniform_bin_labels(
    edges: tuple[float, ...], r_min: float, r_max: float
) -> list[str]:
    bounds = [r_min, *edges, r_max]
    labels: list[str] = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        labels.append(f"{lo * 100:.2f}% to {hi * 100:.2f}%")
    return labels


def _returns_to_binned_states(
    returns: np.ndarray,
    edges: tuple[float, ...],
    labels: list[str],
    r_min: float,
    r_max: float,
) -> list[str]:
    states: list[str] = []
    n_bins = len(labels)
    for r in returns:
        val = float(r)
        if val <= r_min:
            idx = 0
        elif val >= r_max:
            idx = n_bins - 1
        else:
            idx = int(np.searchsorted(edges, val, side="right"))
        states.append(labels[idx])
    return states


def _bin_lower_bounds(r_min: float, edges: tuple[float, ...]) -> list[float]:
    return [r_min, *list(edges)]


def _distribution_dict(vec: np.ndarray, state_labels: list[str]) -> dict[str, float]:
    return {state_labels[i]: round(float(vec[i]), 6) for i in range(len(state_labels))}


def build_empirical_transition_matrix(
    state_sequence: list[str],
    state_labels: list[str],
    laplace: float = 1.0,
) -> np.ndarray:
    """
    Count transitions i -> j, apply Laplace smoothing, row-normalize to probabilities.
    """
    if len(state_sequence) < 2:
        raise ValueError("Need at least two states to estimate transitions")
    index = {s: i for i, s in enumerate(state_labels)}
    n = len(state_labels)
    counts = np.full((n, n), laplace, dtype=float)
    for a, b in zip(state_sequence[:-1], state_sequence[1:]):
        if a in index and b in index:
            counts[index[a], index[b]] += 1.0
    row_sums = counts.sum(axis=1, keepdims=True)
    return counts / row_sums


def _matrix_to_nested_dict(matrix: np.ndarray, state_labels: list[str]) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, si in enumerate(state_labels):
        out[si] = {
            sj: round(float(matrix[i, j]), 6) for j, sj in enumerate(state_labels)
        }
    return out


def _state_mean_returns(
    returns: np.ndarray, states: list[str], state_labels: list[str]
) -> dict[str, float]:
    sums = {s: 0.0 for s in state_labels}
    counts = {s: 0 for s in state_labels}
    for r, s in zip(returns, states):
        if s in sums:
            sums[s] += float(r)
            counts[s] += 1

    out: dict[str, float] = {}
    for s in state_labels:
        out[s] = (sums[s] / counts[s]) if counts[s] > 0 else 0.0
    return out


def _build_variable_order_chain(
    state_sequence: list[str], state_labels: list[str], context_len: int, laplace: float
) -> dict[int, dict[tuple[str, ...], np.ndarray]]:
    """
    Build conditional distributions P(next_state | previous k states) for k in [0, context_len].
    Includes backoff levels, so if a long context is unseen at inference time we can fall back.
    """
    state_to_i = {s: i for i, s in enumerate(state_labels)}
    n_states = len(state_labels)
    max_k = max(0, int(context_len))
    levels: dict[int, dict[tuple[str, ...], np.ndarray]] = {}

    for k in range(0, max_k + 1):
        if len(state_sequence) <= k:
            continue
        counts_by_ctx: dict[tuple[str, ...], np.ndarray] = {}
        for i in range(k, len(state_sequence)):
            ctx = tuple(state_sequence[i - k : i]) if k > 0 else tuple()
            nxt = state_sequence[i]
            if nxt not in state_to_i:
                continue
            if ctx not in counts_by_ctx:
                counts_by_ctx[ctx] = np.full(n_states, laplace, dtype=float)
            counts_by_ctx[ctx][state_to_i[nxt]] += 1.0

        probs_by_ctx: dict[tuple[str, ...], np.ndarray] = {}
        for ctx, row in counts_by_ctx.items():
            probs_by_ctx[ctx] = row / row.sum()
        levels[k] = probs_by_ctx
    return levels


def _predict_next_distribution(
    history: list[str],
    chain_levels: dict[int, dict[tuple[str, ...], np.ndarray]],
    context_len: int,
) -> np.ndarray:
    for k in range(min(context_len, len(history)), -1, -1):
        ctx = tuple(history[-k:]) if k > 0 else tuple()
        level = chain_levels.get(k, {})
        if ctx in level:
            return level[ctx]
    raise ValueError("Unable to predict next distribution from history")


def _context_key(history: list[str], context_len: int) -> tuple[str, ...]:
    """Suffix of length ``context_len`` — sufficient for variable-order prediction."""
    if len(history) >= context_len:
        return tuple(history[-context_len:])
    return tuple(history)


_MAX_CONTEXT_BRANCHES = 250
_MIN_BRANCH_PROB = 1e-5


def _prune_context_weights(weights: dict[tuple[str, ...], float]) -> dict[tuple[str, ...], float]:
    """Keep the highest-probability context branches to avoid exponential blow-up."""
    if len(weights) <= _MAX_CONTEXT_BRANCHES:
        return weights
    ranked = sorted(weights.items(), key=lambda item: item[1], reverse=True)[:_MAX_CONTEXT_BRANCHES]
    total = sum(w for _, w in ranked)
    if total <= 0:
        return weights
    return {key: w / total for key, w in ranked}


def _project_horizon_variable_order(
    recent_context: list[str],
    state_labels: list[str],
    chain_levels: dict[int, dict[tuple[str, ...], np.ndarray]],
    context_len: int,
    horizon_steps: int,
) -> np.ndarray:
    """Multi-step forecast using variable-order context (last N states), not P^n alone.

    Each step: P(next | last ``context_len`` states) with Laplace backoff.
    Uncertainty is propagated by merging contexts that share the same suffix.
    """
    n = len(state_labels)
    ctx_weights: dict[tuple[str, ...], float] = {
        _context_key(recent_context, context_len): 1.0
    }
    dist = np.zeros(n, dtype=float)

    for step in range(horizon_steps):
        step_dist = np.zeros(n, dtype=float)
        next_weights: dict[tuple[str, ...], float] = {}

        for ctx_key, weight in ctx_weights.items():
            if weight < _MIN_BRANCH_PROB:
                continue
            history = list(ctx_key)
            local_dist = _predict_next_distribution(history, chain_levels, context_len)
            step_dist += weight * local_dist

            if step < horizon_steps - 1:
                for j, label in enumerate(state_labels):
                    branch_prob = weight * float(local_dist[j])
                    if branch_prob < _MIN_BRANCH_PROB:
                        continue
                    extended = list(ctx_key) + [label]
                    new_key = _context_key(extended, context_len)
                    next_weights[new_key] = next_weights.get(new_key, 0.0) + branch_prob

        dist = step_dist
        ctx_weights = _prune_context_weights(next_weights)

    total = float(dist.sum())
    return dist / total if total > 0 else dist


def _compute_equilibrium_distribution(
    transition_matrix: np.ndarray,
    tol: float = 1e-10,
    max_iter: int = 10_000,
) -> tuple[np.ndarray, dict[str, Any]]:
    """Stationary distribution π where π = πP (power iteration, no randomness)."""
    n = transition_matrix.shape[0]
    pi = np.ones(n, dtype=float) / n
    iterations = 0
    converged = False
    for i in range(1, max_iter + 1):
        pi_next = pi @ transition_matrix
        if float(np.linalg.norm(pi_next - pi, ord=1)) < tol:
            pi = pi_next
            iterations = i
            converged = True
            break
        pi = pi_next
        iterations = i
    pi = pi / pi.sum()
    return pi, {
        "iterations": iterations,
        "converged": converged,
        "tolerance": tol,
        "method": "power_iteration",
        "formula": "Repeat transitions until the long-run chances stop changing.",
    }


def _build_calculation_sources(
    *,
    last_close: float,
    expected_return_next_day: float,
    estimated_next_close: float,
    current_state: str,
    current_state_idx: int,
    predicted_state: str,
    confidence: float,
    next_pos_prob: float,
    horizon_steps: int,
    horizon_pos_prob: float,
    expected_return_horizon: float,
    estimated_close_horizon: float,
    equilibrium_meta: dict[str, Any],
    equilibrium_pos_prob: float,
    equilibrium_expected_return: float,
    context_len: int,
    recent_context: list[str],
    return_period: int,
    r_min: float,
    r_max: float,
    n_bins: int,
) -> dict[str, dict[str, Any]]:
    """Provenance for UI: tap a number to see how it was derived."""
    return {
        "estimated_next_close": {
            "method": "markov_forecast",
            "formula": "Last price × (1 + expected next-day return).",
            "description": "Tomorrow's expected closing price based on the Markov forecast.",
            "inputs": {
                "last_close": round(last_close, 6),
                "expected_return_next_day": round(expected_return_next_day, 6),
            },
        },
        "expected_return_next_day": {
            "method": "markov_forecast",
            "formula": "For each possible outcome: (chance × average return) — then add them up.",
            "description": (
                f"Expected return tomorrow, using the last {context_len} return ranges as context."
            ),
            "inputs": {
                "context": recent_context,
                "context_len": context_len,
            },
        },
        "next_positive_probability": {
            "method": "markov_forecast",
            "formula": "Add the chances of all outcomes where return is zero or positive.",
            "description": "Probability of a flat or positive return tomorrow.",
            "inputs": {"current_state": current_state},
        },
        "predicted_state": {
            "method": "markov_forecast",
            "formula": "The return range with the highest probability tomorrow.",
            "description": "The single most likely outcome for the next trading day.",
            "inputs": {
                "predicted_state": predicted_state,
                "confidence": round(confidence, 6),
                "context": recent_context,
            },
        },
        "horizon_positive_probability": {
            "method": "markov_forecast",
            "formula": (
                f"Forecast {horizon_steps} days ahead, then add chances of zero or positive returns."
            ),
            "description": f"Chance the stock ends up flat or up after {horizon_steps} trading days.",
            "inputs": {
                "context": recent_context,
                "context_len": context_len,
                "horizon_steps": horizon_steps,
                "current_state": current_state,
            },
        },
        "distribution_after_horizon": {
            "method": "markov_forecast",
            "formula": f"Step the Markov chain forward {horizon_steps} days — chance of each outcome.",
            "description": "Full probability spread across all return ranges after the forecast period.",
            "inputs": {
                "context": recent_context,
                "context_len": context_len,
                "horizon_steps": horizon_steps,
            },
        },
        "expected_return_horizon": {
            "method": "markov_forecast",
            "formula": "For each horizon outcome: (chance × average return) — then add them up.",
            "description": f"Average expected return over the next {horizon_steps} trading days.",
            "inputs": {"horizon_steps": horizon_steps, "context_len": context_len},
        },
        "estimated_close_horizon": {
            "method": "markov_forecast",
            "formula": "Last price × (1 + expected return over the horizon).",
            "description": f"Expected price after {horizon_steps} trading days.",
            "inputs": {
                "last_close": round(last_close, 6),
                "expected_return_horizon": round(expected_return_horizon, 6),
                "horizon_steps": horizon_steps,
                "context_len": context_len,
            },
        },
        "equilibrium_distribution": {
            "method": "long_run_average",
            "formula": "Repeat transitions until chances settle into a steady long-run pattern.",
            "description": (
                f"Long-run chances across {n_bins} return ranges "
                f"from {r_min * 100:.2f}% to {r_max * 100:.2f}%."
            ),
            "inputs": {
                "return_period_days": return_period,
                "bin_min_percent": round(r_min * 100, 4),
                "bin_max_percent": round(r_max * 100, 4),
                "n_bins": n_bins,
                "iterations": equilibrium_meta.get("iterations"),
                "converged": equilibrium_meta.get("converged"),
                "tolerance": equilibrium_meta.get("tolerance"),
            },
        },
        "equilibrium_expected_return": {
            "method": "long_run_average",
            "formula": "For each long-run outcome: (steady chance × average return) — add up.",
            "description": f"Average {return_period}-day return in the long run.",
            "inputs": {
                "equilibrium_expected_return": round(equilibrium_expected_return, 6),
                "return_period_days": return_period,
            },
        },
        "equilibrium_positive_probability": {
            "method": "long_run_average",
            "formula": "Add long-run chances of all zero or positive return ranges.",
            "description": "Long-run probability of a flat or positive return.",
            "inputs": {"iterations": equilibrium_meta.get("iterations")},
        },
        "confidence": {
            "method": "markov_forecast",
            "formula": "The highest single probability among tomorrow's possible outcomes.",
            "description": "How confident the model is in its top pick for tomorrow.",
            "inputs": {
                "predicted_state": predicted_state,
                "confidence": round(confidence, 6),
            },
        },
    }


def _positive_probability(
    distribution: np.ndarray,
    r_min: float,
    edges: tuple[float, ...],
) -> float:
    """Sum probability mass in bins whose lower bound is >= 0%."""
    bounds = _bin_lower_bounds(r_min, edges)
    p = 0.0
    for i in range(len(distribution)):
        if bounds[i] >= 0:
            p += float(distribution[i])
    return p


def _expected_contributions_dict(
    distribution: np.ndarray, state_mean_returns: dict[str, float], state_labels: list[str]
) -> dict[str, float]:
    out: dict[str, float] = {}
    for i, label in enumerate(state_labels):
        contrib = float(distribution[i]) * float(state_mean_returns.get(label, 0.0))
        out[label] = round(contrib, 6)
    return out


def run_prediction_from_closes(
    close_prices: np.ndarray,
    symbol: str,
    period: str,
    steps: int = 1,
    context_len: int = 5,
    current_price: float | None = None,
) -> dict[str, Any]:
    """Run the Markov chain on a pre-fetched close-price array.

    Useful when the caller has already fetched yfinance data (e.g. the
    /analyze endpoint also wants OHLCV for indicators) and wants to avoid
    a second network round-trip.
    """
    if steps < 1 or steps > 60:
        raise ValueError("steps must be between 1 and 60")
    if context_len < 1 or context_len > 10:
        raise ValueError("context_len must be between 1 and 10")
    if close_prices.size < 3:
        raise ValueError(f"Not enough close observations for {_normalize_symbol(symbol)}")

    returns = _period_returns(close_prices, RETURN_PERIOD_DAYS)
    bin_edges, r_min, r_max = _build_uniform_bin_edges(returns, NUM_RETURN_BINS)
    state_labels = _build_uniform_bin_labels(bin_edges, r_min, r_max)
    states = _returns_to_binned_states(returns, bin_edges, state_labels, r_min, r_max)
    if len(states) <= context_len:
        raise ValueError("Not enough history for requested context_len")

    chain_levels = _build_variable_order_chain(
        state_sequence=states,
        state_labels=state_labels,
        context_len=context_len,
        laplace=1.0,
    )
    state_mean_returns = _state_mean_returns(returns, states, state_labels)

    recent_context = states[-context_len:]
    row = _predict_next_distribution(recent_context, chain_levels, context_len)
    next_idx = int(np.argmax(row))
    confidence = float(row[next_idx])
    expected_return_next_day = float(
        sum(float(row[j]) * state_mean_returns[state] for j, state in enumerate(state_labels))
    )
    last_close = float(close_prices[-1])
    estimated_next_close = last_close * (1.0 + expected_return_next_day)

    first_order_matrix = build_empirical_transition_matrix(states, state_labels)
    current_state_idx = state_labels.index(recent_context[-1])
    dist = _project_horizon_variable_order(
        recent_context=recent_context,
        state_labels=state_labels,
        chain_levels=chain_levels,
        context_len=context_len,
        horizon_steps=steps,
    )
    equilibrium, equilibrium_meta = _compute_equilibrium_distribution(first_order_matrix)

    next_pos_prob = _positive_probability(row, r_min, bin_edges)
    horizon_pos_prob = _positive_probability(dist, r_min, bin_edges)
    equilibrium_pos_prob = _positive_probability(equilibrium, r_min, bin_edges)

    expected_return_horizon = float(
        sum(float(dist[j]) * state_mean_returns[state] for j, state in enumerate(state_labels))
    )
    equilibrium_expected_return = float(
        sum(
            float(equilibrium[j]) * state_mean_returns[state]
            for j, state in enumerate(state_labels)
        )
    )
    estimated_close_horizon = last_close * (1.0 + expected_return_horizon)

    calculation_sources = _build_calculation_sources(
        last_close=last_close,
        expected_return_next_day=expected_return_next_day,
        estimated_next_close=estimated_next_close,
        current_state=recent_context[-1],
        current_state_idx=current_state_idx,
        predicted_state=state_labels[next_idx],
        confidence=confidence,
        next_pos_prob=next_pos_prob,
        horizon_steps=steps,
        horizon_pos_prob=horizon_pos_prob,
        expected_return_horizon=expected_return_horizon,
        estimated_close_horizon=estimated_close_horizon,
        equilibrium_meta=equilibrium_meta,
        equilibrium_pos_prob=equilibrium_pos_prob,
        equilibrium_expected_return=equilibrium_expected_return,
        context_len=context_len,
        recent_context=recent_context,
        return_period=RETURN_PERIOD_DAYS,
        r_min=r_min,
        r_max=r_max,
        n_bins=NUM_RETURN_BINS,
    )
    for i, label in enumerate(state_labels):
        calculation_sources[f"next_state_prob__{i}"] = {
            "method": "markov_forecast",
            "formula": "Chance this return range happens tomorrow.",
            "description": f"Probability for range: {label}.",
            "inputs": {
                "state": label,
                "probability": round(float(row[i]), 6),
                "context": recent_context,
            },
        }
        calculation_sources[f"next_contribution__{i}"] = {
            "method": "markov_forecast",
            "formula": "Chance × average return for this range.",
            "description": f"How much this range ({label}) adds to the expected return.",
            "inputs": {
                "state": label,
                "probability": round(float(row[i]), 6),
                "mean_return": round(state_mean_returns[label], 6),
                "contribution": round(float(row[i]) * state_mean_returns[label], 6),
            },
        }
        calculation_sources[f"horizon_state_prob__{i}"] = {
            "method": "markov_forecast",
            "formula": f"Chance this range happens after {steps} trading days.",
            "description": f"Horizon probability for range: {label}.",
            "inputs": {
                "state": label,
                "probability": round(float(dist[i]), 6),
                "horizon_steps": steps,
                "context_len": context_len,
                "context": recent_context,
            },
        }
        calculation_sources[f"equilibrium_state_prob__{i}"] = {
            "method": "long_run_average",
            "formula": "Long-run steady chance of this return range.",
            "description": f"Equilibrium probability for range: {label}.",
            "inputs": {
                "state": label,
                "probability": round(float(equilibrium[i]), 6),
                "iterations": equilibrium_meta.get("iterations"),
            },
        }

    return {
        "schema_version": 6,
        "model": "uniform_binned_5d_returns_variable_order_markov",
        "horizon_method": "variable_order_context_propagation",
        "symbol": _normalize_symbol(symbol),
        "period": period,
        "return_period_days": RETURN_PERIOD_DAYS,
        "bin_min_percent": round(r_min * 100.0, 4),
        "bin_max_percent": round(r_max * 100.0, 4),
        "n_bins": NUM_RETURN_BINS,
        "bin_edges_percent": [round(x * 100.0, 4) for x in bin_edges],
        "state_labels": state_labels,
        "return_observations": len(returns),
        "state_observations": len(states),
        "context_len": context_len,
        "current_context": recent_context,
        "current_state": recent_context[-1],
        "predicted_state": state_labels[next_idx],
        "confidence": round(confidence, 6),
        "next_state_probabilities": _distribution_dict(row, state_labels),
        "state_mean_returns_percent": {
            k: round(float(v) * 100.0, 4) for k, v in state_mean_returns.items()
        },
        "next_state_expected_contributions": _expected_contributions_dict(
            row, state_mean_returns, state_labels
        ),
        "next_positive_probability": round(next_pos_prob, 6),
        "last_close": round(last_close, 6),
        "current_price": round(float(current_price), 6) if current_price is not None else None,
        "expected_return_next_day": round(expected_return_next_day, 6),
        "estimated_next_close": round(estimated_next_close, 6),
        "horizon_steps": steps,
        "distribution_after_horizon": _distribution_dict(dist, state_labels),
        "horizon_positive_probability": round(horizon_pos_prob, 6),
        "expected_return_horizon": round(expected_return_horizon, 6),
        "estimated_close_horizon": round(estimated_close_horizon, 6),
        "equilibrium_distribution": _distribution_dict(equilibrium, state_labels),
        "equilibrium_positive_probability": round(equilibrium_pos_prob, 6),
        "equilibrium_expected_return": round(equilibrium_expected_return, 6),
        "equilibrium_meta": equilibrium_meta,
        "calculation_sources": calculation_sources,
        "first_order_transition_matrix": _matrix_to_nested_dict(first_order_matrix, state_labels),
    }


def run_prediction(
    symbol: str = "SPY",
    period: str = "2y",
    steps: int = 1,
    context_len: int = 5,
) -> dict[str, Any]:
    """
    Build a variable-order Markov chain from binned daily returns (yfinance), then:
    - current_context: last `context_len` discretized return states (default = 5 trading days)
    - next_state_probabilities: probability over return-range scenarios for the next day
    - distribution_after_horizon: multi-step state distribution via P^steps (deterministic)
    - equilibrium_distribution: stationary distribution π = πP (power iteration)
    """
    close_prices = _price_history(symbol, period)
    current_price = _current_price(symbol)
    return run_prediction_from_closes(
        close_prices=close_prices,
        symbol=symbol,
        period=period,
        steps=steps,
        context_len=context_len,
        current_price=current_price,
    )


def render_graph_png(
    symbol: str = "SPY",
    period: str = "2y",
    edge_threshold: float = 0.05,
) -> bytes:
    """
    Draw a simplified first-order transition graph over binned return states.
    """
    close = _price_history(symbol, period)
    returns = _period_returns(close, RETURN_PERIOD_DAYS)
    bin_edges, r_min, r_max = _build_uniform_bin_edges(returns, NUM_RETURN_BINS)
    state_labels = _build_uniform_bin_labels(bin_edges, r_min, r_max)
    states = _returns_to_binned_states(returns, bin_edges, state_labels, r_min, r_max)
    matrix = build_empirical_transition_matrix(states, state_labels)

    graph = nx.DiGraph()
    for s in state_labels:
        graph.add_node(s)

    for i, src in enumerate(state_labels):
        for j, dst in enumerate(state_labels):
            w = float(matrix[i, j])
            if w >= edge_threshold:
                graph.add_edge(src, dst, weight=w)

    fig, ax = plt.subplots(figsize=(10, 7))
    pos = nx.circular_layout(graph)

    nx.draw_networkx_nodes(
        graph, pos, ax=ax, node_size=2800, node_color="#cfe8ff", edgecolors="#2b5dcf"
    )
    nx.draw_networkx_edges(
        graph,
        pos,
        ax=ax,
        arrowstyle="->",
        arrowsize=18,
        width=2.0,
        edge_color="#5f7b99",
        connectionstyle="arc3,rad=0.1",
    )
    nx.draw_networkx_labels(graph, pos, ax=ax, font_size=12, font_weight="bold")

    edge_labels = {(u, v): f"{d['weight']:.2f}" for u, v, d in graph.edges(data=True)}
    nx.draw_networkx_edge_labels(graph, pos, edge_labels=edge_labels, ax=ax, font_size=10)

    sym = _normalize_symbol(symbol)
    ax.set_title(f"Markov chain ({sym})", fontsize=13)
    ax.axis("off")

    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()
