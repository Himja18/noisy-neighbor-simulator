from noisy_neighbor.workload import GoodTenantWorkload, NoisyTenantWorkload, Tenant


def test_good_tenant_query_scopes_to_tenant_id():
    tenant = Tenant(tenant_id=42, name="acme", is_noisy=False)
    sql, params = GoodTenantWorkload(tenant).query()
    assert params == (42,)
    assert "WHERE tenant_id" in sql


def test_noisy_tenant_query_scopes_to_tenant_id():
    tenant = Tenant(tenant_id=99, name="noisy", is_noisy=True)
    sql, params = NoisyTenantWorkload(tenant).query()
    assert params == (99,)
    assert "oi.tenant_id" in sql


def test_tenant_is_immutable():
    tenant = Tenant(tenant_id=1, name="x", is_noisy=False)
    try:
        tenant.tenant_id = 2
        assert False, "Tenant should be frozen"
    except Exception:
        pass
