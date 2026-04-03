"""Shared pytest fixtures for integration tests."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import TYPE_CHECKING, Protocol

import pytest
from starlette.applications import Starlette

if TYPE_CHECKING:
    from collections.abc import AsyncIterator

    from starlette_tailwindcss import TailwindCSS


class StarletteAppFactory(Protocol):
    """Build a Starlette app that runs Tailwind in lifespan."""

    def __call__(
        self,
        tailwind: TailwindCSS,
        *,
        debug: bool = ...,
    ) -> Starlette:
        """Return a Starlette app configured with Tailwind lifespan."""
        ...


@pytest.fixture
def starlette_app_factory() -> StarletteAppFactory:
    """Build a Starlette app that runs Tailwind in lifespan."""

    def factory(
        tailwind: TailwindCSS,
        *,
        debug: bool = True,
    ) -> Starlette:
        @asynccontextmanager
        async def lifespan(app: Starlette) -> AsyncIterator[None]:
            async with tailwind.build(watch=app.debug):
                yield

        return Starlette(debug=debug, lifespan=lifespan)

    return factory
