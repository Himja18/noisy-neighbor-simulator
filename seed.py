"""
Seed the shared database with N well-behaved tenants and 1 noisy tenant.

The noisy tenant gets disproportionately more order_items rows -- this
mirrors a real pattern: one customer's account genuinely grows faster
than the others, and nobody revisits the schema's indexing decisions as
that happens.
"""
import random
from datetime import datetime, timedelta

import psycopg2
from faker import Faker

from noisy_neighbor.db import DBConfig

fake = Faker()
Faker.seed(1346)
random.seed(1346)

GOOD_TENANT_COUNT = 5
GOOD_TENANT_PRODUCTS = 200
GOOD_TENANT_ORDERS = 5_000
GOOD_TENANT_ITEMS_PER_ORDER = 3

NOISY_TENANT_PRODUCTS = 500
NOISY_TENANT_ORDERS = 80_000
NOISY_TENANT_ITEMS_PER_ORDER = 4

CATEGORIES = ["electronics", "home", "apparel", "toys", "grocery", "sports"]


def seed():
    config = DBConfig()
    conn = psycopg2.connect(
        host=config.host, port=config.port, dbname=config.dbname,
        user=config.user, password=config.password,
    )
    cur = conn.cursor()

    with open("schema.sql") as f:
        cur.execute(f.read())
    conn.commit()

    tenant_ids = []
    for i in range(GOOD_TENANT_COUNT):
        cur.execute(
            "INSERT INTO tenants (name, is_noisy) VALUES (%s, %s) RETURNING tenant_id",
            (f"good-tenant-{i+1}", False),
        )
        tenant_ids.append((cur.fetchone()[0], False))
    cur.execute(
        "INSERT INTO tenants (name, is_noisy) VALUES (%s, %s) RETURNING tenant_id",
        ("noisy-tenant", True),
    )
    noisy_id = cur.fetchone()[0]
    tenant_ids.append((noisy_id, True))
    conn.commit()

    for tenant_id, is_noisy in tenant_ids:
        n_products = NOISY_TENANT_PRODUCTS if is_noisy else GOOD_TENANT_PRODUCTS
        n_orders = NOISY_TENANT_ORDERS if is_noisy else GOOD_TENANT_ORDERS
        items_per_order = NOISY_TENANT_ITEMS_PER_ORDER if is_noisy else GOOD_TENANT_ITEMS_PER_ORDER

        product_ids = []
        rows = [
            (tenant_id, fake.word() + " " + fake.word(), random.randint(500, 20000), random.choice(CATEGORIES))
            for _ in range(n_products)
        ]
        # executemany doesn't support RETURNING cleanly, so insert one by one.
        for r in rows:
            cur.execute(
                "INSERT INTO products (tenant_id, name, price_cents, category) VALUES (%s,%s,%s,%s) RETURNING product_id",
                r,
            )
            product_ids.append(cur.fetchone()[0])
        conn.commit()

        base_date = datetime(2025, 1, 1)
        order_ids = []
        batch = []
        for i in range(n_orders):
            created = base_date + timedelta(minutes=random.randint(0, 60 * 24 * 240))
            batch.append((tenant_id, random.randint(1, 5000), created, random.choice(["placed", "shipped", "delivered", "cancelled"])))
            if len(batch) >= 2000:
                cur.executemany(
                    "INSERT INTO orders (tenant_id, customer_id, created_at, status) VALUES (%s,%s,%s,%s)",
                    batch,
                )
                conn.commit()
                batch = []
        if batch:
            cur.executemany(
                "INSERT INTO orders (tenant_id, customer_id, created_at, status) VALUES (%s,%s,%s,%s)",
                batch,
            )
            conn.commit()

        cur.execute("SELECT order_id FROM orders WHERE tenant_id = %s", (tenant_id,))
        order_ids = [r[0] for r in cur.fetchall()]

        item_batch = []
        for oid in order_ids:
            for _ in range(items_per_order):
                pid = random.choice(product_ids)
                item_batch.append((oid, pid, tenant_id, random.randint(1, 5)))
                if len(item_batch) >= 5000:
                    cur.executemany(
                        "INSERT INTO order_items (order_id, product_id, tenant_id, quantity) VALUES (%s,%s,%s,%s)",
                        item_batch,
                    )
                    conn.commit()
                    item_batch = []
        if item_batch:
            cur.executemany(
                "INSERT INTO order_items (order_id, product_id, tenant_id, quantity) VALUES (%s,%s,%s,%s)",
                item_batch,
            )
            conn.commit()

        print(f"seeded tenant_id={tenant_id} noisy={is_noisy} products={n_products} orders={n_orders} items~={n_orders*items_per_order}")

    cur.execute("ANALYZE;")
    conn.commit()
    cur.close()
    conn.close()
    return tenant_ids


if __name__ == "__main__":
    ids = seed()
    print("DONE", ids)
