-- Multi-tenant schema: all tenants share one Postgres instance and these
-- tables, distinguished only by tenant_id. This is the common "pooled"
-- multi-tenancy model used by many real SaaS systems because it's cheap
-- to operate, but it means tenants share buffer cache, disk I/O, and lock
-- contention -- one tenant's bad query can degrade latency for everyone.

DROP TABLE IF EXISTS order_items CASCADE;
DROP TABLE IF EXISTS orders CASCADE;
DROP TABLE IF EXISTS products CASCADE;
DROP TABLE IF EXISTS tenants CASCADE;

CREATE TABLE tenants (
    tenant_id   SERIAL PRIMARY KEY,
    name        TEXT NOT NULL,
    is_noisy    BOOLEAN NOT NULL DEFAULT FALSE
);

CREATE TABLE products (
    product_id  SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(tenant_id),
    name        TEXT NOT NULL,
    price_cents INTEGER NOT NULL,
    category    TEXT NOT NULL
);

CREATE TABLE orders (
    order_id    SERIAL PRIMARY KEY,
    tenant_id   INTEGER NOT NULL REFERENCES tenants(tenant_id),
    customer_id INTEGER NOT NULL,
    created_at  TIMESTAMP NOT NULL,
    status      TEXT NOT NULL
);

CREATE TABLE order_items (
    order_item_id SERIAL PRIMARY KEY,
    order_id      INTEGER NOT NULL REFERENCES orders(order_id),
    product_id    INTEGER NOT NULL REFERENCES products(product_id),
    tenant_id     INTEGER NOT NULL REFERENCES tenants(tenant_id),
    quantity      INTEGER NOT NULL
);

-- Baseline indexes every well-run tenant would have on their own hot path.
CREATE INDEX idx_orders_tenant_created ON orders(tenant_id, created_at);
CREATE INDEX idx_products_tenant ON products(tenant_id);

-- Deliberately NOT indexing order_items(tenant_id, order_id) or
-- order_items(product_id) -- this absence is what makes the noisy
-- tenant's query pathologically expensive later. A real onboarding
-- gap like this is common: a tenant's schema "works" in dev at low
-- volume and only becomes a problem once data and concurrency grow.
