# AI_USE.md

## What AI was used for

I used Claude to scaffold this project: the initial class structure
(`Tenant`/`Workload` split, `ConnectionBudget`, the benchmark harness) and
the first draft of the unit tests. I decided the actual experiment design
myself — the three scenarios, what "noisy" should mean (a genuinely
larger tenant with a realistic unindexed analytics query, not an
artificial stress test), and the interpretation of the results.

## What was done without AI

- Running every experiment against a real, locally running Postgres
  instance and reading the actual output — none of the numbers in
  `README.md` or `results/results.json` are estimated or invented.
- Reading the `EXPLAIN ANALYZE` output myself to understand *why* the
  index-isolation scenario didn't move the good-tenant latency, rather
  than accepting "added the index" as sufficient.
- Deciding which mitigation to recommend based on what the data actually
  showed, which was not what I expected going in (see README's "The
  finding I didn't expect" section).

## A wrong AI output, and how I caught it

The first draft of `tests/test_metrics.py` included this assertion:

```python
values = [1.0, 2.0, float("inf")]
s = summarize(values)
assert s["p50_ms"] == 2.0
```

This is wrong: the median of two finite values `[1.0, 2.0]` under linear
interpolation is `1.5`, not `2.0`. The test was written assuming
"round up to the next actual value" behavior that the `percentile()`
function doesn't implement (and shouldn't — standard percentile
definitions interpolate).

I caught this by actually running `pytest`, not by re-reading the code:

```
FAILED tests/test_metrics.py::test_summarize_reports_timeout_as_string
assert 1.5 == 2.0
```

The fix was to correct the test's expected value to `1.5`, not to change
`percentile()` — the implementation was right, my generated test's
assumption about it was wrong. This is the same category of mistake as
the DATA260 assignment's `finalize()` bug: an AI-authored assumption that
looked reasonable until it was checked against actual execution.

## Takeaway

Every number in this repo's README came from running real code against a
real database, not from asking an AI what the result "should" be. The one
AI-generated artifact that turned out to be wrong (the test assertion)
was caught the same way the empirical finding about indexing was reached:
by running the thing and checking, not by trusting the first plausible
answer.
