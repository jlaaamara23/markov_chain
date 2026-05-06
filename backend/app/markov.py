from __future__ import annotations

import io
from typing import Any

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import networkx as nx
import numpy as np

from app.ticker_util import normalize_equity_symbol

# Ordered labels for the empirical daily-return Markov chain
STATE_LABELS: tuple[str, ...] = ("down", "flat", "up")
CONTEXT_LABELS: tuple[tuple[str, str], ...] = tuple(
    (a, b) for a in STATE_LABELS for b in STATE_LABELS
)


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


def _returns_to_states(returns: np.ndarray, threshold: float) -> list[str]:
    """Map each daily simple return to down / flat / up using symmetric thresholds."""
    if threshold <= 0:
        raise ValueError("threshold must be positive")
    states: list[str] = []
    for r in returns:
        if r < -threshold:
            states.append("down")
        elif r > threshold:
            states.append("up")
        else:
            states.append("flat")
    return states


def build_empirical_transition_matrix(
    state_sequence: list[str],
    laplace: float = 1.0,
) -> np.ndarray:
    """
    Count transitions i -> j, apply Laplace smoothing, row-normalize to probabilities.
    """
    if len(state_sequence) < 2:
        raise ValueError("Need at least two states to estimate transitions")
    index = {s: i for i, s in enumerate(STATE_LABELS)}
    n = len(STATE_LABELS)
    counts = np.full((n, n), laplace, dtype=float)
    for a, b in zip(state_sequence[:-1], state_sequence[1:]):
        if a in index and b in index:
            counts[index[a], index[b]] += 1.0
    row_sums = counts.sum(axis=1, keepdims=True)
    return counts / row_sums


def build_second_order_transition_matrix(
    state_sequence: list[str],
    laplace: float = 1.0,
) -> np.ndarray:
    """
    Estimate P(s_t | s_{t-2}, s_{t-1}) with Laplace smoothing.

    Returns a 9x3 matrix where rows are (prev2, prev1) contexts and columns are next-state probs.
    """
    if len(state_sequence) < 3:
        raise ValueError("Need at least three states to estimate second-order transitions")

    context_index = {ctx: i for i, ctx in enumerate(CONTEXT_LABELS)}
    state_index = {s: i for i, s in enumerate(STATE_LABELS)}

    counts = np.full((len(CONTEXT_LABELS), len(STATE_LABELS)), laplace, dtype=float)
    for a, b, c in zip(state_sequence[:-2], state_sequence[1:-1], state_sequence[2:]):
        if (a, b) in context_index and c in state_index:
            counts[context_index[(a, b)], state_index[c]] += 1.0

    row_sums = counts.sum(axis=1, keepdims=True)
    return counts / row_sums


def _matrix_to_nested_dict(matrix: np.ndarray) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, si in enumerate(STATE_LABELS):
        out[si] = {
            sj: round(float(matrix[i, j]), 6) for j, sj in enumerate(STATE_LABELS)
        }
    return out


def _second_order_matrix_to_nested_dict(matrix: np.ndarray) -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for i, (a, b) in enumerate(CONTEXT_LABELS):
        out[f"{a}|{b}"] = {
            sj: round(float(matrix[i, j]), 6) for j, sj in enumerate(STATE_LABELS)
        }
    return out


def _distribution_dict(vec: np.ndarray) -> dict[str, float]:
    return {STATE_LABELS[i]: round(float(vec[i]), 6) for i in range(len(STATE_LABELS))}


def _state_mean_returns(returns: np.ndarray, states: list[str]) -> dict[str, float]:
    sums = {s: 0.0 for s in STATE_LABELS}
    counts = {s: 0 for s in STATE_LABELS}
    for r, s in zip(returns, states):
        if s in sums:
            sums[s] += float(r)
            counts[s] += 1

    out: dict[str, float] = {}
    for s in STATE_LABELS:
        out[s] = (sums[s] / counts[s]) if counts[s] > 0 else 0.0
    return out


def _build_context_transition_matrix(second_order_matrix: np.ndarray) -> np.ndarray:
    """
    Build 9x9 context transition matrix for contexts (a,b) -> (b,c),
    where probability is P(c | a,b).
    """
    context_index = {ctx: i for i, ctx in enumerate(CONTEXT_LABELS)}
    state_index = {s: i for i, s in enumerate(STATE_LABELS)}

    n_ctx = len(CONTEXT_LABELS)
    out = np.zeros((n_ctx, n_ctx), dtype=float)
    for i, (a, b) in enumerate(CONTEXT_LABELS):
        _ = a  # keep tuple unpacking explicit for readability
        for c in STATE_LABELS:
            next_ctx = (b, c)
            j = context_index[next_ctx]
            out[i, j] += float(second_order_matrix[i, state_index[c]])
    return out


def _context_distribution_to_state_distribution(context_dist: np.ndarray) -> np.ndarray:
    """Marginalize context distribution to state distribution of the second state in each context."""
    state_index = {s: i for i, s in enumerate(STATE_LABELS)}
    out = np.zeros(len(STATE_LABELS), dtype=float)
    for i, (_, b) in enumerate(CONTEXT_LABELS):
        out[state_index[b]] += float(context_dist[i])
    return out


def run_prediction(
    symbol: str = "SPY",
    period: str = "2y",
    steps: int = 1,
    threshold: float = 0.003,
) -> dict[str, Any]:
    """
    Build a second-order Markov chain from daily returns (yfinance), then:
    - current_state: discretized state on the last observed day
    - predicted_state: argmax of P(next | last_two_states)
    - distribution_after_steps: state distribution after `steps` days from the current context
    """
    if steps < 1 or steps > 60:
        raise ValueError("steps must be between 1 and 60")

    close_prices = _price_history(symbol, period)
    returns = close_prices[1:] / close_prices[:-1] - 1.0
    states = _returns_to_states(returns, threshold)
    matrix = build_second_order_transition_matrix(states)
    state_mean_returns = _state_mean_returns(returns, states)

    last_two = (states[-2], states[-1])
    context_index = {ctx: i for i, ctx in enumerate(CONTEXT_LABELS)}
    idx = context_index[last_two]
    row = matrix[idx]
    next_idx = int(np.argmax(row))
    confidence = float(row[next_idx])
    expected_return_next_day = float(
        sum(float(row[j]) * state_mean_returns[state] for j, state in enumerate(STATE_LABELS))
    )
    last_close = float(close_prices[-1])
    estimated_next_close = last_close * (1.0 + expected_return_next_day)
    current_price = _current_price(symbol)

    # Multi-step distribution using context transition matrix.
    context_transition = _build_context_transition_matrix(matrix)
    e = np.zeros(len(CONTEXT_LABELS))
    e[idx] = 1.0
    power = np.linalg.matrix_power(context_transition, steps)
    context_dist = e @ power
    dist = _context_distribution_to_state_distribution(context_dist)

    return {
        "schema_version": 2,
        "model": "empirical_daily_returns_second_order",
        "symbol": _normalize_symbol(symbol),
        "period": period,
        "threshold": threshold,
        "return_observations": len(returns),
        "state_observations": len(states),
        "current_context": {"prev2": last_two[0], "prev1": last_two[1]},
        "current_state": last_two[1],
        "predicted_state": STATE_LABELS[next_idx],
        "confidence": round(confidence, 6),
        "next_state_probabilities": _distribution_dict(row),
        "last_close": round(last_close, 6),
        "current_price": round(float(current_price), 6) if current_price is not None else None,
        "expected_return_next_day": round(expected_return_next_day, 6),
        "estimated_next_close": round(estimated_next_close, 6),
        "horizon_steps": steps,
        "distribution_after_horizon": _distribution_dict(dist),
        "transition_matrix": _second_order_matrix_to_nested_dict(matrix),
        "first_order_transition_matrix": _matrix_to_nested_dict(
            build_empirical_transition_matrix(states)
        ),
    }


def render_graph_png(
    symbol: str = "SPY",
    period: str = "2y",
    threshold: float = 0.003,
    edge_threshold: float = 0.05,
) -> bytes:
    """
    Draw the empirical 3-state transition graph (weights = probabilities).
    """
    returns = _daily_simple_returns(symbol, period)
    states = _returns_to_states(returns, threshold)
    matrix = build_empirical_transition_matrix(states)

    graph = nx.DiGraph()
    for s in STATE_LABELS:
        graph.add_node(s)

    for i, src in enumerate(STATE_LABELS):
        for j, dst in enumerate(STATE_LABELS):
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
    ax.set_title(
        f"Empirical Markov chain ({sym}, {period}, |r|>{threshold:.4f} → flat)\n"
        f"Edges shown if P ≥ {edge_threshold:.2f}",
        fontsize=13,
    )
    ax.axis("off")

    buffer = io.BytesIO()
    fig.tight_layout()
    fig.savefig(buffer, format="png", dpi=150)
    plt.close(fig)
    buffer.seek(0)
    return buffer.getvalue()
