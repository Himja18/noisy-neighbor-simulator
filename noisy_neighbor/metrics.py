"""Latency statistics used across benchmark scenarios."""
from __future__ import annotations

import math


def percentile(values: list[float], pct: float) -> float:
    """
    Simple linear-interpolation percentile. inf values (timed-out or
    budget-rejected requests) are kept in the list deliberately -- a
    rejected/killed request is a real latency outcome from the caller's
    point of view, not something to discard from the distribution.
    """
    if not values:
        return float("nan")
    finite = sorted(v for v in values if math.isfinite(v))
    n_inf = len(values) - len(finite)
    if not finite:
        return float("inf")
    k = (pct / 100) * (len(finite) - 1)
    f = math.floor(k)
    c = math.ceil(k)
    if f == c:
        base = finite[int(k)]
    else:
        base = finite[f] + (finite[c] - finite[f]) * (k - f)
    # If enough of the tail is inf that this percentile falls in it, report inf.
    rank = int(math.ceil((pct / 100) * len(values))) - 1
    sorted_all = sorted(values, key=lambda v: (v != v, v))  # nan-safe, inf sorts last naturally
    if rank >= len(values) - n_inf:
        return float("inf")
    return base


def _json_safe(v: float):
    # Plain "Infinity" is not valid JSON; represent it as a string so
    # results.json can be parsed by standard JSON tooling.
    if math.isinf(v):
        return "TIMEOUT"
    if math.isnan(v):
        return None
    return round(v, 1)


def summarize(values: list[float]) -> dict:
    n_timeout = sum(1 for v in values if not math.isfinite(v))
    return {
        "count": len(values),
        "timeouts_or_rejections": n_timeout,
        "p50_ms": _json_safe(percentile(values, 50)),
        "p95_ms": _json_safe(percentile(values, 95)),
        "p99_ms": _json_safe(percentile(values, 99)),
    }
