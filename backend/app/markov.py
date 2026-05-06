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

# Return bins in decimal form:
# e.g. 0.005 = +0.50%
DEFAULT_BIN_EDGES: tuple[float, ...] = (
    -0.03,
    -0.015,
    -0.0075,
    -0.003,
    -0.001,
    0.001,
    0.005,
    0.01,
    0.02,
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


def _build_bin_labels(edges: tuple[float, ...]) -> list[str]:
    bounds = [-math.inf, *edges, math.inf]
    labels: list[str] = []
    for lo, hi in zip(bounds[:-1], bounds[1:]):
        lo_txt = "-inf" if not math.isfinite(lo) else f"{lo * 100:.2f}%"
        hi_txt = "inf" if not math.isfinite(hi) else f"{hi * 100:.2f}%"
        labels.append(f"{lo_txt} to {hi_txt}")
    return labels


def _returns_to_binned_states(
    returns: np.ndarray, edges: tuple[float, ...], labels: list[str]
) -> list[str]:
    states: list[str] = []
    for r in returns:
        idx = int(np.searchsorted(edges, float(r), side="right"))
        states.append(labels[idx])
    return states


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


def _simulate_horizon_distribution(
    history: list[str],
    state_labels: list[str],
    chain_levels: dict[int, dict[tuple[str, ...], np.ndarray]],
    context_len: int,
    horizon_steps: int,
    n_sims: int = 5000,
) -> np.ndarray:
    state_to_i = {s: i for i, s in enumerate(state_labels)}
    final_counts = np.zeros(len(state_labels), dtype=float)
    rng = np.random.default_rng(42)

    for _ in range(n_sims):
        seq = list(history)
        for _step in range(horizon_steps):
            dist = _predict_next_distribution(seq, chain_levels, context_len)
            next_i = int(rng.choice(len(state_labels), p=dist))
            seq.append(state_labels[next_i])
        final_state = seq[-1]
        final_counts[state_to_i[final_state]] += 1.0
    return final_counts / final_counts.sum()


def _positive_probability(
    distribution: np.ndarray, state_labels: list[str], edges: tuple[float, ...]
) -> float:
    # Use lower bound >= 0 to mark a "positive return" state.
    bounds = [-math.inf, *edges, math.inf]
    p = 0.0
    for i in range(len(state_labels)):
        lo = bounds[i]
        if lo >= 0:
            p += float(distribution[i])
    return p


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
    - distribution_after_horizon: multi-step state distribution via Monte Carlo simulation
    """
    if steps < 1 or steps > 60:
        raise ValueError("steps must be between 1 and 60")
    if context_len < 1 or context_len > 10:
        raise ValueError("context_len must be between 1 and 10")

    close_prices = _price_history(symbol, period)
    returns = close_prices[1:] / close_prices[:-1] - 1.0
    state_labels = _build_bin_labels(DEFAULT_BIN_EDGES)
    states = _returns_to_binned_states(returns, DEFAULT_BIN_EDGES, state_labels)
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
    current_price = _current_price(symbol)

    dist = _simulate_horizon_distribution(
        history=recent_context,
        state_labels=state_labels,
        chain_levels=chain_levels,
        context_len=context_len,
        horizon_steps=steps,
    )
    next_pos_prob = _positive_probability(row, state_labels, DEFAULT_BIN_EDGES)
    horizon_pos_prob = _positive_probability(dist, state_labels, DEFAULT_BIN_EDGES)
    first_order_matrix = build_empirical_transition_matrix(states, state_labels)

    return {
        "schema_version": 3,
        "model": "empirical_binned_returns_variable_order_markov",
        "symbol": _normalize_symbol(symbol),
        "period": period,
        "bin_edges_percent": [round(x * 100.0, 4) for x in DEFAULT_BIN_EDGES],
        "state_labels": state_labels,
        "return_observations": len(returns),
        "state_observations": len(states),
        "context_len": context_len,
        "current_context": recent_context,
        "current_state": recent_context[-1],
        "predicted_state": state_labels[next_idx],
        "confidence": round(confidence, 6),
        "next_state_probabilities": _distribution_dict(row, state_labels),
        "next_positive_probability": round(next_pos_prob, 6),
        "last_close": round(last_close, 6),
        "current_price": round(float(current_price), 6) if current_price is not None else None,
        "expected_return_next_day": round(expected_return_next_day, 6),
        "estimated_next_close": round(estimated_next_close, 6),
        "horizon_steps": steps,
        "distribution_after_horizon": _distribution_dict(dist, state_labels),
        "horizon_positive_probability": round(horizon_pos_prob, 6),
        "first_order_transition_matrix": _matrix_to_nested_dict(first_order_matrix, state_labels),
    }


def render_graph_png(
    symbol: str = "SPY",
    period: str = "2y",
    edge_threshold: float = 0.05,
) -> bytes:
    """
    Draw a simplified first-order transition graph over binned return states.
    """
    returns = _daily_simple_returns(symbol, period)
    state_labels = _build_bin_labels(DEFAULT_BIN_EDGES)
    states = _returns_to_binned_states(returns, DEFAULT_BIN_EDGES, state_labels)
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
    ax.set_title(
        f"Empirical Markov chain ({sym}, {period}, binned return states)\n"
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
