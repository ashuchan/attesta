from __future__ import annotations

from abc import ABC
from typing import Generic, TypeVar

T = TypeVar("T")


class AbstractRepository(ABC, Generic[T]):
    """Base for all repositories. Global repos extend this directly."""

    pass
