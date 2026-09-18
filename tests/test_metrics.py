import math

from noisy_neighbor.metrics import percentile, summarize


def test_percentile_basic():
    values = [10, 20, 30, 40, 50]
    assert percentile(values, 50) == 30
    assert percentile(values, 0) == 10
    assert percentile(values, 100) == 50


def test_percentile_empty():
    assert math.isnan(percentile([], 50))


def test_percentile_with_timeouts_in_tail():
    # 10 values, 3 are inf (timeouts). p95 rank falls inside the inf tail,
    # so it must report inf rather than silently returning a finite number.
    values = [1, 2, 3, 4, 5, 6, 7] + [float("inf")] * 3
    assert percentile(values, 95) == float("inf")
    assert percentile(values, 50) != float("inf")


def test_summarize_reports_timeout_as_string():
    values = [1.0, 2.0, float("inf")]
    s = summarize(values)
    assert s["count"] == 3
    assert s["timeouts_or_rejections"] == 1
    assert s["p50_ms"] == 1.5  # linear interpolation between the two finite values
