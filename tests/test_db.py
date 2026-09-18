import threading
import time

import pytest

from noisy_neighbor.db import ConnectionBudget


def test_connection_budget_allows_up_to_limit():
    budget = ConnectionBudget(limits={1: 2})
    with budget.acquire(1):
        with budget.acquire(1):
            pass  # both should succeed without raising


def test_connection_budget_rejects_over_limit():
    budget = ConnectionBudget(limits={1: 1})
    got_timeout = threading.Event()

    def hold_slot():
        with budget.acquire(1):
            time.sleep(0.5)

    holder = threading.Thread(target=hold_slot)
    holder.start()
    time.sleep(0.05)  # let holder acquire first

    with pytest.raises(TimeoutError):
        with budget.acquire(1, timeout=0.1):
            pass
    holder.join()


def test_connection_budget_is_per_tenant():
    # Tenant 1 being at its limit must not block tenant 2.
    budget = ConnectionBudget(limits={1: 1, 2: 1})
    with budget.acquire(1):
        with budget.acquire(2):
            pass  # tenant 2's slot is independent of tenant 1's
