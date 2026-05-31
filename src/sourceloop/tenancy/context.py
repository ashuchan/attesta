from __future__ import annotations

import uuid
from contextvars import ContextVar

_tenant_ctx: ContextVar[uuid.UUID | None] = ContextVar("tenant_id", default=None)


class TenantContext:
    @staticmethod
    def set(tenant_id: uuid.UUID) -> None:
        _tenant_ctx.set(tenant_id)

    @staticmethod
    def get() -> uuid.UUID:
        val = _tenant_ctx.get()
        if val is None:
            raise RuntimeError(
                "No tenant context set. Call TenantContext.set() first."
            )
        return val

    @staticmethod
    def get_optional() -> uuid.UUID | None:
        return _tenant_ctx.get()
