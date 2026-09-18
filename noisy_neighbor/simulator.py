"""
Runs tenant workloads concurrently against the shared database and
records per-tenant latencies, so we can measure how much a noisy
tenant's traffic degrades a good tenant's latency -- with and without
mitigations applied.
"""
from __future__ import annotations

import threading
import time
from dataclasses import dataclass, field

from .db import ConnectionBudget, DBConfig
from .workload import Workload


@dataclass
class MitigationConfig:
    """Toggle each mitigation independently so their effects can be
    measured separately, not just as an all-or-nothing bundle."""
    connection_budget: ConnectionBudget | None = None
    statement_timeout_ms: int | None = None


@dataclass
class RunResult:
    tenant_id: int
    label: str  # "good" or "noisy"
    latencies_ms: list = field(default_factory=list)


def _run_workload_for_duration(
    workload: Workload,
    config: DBConfig,
    duration_s: float,
    mitigation: MitigationConfig,
    result: RunResult,
):
    end_at = time.monotonic() + duration_s
    while time.monotonic() < end_at:
        try:
            if mitigation.connection_budget is not None:
                with mitigation.connection_budget.acquire(workload.tenant.tenant_id):
                    latency = workload.run_once(config, mitigation.statement_timeout_ms)
            else:
                latency = workload.run_once(config, mitigation.statement_timeout_ms)
        except TimeoutError:
            latency = float("inf")  # connection budget rejected the request
        result.latencies_ms.append(latency)


def run_concurrent_simulation(
    good_workloads: list[Workload],
    noisy_workload: Workload,
    config: DBConfig,
    duration_s: float = 8.0,
    mitigation: MitigationConfig | None = None,
) -> dict[str, RunResult]:
    """
    Runs every good tenant's workload in its own thread, plus the noisy
    tenant's workload in its own thread(s), all concurrently for
    duration_s seconds. Returns latency samples per tenant.
    """
    mitigation = mitigation or MitigationConfig()
    results: dict[str, RunResult] = {}
    threads = []

    for wl in good_workloads:
        r = RunResult(tenant_id=wl.tenant.tenant_id, label="good")
        results[f"good-{wl.tenant.tenant_id}"] = r
        t = threading.Thread(target=_run_workload_for_duration, args=(wl, config, duration_s, mitigation, r))
        threads.append(t)

    noisy_r = RunResult(tenant_id=noisy_workload.tenant.tenant_id, label="noisy")
    results[f"noisy-{noisy_workload.tenant.tenant_id}"] = noisy_r
    # The noisy tenant fires several concurrent instances of its own bad
    # query, since a real noisy neighbor rarely sends just one request.
    for _ in range(4):
        t = threading.Thread(
            target=_run_workload_for_duration,
            args=(noisy_workload, config, duration_s, mitigation, noisy_r),
        )
        threads.append(t)

    for t in threads:
        t.start()
    for t in threads:
        t.join()

    return results
