"""
Runs the noisy-neighbor experiment across three scenarios and writes
results/results.json:

  1. baseline        -- no mitigations, noisy tenant runs freely
  2. conn_timeout     -- per-tenant connection budget + statement_timeout
  3. index_isolation -- (1) plus a covering index that fixes the noisy
                        tenant's own query, removing the root cause
                        rather than just containing its blast radius

Scenario 3 exists because mitigations 1 and 2 only limit *how much*
damage a slow query can do -- they don't make the noisy tenant's own
query fast. Fixing the actual query is usually the better first move;
connection budgets and timeouts are what you fall back on when you
can't fix the query (e.g. it's ad-hoc, tenant-authored, or third-party).
"""
import json
import time

import psycopg2

from noisy_neighbor.db import ConnectionBudget, DBConfig
from noisy_neighbor.metrics import summarize
from noisy_neighbor.simulator import MitigationConfig, run_concurrent_simulation
from noisy_neighbor.workload import GoodTenantWorkload, NoisyTenantWorkload, Tenant

DURATION_S = 8.0


def get_tenants(config: DBConfig):
    conn = psycopg2.connect(
        host=config.host, port=config.port, dbname=config.dbname,
        user=config.user, password=config.password,
    )
    cur = conn.cursor()
    cur.execute("SELECT tenant_id, name, is_noisy FROM tenants ORDER BY tenant_id")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    good = [Tenant(r[0], r[1], r[2]) for r in rows if not r[2]]
    noisy = [Tenant(r[0], r[1], r[2]) for r in rows if r[2]][0]
    return good, noisy


def apply_index_isolation(config: DBConfig):
    """The actual fix: index the columns the noisy query joins/filters on."""
    conn = psycopg2.connect(
        host=config.host, port=config.port, dbname=config.dbname,
        user=config.user, password=config.password,
    )
    cur = conn.cursor()
    cur.execute("CREATE INDEX IF NOT EXISTS idx_order_items_tenant_order ON order_items(tenant_id, order_id);")
    cur.execute("CREATE INDEX IF NOT EXISTS idx_order_items_product ON order_items(product_id);")
    conn.commit()
    cur.execute("ANALYZE order_items;")
    conn.commit()
    cur.close()
    conn.close()


def drop_index_isolation(config: DBConfig):
    conn = psycopg2.connect(
        host=config.host, port=config.port, dbname=config.dbname,
        user=config.user, password=config.password,
    )
    cur = conn.cursor()
    cur.execute("DROP INDEX IF EXISTS idx_order_items_tenant_order;")
    cur.execute("DROP INDEX IF EXISTS idx_order_items_product;")
    conn.commit()
    cur.close()
    conn.close()


def run_scenario(name: str, config: DBConfig, mitigation: MitigationConfig) -> dict:
    good_tenants, noisy_tenant = get_tenants(config)
    good_workloads = [GoodTenantWorkload(t) for t in good_tenants]
    noisy_workload = NoisyTenantWorkload(noisy_tenant)

    print(f"--- scenario: {name} ---")
    start = time.monotonic()
    results = run_concurrent_simulation(
        good_workloads, noisy_workload, config,
        duration_s=DURATION_S, mitigation=mitigation,
    )
    wall_s = time.monotonic() - start

    good_all_latencies = []
    for key, r in results.items():
        if r.label == "good":
            good_all_latencies.extend(r.latencies_ms)
    noisy_latencies = [r.latencies_ms for r in results.values() if r.label == "noisy"][0]

    scenario_result = {
        "scenario": name,
        "wall_seconds": round(wall_s, 2),
        "good_tenants_combined": summarize(good_all_latencies),
        "noisy_tenant": summarize(noisy_latencies),
    }
    print(json.dumps(scenario_result, indent=2))
    return scenario_result


def main():
    config = DBConfig()
    drop_index_isolation(config)  # ensure clean baseline state

    all_results = {}

    # Scenario 1: baseline, no mitigation at all.
    all_results["baseline"] = run_scenario("baseline", config, MitigationConfig())

    # Scenario 2: connection budget + statement timeout, index NOT fixed.
    budget = ConnectionBudget(limits={}, default_limit=100)
    noisy_id = get_tenants(config)[1].tenant_id
    budget = ConnectionBudget(limits={noisy_id: 2}, default_limit=100)
    mitigation = MitigationConfig(connection_budget=budget, statement_timeout_ms=2000)
    all_results["conn_timeout"] = run_scenario("conn_timeout", config, mitigation)

    # Scenario 3: fix the actual root cause with the missing index.
    apply_index_isolation(config)
    all_results["index_isolation"] = run_scenario("index_isolation", config, MitigationConfig())

    with open("results/results.json", "w") as f:
        json.dump(all_results, f, indent=2)
    print("Saved results/results.json")


if __name__ == "__main__":
    main()
