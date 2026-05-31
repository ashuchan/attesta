"""
Tenant isolation tests — written before the full repos, to drive the contract.
These test the tenancy layer in isolation using simple in-memory stubs.
"""
from __future__ import annotations

import uuid

import pytest

from sourceloop.repositories.tenant_scoped import TenantScopedRepository
from sourceloop.tenancy.context import TenantContext, _tenant_ctx
from sourceloop.tenancy.errors import CrossTenantAccessError


class StubRepo(TenantScopedRepository):
    """Minimal stub to test tenancy enforcement."""

    def read(self, row_tenant_id: uuid.UUID) -> str:
        self._assert_tenant(row_tenant_id)
        return "ok"


def test_correct_tenant_passes() -> None:
    tenant_id = uuid.uuid4()
    TenantContext.set(tenant_id)
    repo = StubRepo()
    assert repo.read(tenant_id) == "ok"


def test_wrong_tenant_raises() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    TenantContext.set(tenant_a)
    repo = StubRepo()
    with pytest.raises(CrossTenantAccessError):
        repo.read(tenant_b)


def test_no_tenant_context_raises() -> None:
    _tenant_ctx.set(None)
    with pytest.raises(RuntimeError):
        TenantContext.get()


def test_two_tenants_isolated() -> None:
    tenant_a = uuid.uuid4()
    tenant_b = uuid.uuid4()
    repo = StubRepo()

    TenantContext.set(tenant_a)
    assert repo.read(tenant_a) == "ok"
    with pytest.raises(CrossTenantAccessError):
        repo.read(tenant_b)

    TenantContext.set(tenant_b)
    assert repo.read(tenant_b) == "ok"
    with pytest.raises(CrossTenantAccessError):
        repo.read(tenant_a)
