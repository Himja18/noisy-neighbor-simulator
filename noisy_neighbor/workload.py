"""
Tenant and Workload abstractions.

Each tenant runs a Workload: a repeatable unit of query traffic against the
shared database. Splitting "who is running traffic" (Tenant) from "what
traffic they run" (Workload) keeps the simulator able to mix and match --
e.g. run the same GoodTenantWorkload for five tenants while one runs
NoisyTenantWorkload, without any tenant-specific branching elsewhere.
"""
from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass

from .db import DBConfig, get_connection


@dataclass(frozen=True)
class Tenant:
    tenant_id: int
    name: str
    is_noisy: bool = False


class Workload(ABC):
    """A repeatable query pattern run on behalf of one tenant."""

    def __init__(self, tenant: Tenant):
        self.tenant = tenant

    @abstractmethod
    def query(self) -> tuple[str, tuple]:
        """Return (sql, params) for one iteration of this workload."""
        raise NotImplementedError

    def run_once(self, config: DBConfig, statement_timeout_ms: int | None = None) -> float:
        """
        Execute one iteration and return latency in milliseconds.
        Returns float('inf') if the statement was killed by
        statement_timeout, so callers can distinguish "slow" from "killed".
        """
        sql, params = self.query()
        conn = get_connection(config, statement_timeout_ms=statement_timeout_ms)
        try:
            start = time.perf_counter()
            with conn.cursor() as cur:
                cur.execute(sql, params)
                cur.fetchall()
            conn.commit()
            return (time.perf_counter() - start) * 1000
        except Exception:
            conn.rollback()
            return float("inf")
        finally:
            conn.close()


class GoodTenantWorkload(Workload):
    """
    A well-behaved tenant's hot-path query: fetch a customer's recent
    orders. Uses the tenant_id + created_at index, so in isolation this
    is fast and stays fast as data grows.
    """

    def query(self) -> tuple[str, tuple]:
        sql = """
            SELECT order_id, customer_id, created_at, status
            FROM orders
            WHERE tenant_id = %s
            ORDER BY created_at DESC
            LIMIT 20
        """
        return sql, (self.tenant.tenant_id,)


class NoisyTenantWorkload(Workload):
    """
    A pathological analytics-style query: total quantity sold per product
    category, joined across order_items -> orders -> products. Because
    order_items has no index on (tenant_id, order_id) or (product_id),
    Postgres must sequentially scan and hash-join large portions of a
    table that is shared with every other tenant -- this is the "noise."

    This is a realistic shape of bug, not a contrived one: an ad-hoc
    reporting query someone wrote once for their own dashboard, on a
    table nobody indexed for that access pattern.
    """

    def query(self) -> tuple[str, tuple]:
        sql = """
            SELECT p.category, SUM(oi.quantity) AS total_qty
            FROM order_items oi
            JOIN orders o ON o.order_id = oi.order_id
            JOIN products p ON p.product_id = oi.product_id
            WHERE oi.tenant_id = %s
            GROUP BY p.category
        """
        return sql, (self.tenant.tenant_id,)
