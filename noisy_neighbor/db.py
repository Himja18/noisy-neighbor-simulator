"""
Connection handling for the shared multi-tenant database.

Two mitigations live here because they are both fundamentally about how a
connection is granted or configured, not about the query itself:

  1. ConnectionBudget -- caps how many concurrent connections any single
     tenant can hold against the shared instance, so one tenant cannot
     starve the connection pool that everyone else depends on.
  2. statement_timeout -- killed server-side, so a runaway query cannot
     hold a lock or consume CPU/I/O indefinitely regardless of what the
     client does afterward.
"""
from __future__ import annotations

import os
import threading
from contextlib import contextmanager
from dataclasses import dataclass, field

import psycopg2
import psycopg2.extras


@dataclass
class DBConfig:
    host: str = "localhost"
    port: int = int(os.environ.get("NN_DB_PORT", 5432))
    dbname: str = "noisyneighbor"
    user: str = "postgres"
    password: str = "postgres"


class ConnectionBudget:
    """
    Per-tenant connection cap, shared across threads.

    Without this, a tenant that opens (or leaks) many connections can
    exhaust the database's max_connections limit and lock out every other
    tenant, independent of query speed. A semaphore per tenant_id is the
    simplest correct way to bound that -- it fails a tenant's own request
    the moment they're over budget, rather than letting Postgres itself
    become the bottleneck for everyone.
    """

    def __init__(self, limits: dict[int, int] | None = None, default_limit: int = 100):
        self._default_limit = default_limit
        self._limits = limits or {}
        self._semaphores: dict[int, threading.Semaphore] = {}
        self._lock = threading.Lock()

    def _semaphore_for(self, tenant_id: int) -> threading.Semaphore:
        with self._lock:
            if tenant_id not in self._semaphores:
                limit = self._limits.get(tenant_id, self._default_limit)
                self._semaphores[tenant_id] = threading.Semaphore(limit)
            return self._semaphores[tenant_id]

    @contextmanager
    def acquire(self, tenant_id: int, timeout: float = 5.0):
        sem = self._semaphore_for(tenant_id)
        acquired = sem.acquire(timeout=timeout)
        if not acquired:
            raise TimeoutError(
                f"tenant {tenant_id} exceeded its connection budget "
                f"({self._limits.get(tenant_id, self._default_limit)} concurrent)"
            )
        try:
            yield
        finally:
            sem.release()


def get_connection(config: DBConfig, statement_timeout_ms: int | None = None):
    """
    Open a raw connection. When statement_timeout_ms is set, Postgres
    itself will abort any query on this connection that runs longer than
    the timeout -- this protects the *server* even if the noisy tenant's
    client code never gives up.
    """
    conn = psycopg2.connect(
        host=config.host,
        port=config.port,
        dbname=config.dbname,
        user=config.user,
        password=config.password,
    )
    if statement_timeout_ms is not None:
        with conn.cursor() as cur:
            cur.execute(f"SET statement_timeout = {int(statement_timeout_ms)}")
    return conn
