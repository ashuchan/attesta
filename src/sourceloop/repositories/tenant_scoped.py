from __future__ import annotations

import uuid
from typing import Any

from sourceloop.tenancy.context import TenantContext
from sourceloop.tenancy.errors import CrossTenantAccessError

from .base import AbstractRepository


class TenantScopedRepository(AbstractRepository[Any]):
    """
    Base for all tenant-private repositories. Automatically injects tenant_id
    into writes and WHERE clauses. Any row returned with a different tenant_id
    raises CrossTenantAccessError — defense in depth.
    """

    def _current_tenant(self) -> uuid.UUID:
        return TenantContext.get()

    def _assert_tenant(self, row_tenant_id: uuid.UUID) -> None:
        ctx = self._current_tenant()
        if row_tenant_id != ctx:
            raise CrossTenantAccessError(
                f"Attempted cross-tenant access: context={ctx}, row={row_tenant_id}"
            )
